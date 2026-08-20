"""
投递路由：教员投递简历 + 状态变更。
"""
import datetime
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from database import get_db
from config import settings
from services.calculator import calculate_info_fee
from models.domain import (
    Application, ApplicationStatus, FinancialRecord, FinancialType,
    Order, OrderStatus, Teacher, TeacherResume,
)
from models.schemas import ApplicationResponse
from middleware.auth import TokenPayload, get_current_user, require_role

router = APIRouter(prefix="/api/v1/applications", tags=["投递"])


def _normalize_text(value: str | None) -> str:
    return (value or "").replace(" ", "").replace("\n", "").lower()


def _extract_grade(order: Order) -> str:
    text = _normalize_text(f"{order.grade_subject}{order.requirements}{order.raw_text}")
    for token in ("高三", "高二", "高一", "高中", "初三", "初二", "初一", "初中", "小学"):
        if token in text:
            return token
    return ""


def _extract_subject(order: Order) -> str:
    text = _normalize_text(f"{order.grade_subject}{order.requirements}{order.raw_text}")
    for token in ("英语", "数学", "物理", "化学", "语文", "生物", "历史", "地理", "政治"):
        if token in text:
            return token
    return ""


def _is_grade_compatible(order_grade: str, resume_text: str) -> bool:
    if not order_grade:
        return True
    if order_grade in resume_text:
        return True
    if order_grade.startswith("高") and "高中" in resume_text:
        return True
    if order_grade.startswith("初") and "初中" in resume_text:
        return True
    return False


def _validate_resume_fit(order: Order, resume: TeacherResume) -> None:
    order_grade = _extract_grade(order)
    order_subject = _extract_subject(order)
    resume_grade_text = _normalize_text(
        f"{resume.title}{resume.teaching_grades}{resume.experience}{resume.strengths}"
    )
    resume_subject_text = _normalize_text(
        f"{resume.title}{resume.teaching_subjects}{resume.experience}{resume.strengths}"
    )
    reasons = []

    if order_subject and order_subject not in resume_subject_text:
        reasons.append(f"订单要求「{order_subject}」，所选简历未体现可授该科目")
    if not _is_grade_compatible(order_grade, resume_grade_text):
        reasons.append(f"订单年级为「{order_grade}」，所选简历未体现匹配年级")

    if reasons:
        raise HTTPException(status_code=422, detail="；".join(reasons))


def _build_application_response(application: Application) -> ApplicationResponse:
    teacher = getattr(application, "teacher", None)
    teacher_payload = None
    if teacher is not None:
        teacher_payload = {
            "id": teacher.id,
            "name": teacher.name,
            "gender": teacher.gender,
            "school": teacher.school,
            "is_985_211": teacher.is_985_211,
            "is_985": teacher.is_985,
            "is_211": teacher.is_211,
            "is_double_first_class": teacher.is_double_first_class,
            "major": teacher.major,
            "grade": teacher.grade,
            "highlights": teacher.highlights,
        }
    return ApplicationResponse.model_validate(
        {
            "id": application.id,
            "order_id": application.order_id,
            "teacher_id": application.teacher_id,
            "tenant_id": application.tenant_id,
            "resume_id": application.resume_id,
            "resume": getattr(application, "resume", None),
            "teacher": teacher_payload,
            "status": application.status,
            "proposed_price": application.proposed_price,
            "applied_at": application.applied_at,
            "shortlisted_at": application.shortlisted_at,
            "deposit_paid_at": application.deposit_paid_at,
            "balance_paid_at": application.balance_paid_at,
        }
    )


def _active_trial_statuses() -> tuple[ApplicationStatus, ...]:
    return (ApplicationStatus.trial_in_progress, ApplicationStatus.balance_paid)


async def _get_managed_application(
    application_id: int,
    payload: TokenPayload,
    db: AsyncSession,
) -> Application:
    result = await db.execute(
        select(Application)
        .options(selectinload(Application.teacher), selectinload(Application.resume))
        .where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    if payload.role != "super_admin" and application.tenant_id != payload.tenant_id:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    return application


def _add_financial_record(
    db: AsyncSession,
    application: Application,
    amount: float | Decimal,
    record_type: FinancialType,
    remark: str,
) -> None:
    db.add(
        FinancialRecord(
            order_id=application.order_id,
            tenant_id=application.tenant_id,
            teacher_id=application.teacher_id,
            amount=Decimal(str(amount)),
            type=record_type,
            remark=remark,
        )
    )


@router.post("/", response_model=ApplicationResponse)
async def apply_order(
    order_id: int,
    proposed_price: float | None = None,
    resume_id: int | None = None,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """教员投递简历到某个订单。自带价订单需传入 proposed_price。"""
    # 检查订单是否可投递
    order = await db.get(Order, order_id)
    if not order or order.status != OrderStatus.recruiting:
        raise HTTPException(status_code=400, detail="该订单已不可投递")
    if order.expired_at and order.expired_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="该订单已过期")

    # 自带价订单必须提供报价，并用报价生成后续费用基准。
    if float(order.base_price) <= 0 and (proposed_price is None or proposed_price <= 0):
        raise HTTPException(status_code=422, detail="该订单为自带价订单，请填写您的报价")

    if proposed_price is not None and proposed_price <= 0:
        raise HTTPException(status_code=422, detail="报价必须大于0")

    if resume_id is not None:
        resume = await db.get(TeacherResume, resume_id)
        if not resume or resume.teacher_id != payload.teacher_id:
            raise HTTPException(status_code=404, detail="简历不存在")
    else:
        result = await db.execute(
            select(TeacherResume)
            .where(TeacherResume.teacher_id == payload.teacher_id)
            .order_by(TeacherResume.is_default.desc(), TeacherResume.created_at.desc())
            .limit(1)
        )
        resume = result.scalar_one_or_none()
        if not resume:
            raise HTTPException(status_code=422, detail="请先在个人中心创建一份简历")
        resume_id = resume.id

    _validate_resume_fit(order, resume)

    # 检查是否已投递
    existing = await db.execute(
        select(Application).where(
            Application.order_id == order_id,
            Application.teacher_id == payload.teacher_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="您已投递过该订单")

    application = Application(
        order_id=order_id,
        teacher_id=payload.teacher_id,
        tenant_id=order.tenant_id,
        resume_id=resume_id,
        status=ApplicationStatus.pending,
        proposed_price=proposed_price,
    )
    if float(order.base_price) <= 0 and proposed_price:
        try:
            fee = calculate_info_fee(
                base_price=proposed_price,
                weekly_frequency=order.weekly_frequency,
                is_summer_vacation=order.is_summer_vacation,
            )
            order.base_price = proposed_price
            order.calculated_info_fee = fee["total_info_fee"]
            order.deposit_amount = fee["deposit"]
            order.balance_amount = fee["balance"]
            order.price_total = f"自带价 ¥{proposed_price}/次"
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    db.add(application)
    await db.flush()
    application.teacher = await db.get(Teacher, payload.teacher_id)
    application.resume = resume
    return _build_application_response(application)


@router.get("/mine", response_model=list[ApplicationResponse])
async def list_my_applications(
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """查看我的投递记录。"""
    result = await db.execute(
        select(Application)
        .options(selectinload(Application.teacher), selectinload(Application.resume))
        .where(Application.teacher_id == payload.teacher_id)
        .order_by(Application.applied_at.desc())
    )
    applications = result.scalars().all()
    return [_build_application_response(a) for a in applications]


@router.get("/order/{order_id}", response_model=list[ApplicationResponse])
async def list_order_applications(
    order_id: int,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：查看某订单的所有投递记录。"""
    # 租户隔离
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if payload.role != "super_admin" and order.tenant_id != payload.tenant_id:
        raise HTTPException(status_code=404, detail="订单不存在")

    result = await db.execute(
        select(Application)
        .options(selectinload(Application.teacher), selectinload(Application.resume))
        .where(Application.order_id == order_id)
        .order_by(Application.applied_at.desc())
    )
    applications = result.scalars().all()
    return [_build_application_response(a) for a in applications]


@router.post("/{application_id}/shortlist", response_model=ApplicationResponse)
async def shortlist_application(
    application_id: int,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：将教员加入候选队列（shortlisted）。"""
    result = await db.execute(
        select(Application)
        .options(selectinload(Application.teacher), selectinload(Application.resume))
        .where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    if payload.role != "super_admin" and application.tenant_id != payload.tenant_id:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    if application.status != ApplicationStatus.pending:
        raise HTTPException(status_code=400, detail="仅 pending 状态的投递可被选中")

    application.status = ApplicationStatus.shortlisted
    application.shortlisted_at = datetime.datetime.utcnow()

    # 有候选人后订单退出公开招聘，但不代表已经开始试课。
    order = await db.get(Order, application.order_id)
    if order and order.status == OrderStatus.recruiting:
        order.status = OrderStatus.pending_deposit
    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/start-trial", response_model=ApplicationResponse)
async def start_trial_application(
    application_id: int,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：从候选队列中选择一位教员开始试课，同一订单同时只允许一位。"""
    result = await db.execute(
        select(Application)
        .options(selectinload(Application.teacher), selectinload(Application.resume))
        .where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    if payload.role != "super_admin" and application.tenant_id != payload.tenant_id:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    if application.status not in (ApplicationStatus.shortlisted, ApplicationStatus.deposit_paid):
        raise HTTPException(status_code=400, detail="仅候选或已付定金的教员可开始试课")

    order = await db.get(Order, application.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if order.status == OrderStatus.trial_in_progress:
        raise HTTPException(status_code=409, detail="该订单已有教员正在试课，请先完成当前试课")

    result = await db.execute(
        select(Application).where(
            Application.order_id == application.order_id,
            Application.status.in_(_active_trial_statuses()),
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该订单已有教员正在试课")

    application.status = ApplicationStatus.trial_in_progress
    order.selected_teacher_id = application.teacher_id
    order.status = OrderStatus.trial_in_progress
    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/confirm-deposit", response_model=ApplicationResponse)
async def confirm_deposit(
    application_id: int,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：线下确认已收到教员定金，并生成财务流水。"""
    application = await _get_managed_application(application_id, payload, db)
    if application.status != ApplicationStatus.shortlisted:
        raise HTTPException(status_code=400, detail="仅候选队列中的教员可确认定金")

    order = await db.get(Order, application.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    application.status = ApplicationStatus.deposit_paid
    application.deposit_paid_at = datetime.datetime.utcnow()
    order.selected_teacher_id = application.teacher_id
    order.status = OrderStatus.pending_balance
    _add_financial_record(
        db,
        application,
        order.deposit_amount,
        FinancialType.deposit_in,
        "线下确认定金",
    )
    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/confirm-balance", response_model=ApplicationResponse)
async def confirm_balance(
    application_id: int,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：线下确认已收到尾款，并生成财务流水。"""
    application = await _get_managed_application(application_id, payload, db)
    if application.status not in (
        ApplicationStatus.deposit_paid,
        ApplicationStatus.trial_in_progress,
    ):
        raise HTTPException(status_code=400, detail="仅已付定金或试课中的教员可确认尾款")

    order = await db.get(Order, application.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    application.status = ApplicationStatus.balance_paid
    application.balance_paid_at = datetime.datetime.utcnow()
    order.selected_teacher_id = application.teacher_id
    order.status = OrderStatus.pending_balance
    _add_financial_record(
        db,
        application,
        order.balance_amount,
        FinancialType.balance_in,
        "线下确认尾款",
    )
    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/complete", response_model=ApplicationResponse)
async def complete_application(
    application_id: int,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：确认订单成交完成。"""
    application = await _get_managed_application(application_id, payload, db)
    if application.status != ApplicationStatus.balance_paid:
        raise HTTPException(status_code=400, detail="仅已补齐尾款的教员可完成订单")

    order = await db.get(Order, application.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    order.selected_teacher_id = application.teacher_id
    order.status = OrderStatus.completed
    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/trial-failed", response_model=ApplicationResponse)
async def trial_failed(
    application_id: int,
    refund_amount: float = 0,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：试课失败，记录退款并重新开放订单。"""
    if refund_amount < 0:
        raise HTTPException(status_code=422, detail="退款金额不能为负数")

    application = await _get_managed_application(application_id, payload, db)
    if application.status not in (
        ApplicationStatus.deposit_paid,
        ApplicationStatus.trial_in_progress,
        ApplicationStatus.balance_paid,
    ):
        raise HTTPException(status_code=400, detail="当前状态不能标记试课失败")

    order = await db.get(Order, application.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    now = datetime.datetime.utcnow()
    application.status = (
        ApplicationStatus.refunded if refund_amount > 0 else ApplicationStatus.rejected
    )
    application.refunded_at = now if refund_amount > 0 else None
    application.rejected_at = now if refund_amount <= 0 else None
    order.selected_teacher_id = None
    order.status = OrderStatus.recruiting
    order.expired_at = now + datetime.timedelta(hours=settings.ORDER_EXPIRE_HOURS)

    if refund_amount > 0:
        _add_financial_record(
            db,
            application,
            refund_amount,
            FinancialType.refund_out,
            "试课失败退款",
        )

    await db.flush()
    return _build_application_response(application)
