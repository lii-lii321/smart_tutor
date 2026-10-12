"""
AI 助手路由（阶段 1a：自然语言找单；阶段 1b 扩展知识库问答）。

分层：order_query_tools 只解析条件（LLM），order_search 只查库；本路由编排
二者并套用与订单接口相同的角色/租户守卫——大模型不持有任何数据权限。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import TokenPayload, require_tenant_owner
from middleware.rate_limit import check_ai_query_rate_limit
from models.schemas import FindOrdersRequest, FindOrdersResponse
from services import order_search
from services.order_query_tools import parse_find_order_conditions, resolve_anchor

router = APIRouter(prefix="/api/v1/ai", tags=["AI 助手"])


@router.post("/find-orders", response_model=FindOrdersResponse)
async def find_orders(
    body: FindOrdersRequest,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """自然语言找单：解析条件（LLM）→ 租户内结构化查询 → 脱敏订单卡片。"""
    await check_ai_query_rate_limit(payload)

    try:
        conditions, warnings = await parse_find_order_conditions(body.query)
    except ValueError as e:
        # LLM 输出不可解析/未识别出有效条件：与 batch-parse 同契约转 422
        raise HTTPException(status_code=422, detail=str(e)) from e

    # 地理编码失败降级为忽略距离条件：条件回显里不再保留未生效的半径
    anchor_point = await resolve_anchor(
        conditions.get("anchor"), conditions.get("radius_km"), warnings
    )
    if anchor_point is None:
        conditions.pop("radius_km", None)

    return await order_search.search_orders(db, payload, conditions, warnings, anchor_point)
