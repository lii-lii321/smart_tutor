"""
教员端 AI 找单：自然语言条件 → 全平台在招订单（教员脱敏口径）。

与 order_query_tools/order_search 的分工：条件解析复用同一提示词与归一规则；
本模块的数据口径是教员侧——跨租户招聘中订单、坐标降精度（recommendation
payload）、排除已投递与被拉黑租户，距离按教员常驻地计算。查询层只有等值
条件与 token 内教员 ID，LLM 派生条件一律内存精筛（与 order_search 同不变式）。
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.domain import (
    Application,
    Order,
    OrderStatus,
    Teacher,
    TeacherSubscription,
    TenantTeacherBlacklist,
)
from services.order_query_tools import match_conditions
from services.serializers import order_recommendation_payload
from utils.clock import utcnow
from utils.geo import haversine_distance

logger = logging.getLogger(__name__)

# 候选扫描上限与返回条数：教员跨租户找单，扫描面大于单租户搜索
_SCAN_LIMIT = 500
_RESULT_LIMIT = 20


def subscription_conditions(sub: TeacherSubscription | None) -> dict:
    """
    订阅偏好 → 找单条件字典（与 LLM 解析产物同构，多选用列表口径）。
    无订阅/条件全空时返回空 dict：match_conditions 全放行，等价"按距离看全部在招单"。
    """
    if sub is None:
        return {}
    conditions: dict = {}
    subjects = [s for s in (sub.subjects or "").split(",") if s]
    grades = [g for g in (sub.grades or "").split(",") if g]
    if subjects:
        conditions["subjects"] = subjects
    if grades:
        conditions["grades"] = grades
    if sub.min_base_price is not None:
        conditions["min_base_price"] = float(sub.min_base_price)
    return conditions


async def find_orders_for_teacher(
    db: AsyncSession, teacher: Teacher, conditions: dict, warnings: list[str]
) -> dict:
    """
    教员视角找单：SQL 粗筛（等值：招聘中）→ 内存精筛（条件字典）→
    排除已投递/拉黑租户 → 教员脱敏 payload + 距离。
    """
    now = utcnow()
    radius_km = conditions.get("radius_km")
    teacher_coords = (
        (float(teacher.lng), float(teacher.lat))
        if teacher.lng is not None and teacher.lat is not None
        else None
    )
    if radius_km is not None and teacher_coords is None:
        warnings.append("常驻地未设置，已忽略距离条件；可在「个人资料」中设置常驻地后重试")

    query = select(Order).where(Order.status == OrderStatus.recruiting)
    query = query.order_by(Order.created_at.desc()).limit(_SCAN_LIMIT)
    candidates = (await db.scalars(query)).all()
    # 与 B 端 order_search 同口径：候选达到扫描上限时如实告警，更早的有效单可能漏在窗口外
    if len(candidates) == _SCAN_LIMIT:
        warnings.append(f"候选较多，仅扫描了最近 {_SCAN_LIMIT} 条招聘中订单")

    # 排除集合：本教员的拉黑租户与已投递订单
    blacklisted_tenant_ids = set(
        (
            await db.scalars(
                select(TenantTeacherBlacklist.tenant_id).where(
                    TenantTeacherBlacklist.teacher_id == teacher.id
                )
            )
        ).all()
    )
    applied_order_ids = set(
        (
            await db.scalars(
                select(Application.order_id).where(Application.teacher_id == teacher.id)
            )
        ).all()
    )

    matched: list[tuple[Order, float | None]] = []
    for order in candidates:
        if order.tenant_id in blacklisted_tenant_ids:
            continue
        if order.id in applied_order_ids:
            continue
        if not match_conditions(order, conditions, now):
            continue
        distance_km: float | None = None
        if teacher_coords:
            distance_m = haversine_distance(
                teacher_coords[0], teacher_coords[1], float(order.lng), float(order.lat)
            )
            if radius_km is not None and distance_m > radius_km * 1000:
                continue
            distance_km = round(distance_m / 1000, 2)
        matched.append((order, distance_km))

    if teacher_coords:
        matched.sort(key=lambda pair: pair[1] if pair[1] is not None else float("inf"))

    items = []
    for order, distance_km in matched[:_RESULT_LIMIT]:
        payload = order_recommendation_payload(order)
        payload["is_summer_vacation"] = bool(order.is_summer_vacation)
        payload["expired_at"] = order.expired_at.isoformat() if order.expired_at else None
        payload["distance_km"] = distance_km
        payload["total_score"] = 90
        payload["score_breakdown"] = {
            "distance": 90 if distance_km is not None else 60,
            "subject": 90,
            "grade": 90,
            "school": 60,
            "price": 90,
            "history": 60,
        }
        payload["status"] = order.status.value if order.status else None
        payload["reasons"] = ["匹配你的搜索条件"]
        payload["already_applied"] = False
        items.append(payload)

    return {
        "warnings": warnings,
        "total_matched": len(matched),
        "scanned": len(candidates),
        "items": items,
    }
