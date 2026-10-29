"""
AI 找单 · 订单查询执行：条件字典 → 租户内候选 → 内存精筛 → 脱敏卡片。

与 services/order_query_tools.py（LLM 条件解析）物理隔离：本模块不 import
任何 LLM 客户端，只消费规范化后的条件字典。查询层只有等值条件（活跃状态 +
token 内租户 ID）；全部 AI 派生条件（价格/科目/年级/距离）与过期过滤在候选
集（≤上限条）上内存精筛——提示注入无从改变查询语义，租户边界由
tenant_scoped 统一强制。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from middleware.auth import TokenPayload, tenant_scoped
from models.domain import Order, OrderStatus
from services import serializers
from services.order_query_tools import match_conditions
from utils.clock import utcnow
from utils.geo import haversine_distance

# 候选扫描上限：与推荐服务同口径，防止全租户大表扫描拖垮列表查询
_SCAN_LIMIT = 300
_RESULT_LIMIT = 20
_CENTER_SCAN_LIMIT = 500


async def recruiting_center(db: AsyncSession, payload: TokenPayload) -> tuple[float, float] | None:
    """
    在招订单的坐标中位数（租户内；super_admin 为全平台）："附近 N 公里"
    未指参照地点时的默认锚点——中介口中的"附近"即其经营区域。
    暂无在招订单返回 None，由调用方降级为忽略距离条件。
    """
    stmt = select(Order).where(Order.status == OrderStatus.recruiting)
    stmt = tenant_scoped(stmt, payload, Order.tenant_id).limit(_CENTER_SCAN_LIMIT)
    orders = (await db.scalars(stmt)).all()
    if not orders:
        return None
    lngs = sorted(float(order.lng) for order in orders)
    lats = sorted(float(order.lat) for order in orders)

    def _median(values: list[float]) -> float:
        mid = len(values) // 2
        if len(values) % 2 == 1:
            return values[mid]
        return (values[mid - 1] + values[mid]) / 2

    return _median(lngs), _median(lats)


async def search_orders(
    db: AsyncSession,
    payload: TokenPayload,
    conditions: dict,
    warnings: list[str],
    anchor_point: tuple[float, float] | None = None,
) -> dict:
    """执行找单：SQL 粗筛（仅等值的租户+状态）→ 内存精筛（条件字典）→ 脱敏卡片。

    anchor_point 由调用方解析后传入（本模块不触达地理编码服务）；
    距离过滤仅在锚点与半径同时存在时生效。
    """
    now = utcnow()

    query = select(Order).where(Order.status == OrderStatus.recruiting)
    query = tenant_scoped(query, payload, Order.tenant_id)
    query = query.order_by(Order.created_at.desc()).limit(_SCAN_LIMIT)
    candidates = (await db.scalars(query)).all()
    if len(candidates) == _SCAN_LIMIT:
        warnings.append(f"候选较多，仅扫描了最近 {_SCAN_LIMIT} 条招聘中订单")

    radius_km = conditions.get("radius_km")

    matched: list[tuple[Order, float | None]] = []
    for order in candidates:
        if not match_conditions(order, conditions, now):
            continue
        distance_km: float | None = None
        # 距离过滤仅在锚点与半径同时存在时生效（与 docstring 口径一致），收窄 radius_km 的 Optional
        if anchor_point and radius_km is not None:
            distance_m = haversine_distance(
                anchor_point[0], anchor_point[1], float(order.lng), float(order.lat)
            )
            if distance_m > radius_km * 1000:
                continue
            distance_km = round(distance_m / 1000, 2)
        matched.append((order, distance_km))

    if anchor_point:
        matched.sort(key=lambda pair: pair[1] if pair[1] is not None else float("inf"))

    items = []
    for order, distance_km in matched[:_RESULT_LIMIT]:
        item = serializers.order_list_payload(order, is_teacher_view=False)
        item["distance_km"] = distance_km
        items.append(item)

    return {
        "conditions": conditions,
        "warnings": warnings,
        "total_matched": len(matched),
        "scanned": len(candidates),
        "items": items,
    }
