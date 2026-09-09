"""
教员信用画像聚合：成交数（投递终态）、违约数（没收流水）、评价均分。
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.domain import (
    Application,
    ApplicationStatus,
    FinancialRecord,
    FinancialType,
    OrderReview,
)


async def teacher_credit_map(db: AsyncSession, teacher_ids: list[int]) -> dict[int, dict]:
    """
    批量聚合一批教员的信用画像。
    三条 GROUP BY 覆盖整批教员，避免逐人三次聚合的 N+1。
    """
    if not teacher_ids:
        return {}
    credit: dict[int, dict] = {}

    rows = (await db.execute(
        select(Application.teacher_id, func.count())
        .where(
            Application.teacher_id.in_(teacher_ids),
            Application.status == ApplicationStatus.completed,
        )
        .group_by(Application.teacher_id)
    )).all()
    for teacher_id, count in rows:
        credit.setdefault(teacher_id, {})["completed_count"] = int(count)

    rows = (await db.execute(
        select(FinancialRecord.teacher_id, func.count())
        .where(
            FinancialRecord.teacher_id.in_(teacher_ids),
            FinancialRecord.type == FinancialType.forfeit,
        )
        .group_by(FinancialRecord.teacher_id)
    )).all()
    for teacher_id, count in rows:
        credit.setdefault(teacher_id, {})["violation_count"] = int(count)

    rows = (await db.execute(
        select(OrderReview.teacher_id, func.avg(OrderReview.rating))
        .where(OrderReview.teacher_id.in_(teacher_ids))
        .group_by(OrderReview.teacher_id)
    )).all()
    for teacher_id, avg in rows:
        credit.setdefault(teacher_id, {})["avg_rating"] = round(float(avg), 1)

    return credit
