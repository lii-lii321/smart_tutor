"""
教员找单订阅：偏好查看与保存（一教员一份，PUT 整体覆盖）。

subjects/grades 存规范名（与推荐服务别名表同口径）：保存时逐项归一，
无法归一的项直接丢弃（前端选项即规范名，此处仅防御异常输入）。
"""

from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import TokenPayload, require_role
from models.domain import TeacherSubscription
from models.schemas import TeacherSubscriptionRequest, TeacherSubscriptionResponse
from services.recommendation import GRADE_ALIASES, SUBJECT_ALIASES, extract_subject

router = APIRouter(prefix="/api/v1/subscriptions", tags=["订阅"])


def _normalize_subjects(subjects: list[str]) -> list[str]:
    canonical: list[str] = []
    for raw in subjects:
        name = raw.strip()
        if not name:
            continue
        if name in SUBJECT_ALIASES:
            if name not in canonical:
                canonical.append(name)
            continue
        normalized = extract_subject(name)
        if normalized and normalized not in canonical:
            canonical.append(normalized)
    return canonical


def _normalize_grades(grades: list[str]) -> list[str]:
    canonical: list[str] = []
    for raw in grades:
        name = raw.strip()
        if name in GRADE_ALIASES and name not in canonical:
            canonical.append(name)
    return canonical


def _to_response(sub: TeacherSubscription | None) -> TeacherSubscriptionResponse:
    if sub is None:
        return TeacherSubscriptionResponse(enabled=True)
    return TeacherSubscriptionResponse(
        enabled=sub.enabled,
        subjects=[part for part in (sub.subjects or "").split(",") if part],
        grades=[part for part in (sub.grades or "").split(",") if part],
        min_base_price=float(sub.min_base_price) if sub.min_base_price is not None else None,
        updated_at=sub.updated_at,
    )


@router.get("/mine", response_model=TeacherSubscriptionResponse)
async def get_my_subscription(
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """教员查看自己的订阅偏好；未设置过时返回默认（开启+不限）。"""
    sub = await db.get(TeacherSubscription, payload.teacher_id)
    return _to_response(sub)


@router.put("/mine", response_model=TeacherSubscriptionResponse)
async def save_my_subscription(
    body: TeacherSubscriptionRequest,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """保存订阅偏好（整体覆盖）。关闭开关时仍保存条件，便于随时重新打开。"""
    sub = await db.get(TeacherSubscription, payload.teacher_id)
    if sub is None:
        sub = TeacherSubscription(teacher_id=payload.teacher_id)
        db.add(sub)
    sub.enabled = body.enabled
    sub.subjects = ",".join(_normalize_subjects(body.subjects)) or None
    sub.grades = ",".join(_normalize_grades(body.grades)) or None
    sub.min_base_price = (
        Decimal(str(body.min_base_price)) if body.min_base_price is not None else None
    )
    await db.commit()
    await db.refresh(sub)
    return _to_response(sub)
