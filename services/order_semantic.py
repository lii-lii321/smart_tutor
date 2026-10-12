"""
订单语义索引（阶段 2）：白名单文本化 → 向量化 → 同步；相似订单检索。

安全红线：索引文本只含白名单业务字段，parent_phone / exact_address /
raw_text 永不进入（raw_text 是微信群原文，可能含家长联系方式）——
order_index_text 由测试锁定，新增字段必须先过白名单评审。

一致性模型：本表只是加速结构。相似检索永远以实时 orders 表复核租户与
状态（recruiting 且未过期），状态流转无需改写索引；文本变更由写入钩子
（batch-import / PATCH，BackgroundTasks）驱动同步，scheduler 每轮对缺失
索引的招聘中订单兜底回填。
"""

import logging

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import _get_sessionmaker
from models.domain import Order, OrderSemanticIndex, OrderStatus
from services import serializers
from services.embedding import embed_texts, l2_normalize
from utils.clock import utcnow

logger = logging.getLogger(__name__)

_EMBED_BATCH_SIZE = 16
_DEFAULT_LIMIT = 5
# 相似度下限：bge-m3 余弦，无关订单通常 <0.4；阈值放宽交给前端排序展示
_MIN_SCORE = 0.35


def order_index_text(order: Order) -> str:
    """索引文本 = 白名单业务字段拼接（年级科目/教员要求/模糊地址/交通备注/课酬原文）。"""
    parts = [
        order.grade_subject,
        order.requirements or "",
        order.fuzzy_address,
        order.subway_remark or "",
        order.price_total,
    ]
    return "\n".join(part.strip() for part in parts if part and part.strip())


async def sync_orders_batch(db: AsyncSession, orders: list[Order]) -> int:
    """批量同步索引（不 commit，随调用方事务提交）；返回同步条数。"""
    if not orders:
        return 0

    texts = [order_index_text(order) for order in orders]
    vectors: list[list[float]] = []
    for start in range(0, len(texts), _EMBED_BATCH_SIZE):
        vectors.extend(await embed_texts(texts[start : start + _EMBED_BATCH_SIZE]))

    now = utcnow()
    for order, text, vector in zip(orders, texts, vectors, strict=True):
        row = await db.get(OrderSemanticIndex, order.id)
        if row is None:
            row = OrderSemanticIndex(order_id=order.id, tenant_id=order.tenant_id)
            db.add(row)
        row.content = text
        row.embedding = pack_vector(vector)
        row.embedding_dim = len(vector)
        row.synced_at = now
    return len(orders)


async def backfill_missing(db: AsyncSession, limit: int = 50) -> int:
    """补齐缺索引的招聘中订单（调度兜底/新库回填）；不 commit。
    Embedding 服务不可用时抛出，由调用方决定重试节奏。"""
    stmt = (
        select(Order)
        .outerjoin(OrderSemanticIndex, OrderSemanticIndex.order_id == Order.id)
        .where(
            Order.status == OrderStatus.recruiting,
            OrderSemanticIndex.order_id.is_(None),
        )
        .order_by(Order.id.desc())
        .limit(limit)
    )
    orders = list((await db.scalars(stmt)).all())
    return await sync_orders_batch(db, orders)


async def sync_order_ids(order_ids: list[int]) -> None:
    """独立会话同步指定订单（BackgroundTasks 用）：失败只记日志，调度兜底补齐。"""
    if not order_ids:
        return
    try:
        sessionmaker = _get_sessionmaker()
        async with sessionmaker() as session:
            orders = list(
                (await session.scalars(select(Order).where(Order.id.in_(order_ids)))).all()
            )
            await sync_orders_batch(session, orders)
            await session.commit()
    except Exception:
        logger.exception("订单语义索引同步失败 ids=%s（等调度兜底回填）", order_ids)


async def find_similar_orders(
    db: AsyncSession, order: Order, *, limit: int = _DEFAULT_LIMIT
) -> list[dict]:
    """
    相似订单：优先复用已存向量（零嵌入调用），索引缺失时现场向量化一次。
    候选 = 同租户 + recruiting + 未过期；先向量粗排，再以实时 orders 复核。
    """
    index_row = await db.get(OrderSemanticIndex, order.id)
    if index_row is not None:
        query_vector = unpack_vector(index_row.embedding, index_row.embedding_dim)
    else:
        [vector] = await embed_texts([order_index_text(order)])
        query_vector = l2_normalize(np.asarray(vector, dtype=np.float32))

    candidates = (
        await db.scalars(
            select(OrderSemanticIndex).where(
                OrderSemanticIndex.tenant_id == order.tenant_id,
                OrderSemanticIndex.order_id != order.id,
            )
        )
    ).all()

    scored: list[tuple[float, int]] = []
    for row in candidates:
        score = float(np.dot(query_vector, unpack_vector(row.embedding, row.embedding_dim)))
        if score >= _MIN_SCORE:
            scored.append((score, row.order_id))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    # DB 复核精排：状态/有效期以实时 orders 表为准，向量只是初筛
    top_ids = [order_id for _, order_id in scored[: limit * 3]]
    if not top_ids:
        return []
    order_rows = list((await db.scalars(select(Order).where(Order.id.in_(top_ids)))).all())
    score_by_id = {order_id: score for score, order_id in scored}

    items: list[dict] = []
    for candidate in order_rows:
        if candidate.status != OrderStatus.recruiting or (
            candidate.expired_at is not None and candidate.expired_at <= utcnow()
        ):
            continue
        payload = serializers.order_list_payload(candidate, is_teacher_view=False)
        payload["similarity"] = round(score_by_id[candidate.id], 4)
        items.append(payload)
    items.sort(key=lambda item: item["similarity"], reverse=True)
    return items[:limit]


def pack_vector(vector: list[float]) -> bytes:
    arr = l2_normalize(np.asarray(vector, dtype=np.float32))
    return arr.tobytes()


def unpack_vector(blob: bytes, dim: int) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)[:dim]
