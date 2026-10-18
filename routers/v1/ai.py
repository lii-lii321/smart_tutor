"""
AI 助手路由（阶段 1a：自然语言找单；阶段 1b：知识库问答）。

分层：order_query_tools 只解析条件（LLM），order_search 只查库；knowledge 只
管知识库数据，assistant 只做问答编排。本路由套用与既有接口相同的角色/租户
守卫——大模型不持有任何数据权限；平台公共库（tenant_id=NULL）写权仅
super_admin，越权访问按 404 口径不泄露存在性。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import TokenPayload, assert_tenant_scope, require_role, require_tenant_owner
from middleware.rate_limit import check_ai_query_rate_limit
from models.domain import KnowledgeDocument, Order, Teacher
from models.schemas import (
    AssistantQueryRequest,
    AssistantQueryResponse,
    FindOrdersRequest,
    FindOrdersResponse,
    KnowledgeDocCreateRequest,
    KnowledgeDocDetail,
    KnowledgeDocItem,
    KnowledgeDocListResponse,
    KnowledgeDocUpdateRequest,
    SimilarOrdersResponse,
)
from services import assistant, knowledge, order_search, order_semantic, teacher_order_search
from services.embedding import EmbeddingUnavailableError
from services.order_query_tools import parse_find_order_conditions, resolve_anchor
from utils.clock import utcnow

router = APIRouter(prefix="/api/v1/ai", tags=["AI 助手"])


@router.post("/find-orders", response_model=FindOrdersResponse)
async def find_orders(
    body: FindOrdersRequest,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """自然语言找单：解析条件（LLM）→ 租户内结构化查询 → 脱敏订单卡片。"""
    await check_ai_query_rate_limit(payload)
    started_at = utcnow()

    try:
        conditions, warnings = await parse_find_order_conditions(body.query)
    except ValueError as e:
        # LLM 输出不可解析/未识别出有效条件：与 batch-parse 同契约转 422
        raise HTTPException(status_code=422, detail=str(e)) from e

    # 距离条件的锚点解析，优先级：用户写明的地点（地理编码）> 设备定位（"附近"
    # 即"我附近"）> 在招订单中心兜底（定位不可用/未授权时）。地理编码失败与
    # 无任何可用锚点都降级为忽略距离条件，并在 warnings 里如实说明。
    radius_km = conditions.get("radius_km")
    anchor_point = None
    if conditions.get("anchor"):
        anchor_point = await resolve_anchor(conditions["anchor"], radius_km, warnings)
    elif radius_km is not None and body.anchor_lng is not None and body.anchor_lat is not None:
        anchor_point = (body.anchor_lng, body.anchor_lat)
        conditions["anchor"] = "你的位置"
    if anchor_point is None and radius_km is not None:
        center = await order_search.recruiting_center(db, payload)
        if center is not None:
            anchor_point = center
            conditions["anchor"] = "在招订单中心"
            warnings.append("未获取到你的位置，已按你在招订单的中心位置计算距离")
        else:
            warnings.append(
                "无法确定「附近」的参照点（暂无在招订单），已忽略距离条件；可补充地点，如「武侯区10公里内」"
            )
    if anchor_point is None:
        conditions.pop("radius_km", None)

    result = await order_search.search_orders(db, payload, conditions, warnings, anchor_point)

    latency_ms = int((utcnow() - started_at).total_seconds() * 1000)
    await assistant.log_ai_query(
        db, payload, intent="find_orders", question=body.query, latency_ms=latency_ms
    )
    return result


@router.post("/teacher/find-orders")
async def teacher_find_orders(
    body: FindOrdersRequest,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """教员端 AI 找单：全平台在招订单、教员脱敏口径（坐标降精度、无家长信息）、
    排除已投递与被拉黑租户，距离按教员常驻地计算。"""
    await check_ai_query_rate_limit(payload)

    teacher = await db.get(Teacher, payload.teacher_id)
    if teacher is None:
        raise HTTPException(status_code=404, detail="教员不存在")

    try:
        conditions, warnings = await parse_find_order_conditions(body.query)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    result = await teacher_order_search.find_orders_for_teacher(db, teacher, conditions, warnings)
    await assistant.log_ai_query(
        db, payload, intent="find_orders", question=body.query, latency_ms=None
    )
    return result


# ── 知识库管理（阶段 1b）──


def _doc_item(doc: KnowledgeDocument) -> dict:
    return {
        "id": doc.id,
        "tenant_id": doc.tenant_id,
        "title": doc.title,
        "source_type": doc.source_type,
        "status": doc.status,
        "chunk_count": doc.chunk_count,
        "fail_reason": doc.fail_reason,
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }


async def _get_managed_doc(
    doc_id: int, payload: TokenPayload, db: AsyncSession
) -> KnowledgeDocument:
    """取可管理的文档：租户只能管本租户文档；super_admin 只管平台公共库。
    越权一律 404（对齐 assert_tenant_scope 口径，不泄露存在性）。"""
    doc = await db.get(KnowledgeDocument, doc_id)
    if doc is None or doc.deleted_at is not None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if payload.role == "super_admin":
        if doc.tenant_id is not None:
            raise HTTPException(status_code=404, detail="文档不存在")
    else:
        assert_tenant_scope(payload, doc.tenant_id, detail="文档不存在")
    return doc


@router.post("/knowledge/documents", response_model=KnowledgeDocItem, status_code=201)
async def create_knowledge_document(
    body: KnowledgeDocCreateRequest,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """上传知识文档（粘贴文本）。同步切分+向量化；Embedding 不可用时文档
    置 failed 可重试，接口本身始终受理成功。"""
    doc = KnowledgeDocument(
        tenant_id=payload.tenant_id,  # super_admin 无 tid → NULL = 平台公共库
        title=body.title.strip(),
        source_type=body.source_type,
        content=body.content,
        status="pending",
        created_by_role=payload.role,
    )
    db.add(doc)
    await db.flush()  # 取 id 供切片挂载
    await knowledge.process_document(db, doc)
    item = _doc_item(doc)  # commit 会过期实例（expire_on_commit），响应字段先取值
    await db.commit()
    return item


@router.get("/knowledge/documents", response_model=KnowledgeDocListResponse)
async def list_knowledge_documents(
    tenant_id: int | None = None,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """文档列表：租户看「本租户 + 平台公共库」；super_admin 默认平台库，
    可显式传 tenant_id 查看指定租户的库（含平台公共文档）。"""
    query = select(KnowledgeDocument).where(KnowledgeDocument.deleted_at.is_(None))
    if payload.role == "super_admin":
        if tenant_id is not None:
            query = query.where(
                or_(
                    KnowledgeDocument.tenant_id == tenant_id,
                    KnowledgeDocument.tenant_id.is_(None),
                )
            )
        else:
            query = query.where(KnowledgeDocument.tenant_id.is_(None))
    else:
        query = query.where(
            or_(
                KnowledgeDocument.tenant_id == payload.tenant_id,
                KnowledgeDocument.tenant_id.is_(None),
            )
        )

    total = (await db.scalars(select(func.count()).select_from(query.subquery()))).one()
    rows = (await db.scalars(query.order_by(KnowledgeDocument.created_at.desc()))).all()
    return {
        "items": [_doc_item(doc) for doc in rows],
        "total": total,
    }


@router.get("/knowledge/documents/{doc_id}", response_model=KnowledgeDocDetail)
async def get_knowledge_document(
    doc_id: int,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """文档详情（含正文，供编辑回显）。平台公共文档所有 B 端可读。"""
    doc = await db.get(KnowledgeDocument, doc_id)
    if doc is None or doc.deleted_at is not None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.tenant_id is not None:
        assert_tenant_scope(payload, doc.tenant_id, detail="文档不存在")
    return {**_doc_item(doc), "content": doc.content}


@router.put("/knowledge/documents/{doc_id}", response_model=KnowledgeDocItem)
async def update_knowledge_document(
    doc_id: int,
    body: KnowledgeDocUpdateRequest,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """更新文档：正文变更即重切分重向量化（旧切片先清掉）。"""
    doc = await _get_managed_doc(doc_id, payload, db)
    if body.title is not None:
        doc.title = body.title.strip()
    if body.content is not None and body.content != doc.content:
        doc.content = body.content
        doc.status = "pending"
        doc.chunk_count = 0
        await knowledge.delete_document_chunks(db, doc)
        await knowledge.process_document(db, doc)
        # 先 flush 落盘 pending 变更，再重载服务端生成的 updated_at
        # （refresh 不自动 flush：直接重载会用 DB 旧值覆盖内存改动）
        await db.flush()
        await db.refresh(doc)
    item = _doc_item(doc)  # 同 create：commit 过期实例前取响应字段
    await db.commit()
    return item


@router.delete("/knowledge/documents/{doc_id}")
async def delete_knowledge_document(
    doc_id: int,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """删除文档（软删）并清理向量切片；删除后检索即刻不可见。"""
    doc = await _get_managed_doc(doc_id, payload, db)
    await knowledge.delete_document(db, doc)
    await db.commit()
    return {"ok": True}


# ── 知识库问答（阶段 1b）──


@router.post("/assistant/query", response_model=AssistantQueryResponse)
async def assistant_query(
    body: AssistantQueryRequest,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """知识库问答：检索本租户+平台公共库，回答带来源引用；无依据如实说明。"""
    await check_ai_query_rate_limit(payload)
    try:
        return await assistant.answer_knowledge_question(db, payload, body.question)
    except HTTPException:
        raise
    except Exception:
        # LLM/网络级异常统一 503：检索失败与生成失败的降级文案已在服务层兜住，
        # 能到这里的是未预期异常，如实告知暂不可用
        raise HTTPException(status_code=503, detail="AI 服务暂时不可用，请稍后重试") from None


# ── 相似订单（阶段 2）──


@router.get("/orders/{order_id}/similar", response_model=SimilarOrdersResponse)
async def similar_orders(
    order_id: int,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """相似订单：向量初筛 + 实时 orders 表复核（租户/招聘中/未过期）。
    已有索引时零嵌入调用；索引缺失需现场向量化，服务不可用返回 503。"""
    order = await db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    assert_tenant_scope(payload, order.tenant_id, detail="订单不存在")

    try:
        items = await order_semantic.find_similar_orders(db, order)
    except EmbeddingUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="语义检索服务暂不可用（Embedding 未配置或超时），请稍后重试",
        ) from None
    return {"items": items}
