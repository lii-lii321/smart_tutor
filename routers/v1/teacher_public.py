"""
教员公开成绩单：中介向家长转发教员信任凭证的只读页数据。

脱敏口径（与橱窗同纪律）：
- 姓名只露姓氏（"张老师"）；不露手机号/微信号/坐标/常驻地；
- 只统计可见的经营事实：成交数、违约数、评价均分与评语；
- 封禁教员立即 404（防继续借平台背书）。
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.domain import Order, OrderReview, Teacher
from services.credit import teacher_credit_map

router = APIRouter(prefix="/api/v1/public/teacher", tags=["公开接口"])


class ScorecardReview(BaseModel):
    rating: int
    comment: str | None
    grade_subject: str | None
    created_at: object | None  # ISO 串序列化，前端本地化展示


class ScorecardResponse(BaseModel):
    teacher_id: int
    display_name: str
    school: str
    major: str | None
    grade: str | None
    tags: list[str]
    completed_count: int
    violation_count: int
    avg_rating: float | None
    review_count: int
    reviews: list[ScorecardReview]


def _masked_name(name: str) -> str:
    """只露姓氏：单字名原样 + "老师"，多字名取首字 + "老师"。"""
    return f"{name[0]}老师" if name else "老师"


def _tags(teacher: Teacher) -> list[str]:
    tags = []
    if teacher.is_985:
        tags.append("985")
    if teacher.is_211:
        tags.append("211")
    if teacher.is_double_first_class:
        tags.append("双一流")
    # 兜底：只勾了 985/211 联合位
    if not tags and teacher.is_985_211:
        tags.append("985/211")
    return tags


@router.get("/{teacher_id}/scorecard", response_model=ScorecardResponse)
async def teacher_scorecard(teacher_id: int, db: AsyncSession = Depends(get_db)):
    """公开成绩单：教员的脱敏画像 + 最近评价（一单一评）。无需登录。"""
    teacher = await db.get(Teacher, teacher_id)
    if not teacher or teacher.is_banned:
        # 不存在与封禁同响应，不泄露存在性
        raise HTTPException(status_code=404, detail="教员不存在")

    credit_map = await teacher_credit_map(db, [teacher_id])
    credit = credit_map.get(teacher_id, {})

    review_rows = (await db.execute(
        select(OrderReview, Order.grade_subject)
        .join(Order, Order.id == OrderReview.order_id)
        .where(OrderReview.teacher_id == teacher_id)
        .order_by(OrderReview.created_at.desc(), OrderReview.id.desc())
        .limit(20)
    )).all()

    review_count = await db.scalar(
        select(func.count()).select_from(OrderReview).where(OrderReview.teacher_id == teacher_id)
    )

    return ScorecardResponse(
        teacher_id=teacher_id,
        display_name=_masked_name(teacher.name),
        school=teacher.school,
        major=teacher.major,
        grade=teacher.grade,
        tags=_tags(teacher),
        completed_count=int(credit.get("completed_count", 0)),
        violation_count=int(credit.get("violation_count", 0)),
        avg_rating=credit.get("avg_rating"),
        review_count=int(review_count or 0),
        reviews=[
            ScorecardReview(
                rating=r.rating,
                comment=r.comment,
                grade_subject=subject,
                created_at=r.created_at,
            )
            for r, subject in review_rows
        ],
    )
