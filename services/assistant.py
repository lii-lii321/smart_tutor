"""
知识库问答编排：检索 → 带引用生成 → 调用日志。

诚实性约束：知识库无依据/服务不可用时如实说明，绝不编造智派的业务规则；
答案要求带来源编号，来源与切片原文随响应下发供用户核对。
"""

import json
import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.auth import TokenPayload
from models.domain import AiQueryLog, KnowledgeDocument
from services import knowledge
from services.embedding import EmbeddingUnavailableError
from services.llm_client import chat

logger = logging.getLogger(__name__)

KB_SYSTEM_PROMPT = """你是智派家教系统的 AI 业务助手，只依据给定的资料回答问题。

规则：
1. 回答必须完全基于资料内容，不得编造智派的功能、流程、收费标准或业务规则；
2. 引用资料时在对应句子后标注来源编号（如 [1]、[2]）；
3. 资料不足以回答时，直接说明"知识库中没有找到相关内容"，并建议用户联系管理员补充；
4. 回答简洁、可执行，使用中文，适当分点。

资料（带编号）：
{sources}"""


async def log_ai_query(
    db: AsyncSession,
    payload: TokenPayload,
    *,
    intent: str,
    question: str,
    answer_chars: int = 0,
    hit_document_ids: list[int] | None = None,
    latency_ms: int | None = None,
) -> None:
    """AI 调用日志落库：失败只记日志不阻断业务（与资金审计同哲学）。"""
    try:
        db.add(
            AiQueryLog(
                tenant_id=payload.tenant_id,
                actor_role=payload.role,
                actor_id=payload.tenant_id or 0,
                intent=intent,
                question=question[:500],
                answer_chars=answer_chars,
                hit_document_ids=json.dumps(hit_document_ids) if hit_document_ids else None,
                latency_ms=latency_ms,
            )
        )
        await db.commit()
    except Exception:
        logger.exception("AI 调用日志写入失败 intent=%s", intent)
        await db.rollback()


async def answer_knowledge_question(db: AsyncSession, payload: TokenPayload, question: str) -> dict:
    """知识库问答：检索（租户隔离）→ 带引用生成 → 日志。永不抛业务异常，
    服务不可用/无依据都返回诚实文案（路由层只兜网络级 503）。"""
    started = time.monotonic()

    async def build_result(answer: str, citations: list[dict], hit_ids: list[int]) -> dict:
        latency_ms = int((time.monotonic() - started) * 1000)
        await log_ai_query(
            db,
            payload,
            intent="knowledge",
            question=question,
            answer_chars=len(answer),
            hit_document_ids=hit_ids,
            latency_ms=latency_ms,
        )
        return {"answer": answer, "citations": citations, "latency_ms": latency_ms}

    try:
        hits = await knowledge.search_chunks(db, payload.tenant_id, question)
    except EmbeddingUnavailableError:
        return await build_result(
            "知识库服务暂时不可用（Embedding 未配置或超时），请稍后再试，或联系平台管理员。",
            [],
            [],
        )

    if not hits:
        return await build_result(
            "知识库中没有找到与该问题相关的内容。"
            "如果是智派的功能使用或业务规则问题，建议联系系统管理员补充知识库文档后再试。",
            [],
            [],
        )

    doc_ids = sorted({hit["document_id"] for hit in hits})
    docs = (
        await db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.id.in_(doc_ids)))
    ).all()
    titles = {doc.id: doc.title for doc in docs}

    sources_text = "\n\n".join(
        f"[{i}] （{titles.get(hit['document_id'], '未知文档')}）{hit['content']}"
        for i, hit in enumerate(hits, start=1)
    )
    citations = [
        {
            "index": i,
            "document_id": hit["document_id"],
            "title": titles.get(hit["document_id"], "未知文档"),
            "snippet": hit["content"][:80],
            "score": hit["score"],
        }
        for i, hit in enumerate(hits, start=1)
    ]

    try:
        answer = await chat(
            KB_SYSTEM_PROMPT.replace("{sources}", sources_text),
            f"用户问题：{question}",
            temperature=0.2,
            max_tokens=1024,
        )
    except ValueError:
        # LLM 返回不可解析：检索仍然可信，把来源原样给用户而不是整体失败
        answer = "AI 生成回答时出现问题，以下是与问题相关的知识库内容，请直接参考。"

    return await build_result(answer, citations, doc_ids)
