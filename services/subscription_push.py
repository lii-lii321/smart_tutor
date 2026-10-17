"""
教员订阅推送：新订单 → 偏好匹配 → 站内信。

触发点只有 batch-import（新单与唤醒单同入口），BackgroundTasks 异步执行
（独立会话、失败只记日志）；幂等靠 Notification 查重 (teacher_id, order_id,
title)，不需要额外推送日志表。

匹配规则（全部硬过滤，宁缺毋滥——推错的信任代价高于漏推）：
- 订阅开关开启；科目/学段留空视为不限，填了则必须命中（别名表口径）；
- 课酬下限：订单 base_price 不得低于订阅下限；
- 排除：封禁教员、被该租户拉黑的教员、已投递过该单的教员；
- 单笔订单最多通知 50 人（订阅是主动行为，该上限仅作防御）。
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import _get_sessionmaker
from models.domain import (
    Application,
    Notification,
    Order,
    OrderStatus,
    Teacher,
    TeacherSubscription,
    TenantTeacherBlacklist,
)
from services.recommendation import extract_grade, extract_subjects

logger = logging.getLogger(__name__)

_PUSH_TITLE = "订阅新单"
_MAX_NOTIFY_PER_ORDER = 50


def split_csv(value: str | None) -> set[str]:
    """逗号分隔规范名 → 集合（去空白、去空项）。"""
    return {part.strip() for part in (value or "").split(",") if part.strip()}


def match_subscription(
    order: Order,
    subscription: TeacherSubscription,
    *,
    order_subjects: set[str],
    order_grade: str,
) -> bool:
    """偏好硬匹配（科目/学段/课酬下限，留空=不限）。不含封禁/拉黑/已投递排除。"""
    if not subscription.enabled:
        return False
    wanted_subjects = split_csv(subscription.subjects)
    if wanted_subjects and not (order_subjects & wanted_subjects):
        return False
    wanted_grades = split_csv(subscription.grades)
    if wanted_grades and order_grade not in wanted_grades:
        return False
    min_price = subscription.min_base_price
    return not (min_price is not None and float(order.base_price) < float(min_price))


async def deliver_for_order(db: AsyncSession, order: Order) -> int:
    """为单笔订单做订阅匹配并发站内信（不 commit，随调用方事务提交）。"""
    if order.status != OrderStatus.recruiting:
        return 0

    subs = (
        await db.scalars(
            select(TeacherSubscription).where(TeacherSubscription.enabled == True)  # noqa: E712
        )
    ).all()
    if not subs:
        return 0

    teacher_ids = [sub.teacher_id for sub in subs]
    teachers = {
        t.id: t
        for t in (await db.scalars(select(Teacher).where(Teacher.id.in_(teacher_ids)))).all()
    }

    # 硬门槛排除：封禁 / 本租户拉黑 / 已投递过该单
    blacklisted = set(
        (
            await db.scalars(
                select(TenantTeacherBlacklist.teacher_id).where(
                    TenantTeacherBlacklist.tenant_id == order.tenant_id,
                    TenantTeacherBlacklist.teacher_id.in_(teacher_ids),
                )
            )
        ).all()
    )
    applied = set(
        (
            await db.scalars(
                select(Application.teacher_id).where(
                    Application.order_id == order.id,
                    Application.teacher_id.in_(teacher_ids),
                )
            )
        ).all()
    )
    already_notified = set(
        (
            await db.scalars(
                select(Notification.teacher_id).where(
                    Notification.teacher_id.in_(teacher_ids),
                    Notification.order_id == order.id,
                    Notification.title == _PUSH_TITLE,
                )
            )
        ).all()
    )

    order_subjects = extract_subjects(f"{order.grade_subject} {order.requirements or ''}")
    order_grade = extract_grade(order.grade_subject)

    notified = 0
    for sub in subs:
        teacher_id = sub.teacher_id
        if teacher_id in already_notified:
            continue
        teacher = teachers.get(teacher_id)
        if (
            teacher is None
            or teacher.is_banned
            or teacher_id in blacklisted
            or teacher_id in applied
        ):
            continue
        if not match_subscription(
            order, sub, order_subjects=order_subjects, order_grade=order_grade
        ):
            continue
        content = (
            f"「{order.grade_subject}」{order.price_total} · {order.fuzzy_address}，"
            "匹配你的订阅偏好，点击查看详情"
        )[:255]
        db.add(
            Notification(
                teacher_id=teacher_id,
                title=_PUSH_TITLE,
                content=content,
                order_id=order.id,
            )
        )
        notified += 1
        if notified >= _MAX_NOTIFY_PER_ORDER:
            break
    return notified


async def deliver_for_orders(order_ids: list[int]) -> None:
    """BackgroundTasks 入口：独立会话逐单匹配推送，失败只记日志。"""
    if not order_ids:
        return
    try:
        sessionmaker = _get_sessionmaker()
        async with sessionmaker() as session:
            orders = (await session.scalars(select(Order).where(Order.id.in_(order_ids)))).all()
            total = 0
            for order in orders:
                total += await deliver_for_order(session, order)
            await session.commit()
        if total:
            logger.info("订阅推送完成：%d 笔订单共通知 %d 名教员", len(order_ids), total)
    except Exception:
        logger.exception("订阅推送失败 ids=%s", order_ids)
