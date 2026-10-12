"""
知识库：文档切分 → 向量化 → 落库；租户内检索（SQL 租户过滤 + 内存余弦）。

安全边界：检索前必须在 SQL 层完成租户过滤（本租户 + 平台公共库），
相似度只在这之后计算——向量索引永远不是权限系统。
"""

import logging
import re

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.domain import KnowledgeChunk, KnowledgeDocument
from services.embedding import EmbeddingUnavailableError, embed_texts, l2_normalize
from utils.clock import utcnow

logger = logging.getLogger(__name__)

# 中文文档切分上限（字符）：bge-m3 上下文远大于此，切小是为了检索精度与引用粒度
CHUNK_MAX = 500
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？；!?;])\s*")


def split_chunks(content: str) -> list[str]:
    """空行/标题断块 → 贪心装填；超长块按句读二次切分。空文档返回空列表。"""
    normalized = (content or "").replace("\r\n", "\n").strip()
    if not normalized:
        return []

    # 候选块：空行分段，markdown 标题行强制独立起块
    blocks: list[str] = []
    current: list[str] = []
    for line in normalized.split("\n"):
        line = line.strip()
        if not line:
            if current:
                blocks.append("\n".join(current))
                current = []
        elif line.startswith("#") and current:
            blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))

    chunks: list[str] = []
    buf = ""
    for block in blocks:
        for piece in _split_long_block(block):
            if buf and len(buf) + len(piece) + 1 > CHUNK_MAX:
                chunks.append(buf)
                buf = piece
            else:
                buf = f"{buf}\n{piece}".strip()
    if buf:
        chunks.append(buf)
    return chunks


def _split_long_block(block: str) -> list[str]:
    """超长块按句读切分；单句仍超长则硬切，保证任何片段不超过 CHUNK_MAX。"""
    if len(block) <= CHUNK_MAX:
        return [block]
    pieces: list[str] = []
    buf = ""
    for sentence in _SENTENCE_SPLIT.split(block):
        while len(sentence) > CHUNK_MAX:
            if buf:
                pieces.append(buf)
                buf = ""
            pieces.append(sentence[:CHUNK_MAX])
            sentence = sentence[CHUNK_MAX:]
        if not sentence:
            continue
        if buf and len(buf) + len(sentence) > CHUNK_MAX:
            pieces.append(buf)
            buf = sentence
        else:
            buf = f"{buf}{sentence}"
    if buf:
        pieces.append(buf)
    return pieces


def pack_vector(vector: list[float]) -> bytes:
    """向量 → float32 小端 BLOB（存储前再归一化一次，防上游漏归一）。"""
    arr = l2_normalize(np.asarray(vector, dtype=np.float32))
    return arr.tobytes()


def unpack_vector(blob: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)[:dim]


async def process_document(db: AsyncSession, doc: KnowledgeDocument) -> None:
    """
    切分 + 向量化 + 切片落库（不 commit，随调用方事务提交）。
    调用前文档行需已 flush（有 id）。失败置 status=failed 并记录原因，
    不抛出——上传接口始终成功受理，失败可重试（重新触发处理即可）。
    """
    try:
        chunks = split_chunks(doc.content)
        if not chunks:
            raise ValueError("文档内容为空")
        vectors = await embed_texts(chunks)
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
            db.add(
                KnowledgeChunk(
                    document_id=doc.id,
                    tenant_id=doc.tenant_id,
                    chunk_index=index,
                    content=chunk,
                    embedding=pack_vector(vector),
                    embedding_dim=len(vector),
                )
            )
        doc.chunk_count = len(chunks)
        doc.status = "ready"
        doc.fail_reason = None
    except (EmbeddingUnavailableError, ValueError) as exc:
        doc.status = "failed"
        doc.fail_reason = str(exc)[:255]
        logger.warning("知识文档处理失败 doc=%s：%s", doc.id, exc)


async def delete_document_chunks(db: AsyncSession, doc: KnowledgeDocument) -> None:
    """只清切片（文档更新重嵌时用）；文档行不动。不 commit。"""
    chunk_rows = (
        await db.scalars(select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))
    ).all()
    for chunk in chunk_rows:
        await db.delete(chunk)


async def delete_document(db: AsyncSession, doc: KnowledgeDocument) -> None:
    """软删文档 + 硬删切片（向量可由原文重建，不留档）；不 commit。"""
    await delete_document_chunks(db, doc)
    doc.deleted_at = utcnow()


async def search_chunks(
    db: AsyncSession,
    tenant_id: int | None,
    query: str,
    *,
    top_k: int = 5,
    min_score: float = 0.35,
) -> list[dict]:
    """
    租户内检索：SQL 先做租户过滤（本租户 + 平台公共库 tenant_id IS NULL），
    再对过滤结果算点积（向量已归一化 = 余弦）。tenant_id=None（super_admin
    平台检索）只见平台库。Embedding 服务不可用时抛 EmbeddingUnavailableError。
    """
    query = (query or "").strip()
    if not query:
        return []
    [query_vector] = await embed_texts([query])
    qarr = np.asarray(query_vector, dtype=np.float32)

    stmt = (
        select(KnowledgeChunk)
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeDocument.deleted_at.is_(None),
            KnowledgeDocument.status == "ready",
        )
    )
    if tenant_id is None:
        stmt = stmt.where(KnowledgeChunk.tenant_id.is_(None))
    else:
        stmt = stmt.where(
            (KnowledgeChunk.tenant_id == tenant_id) | KnowledgeChunk.tenant_id.is_(None)
        )
    rows = (await db.scalars(stmt)).all()
    if not rows:
        return []

    scored: list[tuple[float, KnowledgeChunk]] = []
    for chunk in rows:
        dvec = unpack_vector(chunk.embedding, chunk.embedding_dim)
        score = float(np.dot(qarr, dvec))
        if score >= min_score:
            scored.append((score, chunk))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    return [
        {"document_id": chunk.document_id, "content": chunk.content, "score": round(score, 4)}
        for score, chunk in scored[:top_k]
    ]
