"""
订单找教员（一期）：中介对滞留订单主动邀约教员。

把教员侧推荐引擎的评分反过来用：对给定订单给全平台教员打分
（科目匹配 > 年级匹配 > 距离 > 信用），返回 Top N；
中介点"邀约"后向教员发站内通知，教员点通知直达订单投递。
邀约内容只含科目/区域/课酬，不暴露家长联系方式。
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import TokenPayload, assert_tenant_scope, require_role
from models.domain import (
    Application,
    Notification,
    Order,
    OrderStatus,
    Teacher,
    TeacherResume,
    TenantTeacherBlacklist,
)
from models.schemas import InviteTeacherRequest, RecommendedTeacherItem
from services.credit import teacher_credit_map
from services.recommendation import (
    extract_grade,
    extract_subjects,
    normalize_text,
    score_distance,
    score_grade,
    score_subjects,
)
from utils.clock import utcnow

router = APIRouter(prefix="/api/v1/orders", tags=["订单找教员"])


async def _get_tenant_order(order_id: int, payload: TokenPayload, db: AsyncSession) -> Order:
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    assert_tenant_scope(payload, order.tenant_id, detail="订单不存在")
    return order


async def _matchable_teachers(db: AsyncSession, order: Order, tenant_id: int) -> list[tuple[Teacher, str]]:
    """参与匹配的教员及其简历文本：排除封禁、已被本租户拉黑、已投递过本单的教员。"""
    # 按 id 排序保证候选池确定：无 ORDER BY 时 MySQL 返回顺序不定，
    # 同一订单两次调用的 Top-N 可能不同（中介视角"推荐结果每次都不一样"）
    teachers = (await db.execute(
        select(Teacher).where(Teacher.is_banned.is_(False)).order_by(Teacher.id).limit(500)
    )).scalars().all()

    applied_ids = set((await db.execute(
        select(Application.teacher_id).where(Application.order_id == order.id)
    )).scalars().all())
    blacklisted_ids = set((await db.execute(
        select(TenantTeacherBlacklist.teacher_id).where(
            TenantTeacherBlacklist.tenant_id == tenant_id,
            TenantTeacherBlacklist.teacher_id.in_([t.id for t in teachers] or [0]),
        )
    )).scalars().all())

    default_resumes = (await db.execute(
        select(TeacherResume)
        .order_by(TeacherResume.is_default.desc(), TeacherResume.created_at.desc(), TeacherResume.id.desc())
        .limit(2000)
    )).scalars().all()
    resume_by_teacher: dict[int, str] = {}
    for resume in default_resumes:
        text = normalize_text("".join(filter(None, [
            resume.title, resume.teaching_subjects, resume.teaching_grades,
            resume.experience, resume.strengths,
        ])))
        # 排序保证默认简历在前:每名教员只取第一条(缺默认简历时退化为最新一份)
        resume_by_teacher.setdefault(resume.teacher_id, text)

    result: list[tuple[Teacher, str]] = []
    for teacher in teachers:
        if teacher.id in applied_ids or teacher.id in blacklisted_ids:
            continue
        result.append((teacher, resume_by_teacher.get(teacher.id, "")))
    return result


@router.get("/{order_id}/recommended-teachers", response_model=list[RecommendedTeacherItem])
async def recommended_teachers(
    order_id: int,
    limit: int = Query(10, ge=1, le=20),
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """为招聘中订单推荐匹配教员（评分：科目 .45 / 年级 .2 / 距离 .15 / 信用 .2）。"""
    order = await _get_tenant_order(order_id, payload, db)
    if order.status != OrderStatus.recruiting:
        raise HTTPException(status_code=400, detail="仅招聘中的订单可以匹配教员")

    subject_pool = extract_subjects(f"{order.grade_subject} {order.requirements} {order.raw_text}")
    order_grade = extract_grade(f"{order.grade_subject} {order.requirements} {order.raw_text}")
    candidates = await _matchable_teachers(db, order, order.tenant_id)
    credit = await teacher_credit_map(db, [t.id for t, _ in candidates])

    items: list[RecommendedTeacherItem] = []
    for teacher, resume_text in candidates:
        subject_score, _ = score_subjects(subject_pool, resume_text)
        grade_score, _ = score_grade(order_grade, resume_text)
        distance_score, distance_km, _ = score_distance(teacher, order)
        stats = credit.get(teacher.id, {})
        completed = int(stats.get("completed_count", 0))
        violations = int(stats.get("violation_count", 0))
        credit_score = max(0, min(100, completed * 20 - violations * 30))
        total = round(
            subject_score * 0.45 + grade_score * 0.2 + distance_score * 0.15 + credit_score * 0.2, 1
        )
        items.append(RecommendedTeacherItem(
            teacher_id=teacher.id,
            name=teacher.name,
            school=teacher.school,
            major=teacher.major,
            grade=teacher.grade,
            home_area=teacher.home_area,
            completed_count=completed,
            violation_count=violations,
            avg_rating=stats.get("avg_rating"),
            distance_km=round(distance_km, 1) if distance_km is not None else None,
            subject_matched=subject_score > 0,
            total_score=total,
        ))

    items.sort(key=lambda item: (-item.total_score, item.teacher_id))
    return items[:limit]


@router.post("/{order_id}/invite-teacher")
async def invite_teacher(
    order_id: int,
    body: InviteTeacherRequest,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """邀约教员投递指定订单：发站内通知（72 小时内同一订单不重复邀约同一教员）。"""
    order = await _get_tenant_order(order_id, payload, db)
    if order.status != OrderStatus.recruiting:
        raise HTTPException(status_code=400, detail="订单已不在招聘中，无法邀约")
    if order.expired_at and order.expired_at <= utcnow():
        raise HTTPException(status_code=400, detail="订单已过期，请先重新发布刷新有效期")

    teacher = await db.get(Teacher, body.teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="教员不存在")
    if teacher.is_banned:
        raise HTTPException(status_code=400, detail="该教员已被平台限制，无法邀约")

    blacklisted = await db.scalar(
        select(TenantTeacherBlacklist.id).where(
            TenantTeacherBlacklist.tenant_id == order.tenant_id,
            TenantTeacherBlacklist.teacher_id == teacher.id,
        )
    )
    if blacklisted:
        raise HTTPException(status_code=400, detail="该教员已被拉黑，无法邀约")

    applied = await db.scalar(
        select(Application.id).where(
            Application.order_id == order.id,
            Application.teacher_id == teacher.id,
        )
    )
    if applied:
        raise HTTPException(status_code=409, detail="该教员已投递过本单，无需重复邀约")

    dup = await db.scalar(
        select(Notification.id).where(
            Notification.teacher_id == teacher.id,
            Notification.order_id == order.id,
            Notification.title == "订单邀约",
            Notification.deleted_at.is_(None),
            Notification.created_at >= utcnow() - datetime.timedelta(hours=72),
        )
    )
    if dup:
        raise HTTPException(status_code=409, detail="72 小时内已邀约过该教员，请耐心等待响应")

    db.add(Notification(
        teacher_id=teacher.id,
        title="订单邀约",
        content=(
            f"「{order.grade_subject}」收到订单邀约：{order.fuzzy_address} · "
            f"{order.price_total}。感兴趣请尽快投递。"
        ),
        order_id=order.id,
    ))
    await db.flush()
    return {"detail": "已向教员发送订单邀约"}
