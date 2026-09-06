"""
投递路由：教员投递简历 + 状态变更。
"""
import datetime
import re
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from database import get_db
from config import settings
from services.calculator import calculate_info_fee, calculate_refund
from models.domain import (
    Application, ApplicationStatus, FinancialRecord, FinancialType,
    Order, OrderStatus, Teacher, TeacherResume, Tenant,
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


# 年级等级表：用于解析简历中的年级范围（如 "初二-高三"）
_GRADE_LEVELS = {
    "小学": 0, "小一": 1, "小二": 2, "小三": 3, "小四": 4, "小五": 5, "小六": 6,
    "初一": 7, "初二": 8, "初三": 9, "初中": 8,
    "高一": 10, "高二": 11, "高三": 12, "高中": 11,
}


def _is_grade_compatible(order_grade: str, resume_text: str) -> bool:
    if not order_grade:
        return True
    if order_grade in resume_text:
        return True
    if order_grade.startswith("高") and "高中" in resume_text:
        return True
    if order_grade.startswith("初") and "初中" in resume_text:
        return True
    # 简历以范围表述（如 "初二-高三"）时按区间判断是否覆盖订单年级
    order_level = _GRADE_LEVELS.get(order_grade)
    if order_level is not None:
        for m in re.finditer(r"([高一高二高三初中小学小一二三四五六]{2})\s*[-—~至]\s*([高一高二高三初中小学小一二三四五六]{2})", resume_text):
            lo = _GRADE_LEVELS.get(m.group(1))
            hi = _GRADE_LEVELS.get(m.group(2))
            if lo is not None and hi is not None and lo <= order_level <= hi:
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
    order = getattr(application, "order", None)
    tenant = getattr(application, "tenant", None)
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
            "raw_order_id": getattr(order, "raw_id", None),
            "teacher_id": application.teacher_id,
            "tenant_id": application.tenant_id,
            "tenant_name": getattr(tenant, "tenant_name", None),
            "order_grade_subject": getattr(order, "grade_subject", None),
            "order_price_total": getattr(order, "price_total", None),
            "order_fuzzy_address": getattr(order, "fuzzy_address", None),
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
        .options(
            selectinload(Application.teacher),
            selectinload(Application.resume),
            selectinload(Application.order),
            selectinload(Application.tenant),
        )
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


def _application_fee(order: Order, application: Application) -> dict:
    """
    该投递适用的费用基准：
    - 自带价订单按教员报价精算（order 级字段保持 0，不互相覆盖）；
    - 其余用订单级精算结果。
    """
    if application.proposed_price and float(application.proposed_price) > 0:
        return calculate_info_fee(
            base_price=float(application.proposed_price),
            weekly_frequency=order.weekly_frequency,
            is_summer_vacation=order.is_summer_vacation,
        )
    return {
        "total_info_fee": float(order.calculated_info_fee),
        "deposit": float(order.deposit_amount),
        "balance": float(order.balance_amount),
    }


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
    # 自带价订单：报价仅记录在投递上，不回写订单级价格，避免后投教员覆盖先投教员的费用基准。
    # 此处提前精算校验报价合法（过低会抛 ValueError），实际费用在定金/尾款确认时按投递计算。
    if float(order.base_price) <= 0 and proposed_price:
        try:
            calculate_info_fee(
                base_price=proposed_price,
                weekly_frequency=order.weekly_frequency,
                is_summer_vacation=order.is_summer_vacation,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))

    db.add(application)
    await db.flush()
    application.teacher = await db.get(Teacher, payload.teacher_id)
    application.resume = resume
    application.order = order
    application.tenant = await db.get(Tenant, order.tenant_id)
    return _build_application_response(application)


@router.get("/summary")
async def application_summary(
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """返回当前需要中介处理的待审核投递总数和按订单聚合数量。"""
    query = (
        select(Application.order_id, func.count(Application.id))
        .join(Order, Order.id == Application.order_id)
        .where(Application.status == ApplicationStatus.pending)
        .where(Order.status.in_((OrderStatus.recruiting, OrderStatus.trial_in_progress)))
        .where((Order.status != OrderStatus.recruiting) | (Order.expired_at > datetime.datetime.utcnow()))
    )
    if payload.role != "super_admin" and payload.tenant_id is not None:
        query = query.where(Application.tenant_id == payload.tenant_id)
    query = query.group_by(Application.order_id)

    result = await db.execute(query)
    order_counts = {order_id: int(count) for order_id, count in result.all()}
    total_applications = sum(order_counts.values())
    return {"total_applications": total_applications, "order_counts": order_counts}


@router.get("/mine", response_model=list[ApplicationResponse])
async def list_my_applications(
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """查看我的投递记录。"""
    result = await db.execute(
        select(Application)
        .options(
            selectinload(Application.teacher),
            selectinload(Application.resume),
            selectinload(Application.order),
            selectinload(Application.tenant),
        )
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
        .options(
            selectinload(Application.teacher),
            selectinload(Application.resume),
            selectinload(Application.order),
            selectinload(Application.tenant),
        )
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
        .options(
            selectinload(Application.teacher),
            selectinload(Application.resume),
            selectinload(Application.order),
            selectinload(Application.tenant),
        )
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

    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/reject", response_model=ApplicationResponse)
async def reject_application(
    application_id: int,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：拒绝待审核/候选队列中的投递，落选教员不再挂在待处理列表。"""
    application = await _get_managed_application(application_id, payload, db)
    if application.status not in (
        ApplicationStatus.pending,
        ApplicationStatus.shortlisted,
    ):
        raise HTTPException(status_code=400, detail="仅待审核或候选状态的投递可拒绝")

    application.status = ApplicationStatus.rejected
    application.rejected_at = datetime.datetime.utcnow()
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
        .options(
            selectinload(Application.teacher),
            selectinload(Application.resume),
            selectinload(Application.order),
            selectinload(Application.tenant),
        )
        .where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    if payload.role != "super_admin" and application.tenant_id != payload.tenant_id:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    if application.status != ApplicationStatus.deposit_paid:
        raise HTTPException(status_code=400, detail="必须先支付定金才能开始试课，防止教员绕过中介获取家长联系方式")

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
    # 订单保持 recruiting（候选已付定金，等待开始试课）；自带价订单按投递报价精算
    fee = _application_fee(order, application)
    _add_financial_record(
        db,
        application,
        fee["deposit"],
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
    if application.status != ApplicationStatus.trial_in_progress:
        raise HTTPException(status_code=400, detail="仅试课中的教员可确认尾款")

    order = await db.get(Order, application.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    application.status = ApplicationStatus.balance_paid
    application.balance_paid_at = datetime.datetime.utcnow()
    order.selected_teacher_id = application.teacher_id
    # 订单保持 trial_in_progress，直到中介确认完成（complete）
    fee = _application_fee(order, application)
    _add_financial_record(
        db,
        application,
        fee["balance"],
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
    # 投递进入终态，避免卡片停留在"尾款已付"导致重复点击确认完成
    application.status = ApplicationStatus.completed
    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/trial-failed", response_model=ApplicationResponse)
async def trial_failed(
    application_id: int,
    refund_amount: float = 0,
    trial_paid_by_parent: float = 0,
    is_teacher_violated: bool = False,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    B 端：试课失败，重新开放订单。

    退费规则：
    - 教员违约（is_teacher_violated=true）：没收已交信息费，不退款；
    - 正常失败：按精算公式 退费 = max(0, 已交信息费 − 家长支付试课酬 × 70%)；
    - 兼容旧调用：显式传 refund_amount 时以其为准。
    """
    if refund_amount < 0 or trial_paid_by_parent < 0:
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
    fee = _application_fee(order, application)
    paid_amount = fee["deposit"] + (
        fee["balance"] if application.status == ApplicationStatus.balance_paid else 0
    )

    if is_teacher_violated:
        # 教员违约：没收已交信息费（定金 + 已付尾款）
        _add_financial_record(
            db, application, paid_amount, FinancialType.forfeit, "教员违约，没收信息费"
        )
        application.status = ApplicationStatus.rejected
        application.rejected_at = now
    else:
        if trial_paid_by_parent > 0:
            refund = calculate_refund(
                total_info_fee_paid=paid_amount,
                trial_paid_by_parent=trial_paid_by_parent,
                is_trial_success=False,
                is_teacher_violated=False,
            )
        else:
            refund = max(0.0, round(refund_amount, 2))

        if refund > 0:
            application.status = ApplicationStatus.refunded
            application.refunded_at = now
            _add_financial_record(
                db, application, refund, FinancialType.refund_out, "试课失败退款"
            )
        else:
            application.status = ApplicationStatus.rejected
            application.rejected_at = now

    order.selected_teacher_id = None
    order.status = OrderStatus.recruiting
    order.expired_at = now + datetime.timedelta(hours=settings.ORDER_EXPIRE_HOURS)

    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/forfeit", response_model=ApplicationResponse)
async def forfeit_deposit(
    application_id: int,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：教员违约，没收已交信息费（定金/尾款），订单重新开放招聘。"""
    application = await _get_managed_application(application_id, payload, db)
    if application.status not in (
        ApplicationStatus.deposit_paid,
        ApplicationStatus.trial_in_progress,
        ApplicationStatus.balance_paid,
    ):
        raise HTTPException(status_code=400, detail="仅已付定金/试课中/尾款已付的投递可没收定金")

    order = await db.get(Order, application.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    now = datetime.datetime.utcnow()
    fee = _application_fee(order, application)
    forfeited = fee["deposit"] + (
        fee["balance"] if application.status == ApplicationStatus.balance_paid else 0
    )
    _add_financial_record(
        db, application, forfeited, FinancialType.forfeit, "教员违约，没收信息费"
    )

    application.status = ApplicationStatus.rejected
    application.rejected_at = now
    order.selected_teacher_id = None
    order.status = OrderStatus.recruiting
    order.expired_at = now + datetime.timedelta(hours=settings.ORDER_EXPIRE_HOURS)

    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/cancel", response_model=ApplicationResponse)
async def cancel_application(
    application_id: int,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """
    C 端：教员取消投递。
    - 未付定金（pending/shortlisted）：直接取消；
    - 已付定金（deposit_paid）：退还定金并重新开放订单；
    - 试课中/尾款已付：不可自助取消，需联系中介（走试课失败流程）。
    """
    result = await db.execute(
        select(Application)
        .options(
            selectinload(Application.teacher),
            selectinload(Application.resume),
            selectinload(Application.order),
            selectinload(Application.tenant),
        )
        .where(Application.id == application_id)
    )
    application = result.scalar_one_or_none()
    if not application or application.teacher_id != payload.teacher_id:
        raise HTTPException(status_code=404, detail="投递记录不存在")

    if application.status not in (
        ApplicationStatus.pending,
        ApplicationStatus.shortlisted,
        ApplicationStatus.deposit_paid,
    ):
        raise HTTPException(status_code=400, detail="当前状态不可自助取消，请联系中介处理")

    order = await db.get(Order, application.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    now = datetime.datetime.utcnow()

    if application.status == ApplicationStatus.deposit_paid:
        fee = _application_fee(order, application)
        _add_financial_record(
            db, application, fee["deposit"], FinancialType.refund_out, "教员取消投递，退还定金"
        )
        application.status = ApplicationStatus.refunded
        application.refunded_at = now
    else:
        application.status = ApplicationStatus.rejected
        application.rejected_at = now

    # 订单若因此失去候选/已付定金教员，重新开放招聘
    if order.status == OrderStatus.recruiting:
        order.selected_teacher_id = None
        order.expired_at = now + datetime.timedelta(hours=settings.ORDER_EXPIRE_HOURS)

    await db.flush()
    return _build_application_response(application)
