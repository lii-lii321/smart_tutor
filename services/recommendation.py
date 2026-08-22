from __future__ import annotations

import re
from collections import Counter
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.domain import Application, ApplicationStatus, Order, OrderStatus, Teacher, TeacherResume
from models.schemas import (
    RecommendedResumeSnapshot,
    TeacherOrderRecommendationItem,
    TeacherOrderRecommendationResponse,
)
from utils.geo import haversine_distance

SUBJECT_ALIASES: dict[str, tuple[str, ...]] = {
    "数学": ("数学", "奥数", "代数", "几何", "函数", "微积分"),
    "英语": ("英语", "英文", "口语", "阅读", "写作"),
    "语文": ("语文", "作文", "阅读理解", "写作"),
    "物理": ("物理", "力学", "电学", "实验"),
    "化学": ("化学", "实验", "分子", "有机"),
    "生物": ("生物", "细胞", "遗传"),
    "历史": ("历史", "文史"),
    "地理": ("地理", "区域", "地图"),
    "政治": ("政治", "思政", "道法"),
}

GRADE_ALIASES: dict[str, tuple[str, ...]] = {
    "小学": ("小学", "小一", "小二", "小三", "小四", "小五", "小六"),
    "初中": ("初中", "初一", "初二", "初三"),
    "高中": ("高中", "高一", "高二", "高三"),
}


def normalize_text(value: str | None) -> str:
    return (value or "").replace(" ", "").replace("\n", "").lower()


def extract_subject(text: str | None) -> str:
    normalized = normalize_text(text)
    for subject, aliases in SUBJECT_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return subject
    return ""


def extract_grade(text: str | None) -> str:
    normalized = normalize_text(text)
    for grade, aliases in GRADE_ALIASES.items():
        if any(alias in normalized for alias in aliases):
            return grade
    return ""


def parse_expected_rate(value: str | None) -> float | None:
    if not value:
        return None
    numbers = [float(item) for item in re.findall(r"\d+(?:\.\d+)?", value)]
    if not numbers:
        return None
    if len(numbers) == 1:
        return numbers[0]
    return sum(numbers[:2]) / 2


def _clamp_score(value: float) -> int:
    return max(0, min(100, int(round(value))))


def score_distance(teacher: Teacher, order: Order) -> tuple[int, float | None, str]:
    if teacher.lng is None or teacher.lat is None or order.lng is None or order.lat is None:
        return 60, None, "位置未完善，距离分按中性处理"

    distance_m = float(
        haversine_distance(float(teacher.lng), float(teacher.lat), float(order.lng), float(order.lat))
    )
    if distance_m <= 1500:
        score = 100
    elif distance_m <= 3000:
        score = 92
    elif distance_m <= 6000:
        score = 84
    elif distance_m <= 10000:
        score = 72
    elif distance_m <= 20000:
        score = 58
    else:
        score = 42
    return score, round(distance_m / 1000, 2), f"距离约 {distance_m / 1000:.1f} km"


def score_subject(order_subject: str, resume_text: str) -> tuple[int, str]:
    if not order_subject:
        return 62, "订单科目信息不够明确"
    normalized = normalize_text(resume_text)
    aliases = SUBJECT_ALIASES.get(order_subject, (order_subject,))
    if any(alias in normalized for alias in aliases):
        return 100, f"科目匹配：{order_subject}"
    if order_subject in normalized:
        return 95, f"科目匹配：{order_subject}"
    return 38, f"科目相关度一般：{order_subject}"


def score_grade(order_grade: str, resume_text: str) -> tuple[int, str]:
    if not order_grade:
        return 60, "订单年级信息不够明确"
    normalized = normalize_text(resume_text)
    aliases = GRADE_ALIASES.get(order_grade, (order_grade,))
    if any(alias in normalized for alias in aliases):
        return 100, f"年级匹配：{order_grade}"
    if order_grade.startswith("高") and any(alias in normalized for alias in GRADE_ALIASES["高中"]):
        return 88, f"年级匹配：{order_grade}"
    if order_grade.startswith("初") and any(alias in normalized for alias in GRADE_ALIASES["初中"]):
        return 88, f"年级匹配：{order_grade}"
    if order_grade.startswith("小") and any(alias in normalized for alias in GRADE_ALIASES["小学"]):
        return 88, f"年级匹配：{order_grade}"
    return 40, f"年级相关度一般：{order_grade}"


def score_school(teacher: Teacher) -> tuple[int, str]:
    if teacher.is_double_first_class and teacher.is_985 and teacher.is_211:
        return 100, "院校背景：985/211 + 双一流"
    if teacher.is_985 and teacher.is_211:
        return 98, "院校背景：985/211"
    if teacher.is_985:
        return 92, "院校背景：985"
    if teacher.is_211:
        return 86, "院校背景：211"
    if teacher.is_double_first_class:
        return 88, "院校背景：双一流"
    if teacher.is_985_211:
        return 95, "院校背景：985/211"
    return 66, f"院校背景：{teacher.school}"


def score_price(order: Order, expected_rate: float | None) -> tuple[int, str]:
    order_price = float(order.base_price)
    if order_price <= 0 or expected_rate is None:
        return 60, "课酬信息不足，价格分按中性处理"

    gap = abs(order_price - expected_rate) / max(expected_rate, 1.0)
    if gap <= 0.1:
        score = 100
    elif gap <= 0.2:
        score = 88
    elif gap <= 0.35:
        score = 76
    elif gap <= 0.5:
        score = 62
    else:
        score = 46
    return score, f"课酬接近期望：¥{order_price:.0f} vs ¥{expected_rate:.0f}"


def score_history(status_counts: Counter[ApplicationStatus]) -> tuple[int, str]:
    total = sum(status_counts.values())
    if total <= 0:
        return 55, "历史投递较少，先看基础匹配"

    positive = (
        status_counts[ApplicationStatus.shortlisted] * 4
        + status_counts[ApplicationStatus.deposit_paid] * 7
        + status_counts[ApplicationStatus.balance_paid] * 10
    )
    negative = status_counts[ApplicationStatus.rejected] * 3 + status_counts[ApplicationStatus.refunded] * 2
    score = _clamp_score(55 + positive - negative + min(15, total * 2))
    return score, f"历史投递 {total} 次，试课/成交 {status_counts[ApplicationStatus.balance_paid]} 次"


def _resume_text(resume: TeacherResume | dict[str, str | None]) -> str:
    if isinstance(resume, TeacherResume):
        parts = [resume.title, resume.teaching_subjects, resume.teaching_grades, resume.experience, resume.strengths]
    else:
        parts = [
            resume.get("title"),
            resume.get("teaching_subjects"),
            resume.get("teaching_grades"),
            resume.get("experience"),
            resume.get("strengths"),
        ]
    return normalize_text("".join(part or "" for part in parts))


def _fallback_resume(teacher: Teacher) -> dict[str, str | None]:
    base = teacher.highlights or teacher.major or teacher.school or ""
    return {
        "title": "教员基础画像",
        "teaching_subjects": base,
        "teaching_grades": teacher.grade or "",
        "experience": base,
        "strengths": base,
        "availability": None,
        "expected_rate": None,
        "is_default": True,
    }


async def build_teacher_recommendations(
    db: AsyncSession,
    teacher_id: int,
    tenant_id: int,
    limit: int = 20,
) -> list[TeacherOrderRecommendationItem]:
    teacher_result = await db.execute(select(Teacher).where(Teacher.id == teacher_id))
    teacher = teacher_result.scalar_one_or_none()
    if not teacher:
        return []

    resumes_result = await db.execute(
        select(TeacherResume)
        .where(TeacherResume.teacher_id == teacher_id)
        .order_by(TeacherResume.is_default.desc(), TeacherResume.created_at.desc())
    )
    actual_resumes = list(resumes_result.scalars().all())
    resume_candidates: list[TeacherResume | dict[str, str | None]] = actual_resumes or [_fallback_resume(teacher)]

    history_result = await db.execute(
        select(Application.status, func.count(Application.id))
        .where(Application.teacher_id == teacher_id)
        .group_by(Application.status)
    )
    status_counts = Counter({status: count for status, count in history_result.all()})

    application_result = await db.execute(
        select(Application.order_id, Application.id, Application.status).where(Application.teacher_id == teacher_id)
    )
    applications = {
        row.order_id: {"application_id": row.id, "status": row.status}
        for row in application_result.all()
    }

    now = datetime.utcnow()
    order_result = await db.execute(
        select(Order)
        .where(
            Order.tenant_id == tenant_id,
            Order.status == OrderStatus.recruiting,
            Order.expired_at > now,
        )
        .order_by(Order.created_at.desc())
    )
    orders = order_result.scalars().all()

    items: list[TeacherOrderRecommendationItem] = []
    for order in orders:
        order_subject = extract_subject(f"{order.grade_subject} {order.requirements} {order.raw_text}")
        order_grade = extract_grade(f"{order.grade_subject} {order.requirements} {order.raw_text}")

        distance_score, distance_km, distance_reason = score_distance(teacher, order)
        school_score, school_reason = score_school(teacher)
        history_score, history_reason = score_history(status_counts)

        best_resume: TeacherResume | None = None
        best_resume_payload: RecommendedResumeSnapshot | None = None
        best_subject_score = 0
        best_grade_score = 0
        best_price_score = 0
        best_fit = -1.0
        matched_subject_reason = ""
        matched_grade_reason = ""
        price_reason = ""

        for candidate in resume_candidates:
            if isinstance(candidate, TeacherResume):
                resume_text = _resume_text(candidate)
                expected_rate = parse_expected_rate(candidate.expected_rate)
                snapshot = RecommendedResumeSnapshot.model_validate(candidate)
                source_resume = candidate
            else:
                resume_text = _resume_text(candidate)
                expected_rate = parse_expected_rate(candidate.get("expected_rate"))
                snapshot = None
                source_resume = None

            subject_score, subject_reason = score_subject(order_subject, resume_text)
            grade_score, grade_reason = score_grade(order_grade, resume_text)
            price_score, current_price_reason = score_price(order, expected_rate)
            fit = subject_score * 0.45 + grade_score * 0.35 + price_score * 0.2

            if fit > best_fit:
                best_fit = fit
                best_subject_score = subject_score
                best_grade_score = grade_score
                best_price_score = price_score
                matched_subject_reason = subject_reason
                matched_grade_reason = grade_reason
                price_reason = current_price_reason
                best_resume = source_resume
                best_resume_payload = snapshot

        total_score = _clamp_score(
            distance_score * 0.20
            + best_subject_score * 0.22
            + best_grade_score * 0.16
            + school_score * 0.15
            + best_price_score * 0.12
            + history_score * 0.15
        )

        reasons = [distance_reason, matched_subject_reason, matched_grade_reason, school_reason, price_reason, history_reason]
        reasons = [item for item in reasons if item][:4]
        application = applications.get(order.id)

        items.append(
            TeacherOrderRecommendationItem.model_validate(
                {
                    "id": order.id,
                    "raw_id": order.raw_id,
                    "grade_subject": order.grade_subject,
                    "price_total": order.price_total,
                    "base_price": float(order.base_price),
                    "weekly_frequency": order.weekly_frequency,
                    "fuzzy_address": order.fuzzy_address,
                    "subway_remark": order.subway_remark,
                    "lng": float(order.lng),
                    "lat": float(order.lat),
                    "calculated_info_fee": float(order.calculated_info_fee),
                    "deposit_amount": float(order.deposit_amount),
                    "balance_amount": float(order.balance_amount),
                    "needs_manual_price": float(order.base_price) <= 0,
                    "created_at": order.created_at,
                    "status": order.status,
                    "total_score": total_score,
                    "score_breakdown": {
                        "distance": distance_score,
                        "subject": best_subject_score,
                        "grade": best_grade_score,
                        "school": school_score,
                        "price": best_price_score,
                        "history": history_score,
                    },
                    "reasons": reasons,
                    "distance_km": distance_km,
                    "already_applied": application is not None,
                    "application_id": application["application_id"] if application else None,
                    "application_status": application["status"] if application else None,
                    "matched_subject": order_subject or None,
                    "matched_grade": order_grade or None,
                    "best_resume": best_resume_payload,
                }
            )
        )

    items.sort(key=lambda item: (-item.total_score, -item.created_at.timestamp()))
    return items[: max(1, min(limit, 50))]


async def build_teacher_recommendation_response(
    db: AsyncSession,
    teacher_id: int,
    tenant_id: int,
    tenant_name: str,
    invite_code: str,
    limit: int = 20,
) -> TeacherOrderRecommendationResponse:
    items = await build_teacher_recommendations(db, teacher_id, tenant_id, limit=limit)
    return TeacherOrderRecommendationResponse(
        tenant_name=tenant_name,
        invite_code=invite_code,
        count=len(items),
        items=items,
    )
