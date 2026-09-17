"""
投递路由：教员投递简历 + 状态变更。
"""
import datetime
import re
from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import get_db
from middleware.auth import TokenPayload, assert_tenant_scope, require_role, tenant_scoped
from models.domain import (
    Application,
    ApplicationStatus,
    FinancialRecord,
    FinancialType,
    Notification,
    Order,
    OrderReview,
    OrderStatus,
    Teacher,
    TeacherResume,
    Tenant,
)
from models.schemas import (
    ApplicationResponse,
    ApplicationSummaryResponse,
    ApplyOrderRequest,
    OrderReviewResponse,
    ReviewCreateRequest,
    TrialFailedRequest,
)
from services.audit import (
    ACTION_CANCEL,
    ACTION_CONFIRM_BALANCE,
    ACTION_CONFIRM_DEPOSIT,
    ACTION_FORFEIT,
    ACTION_TRIAL_FAILED,
    record_audit,
)
from services.calculator import calculate_info_fee, calculate_refund
from services.credit import teacher_credit_map
from services.order_maintenance import refresh_order_expiry

router = APIRouter(prefix="/api/v1/applications", tags=["投递"])

# B008：FastAPI body 默认值需模块级单例（模型只读使用，不修改）
_TRIAL_FAILED_DEFAULT = TrialFailedRequest()


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


def _fee_preview(application: Application) -> dict | None:
    """费用基准单点下发（P1-3）：定金确认后是快照口径，前端不复算费率。"""
    order = getattr(application, "order", None)
    if order is None:
        return None
    fee = _fee_locked(order, application)
    return {
        "total_info_fee": float(fee["total_info_fee"]),
        "deposit": float(fee["deposit"]),
        "balance": float(fee["balance"]),
    }


def _build_application_response(
    application: Application,
    credit_map: dict[int, dict] | None = None,
) -> ApplicationResponse:
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
            # 教员只收到自己的联系方式；B 端靠它与教员线下沟通收定金
            "phone": teacher.phone,
            "wechat_id": teacher.wechat_id,
        }
        if credit_map and teacher.id in credit_map:
            teacher_payload.update(credit_map[teacher.id])
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
            "fee": _fee_preview(application),
        }
    )


def _active_trial_statuses() -> tuple[ApplicationStatus, ...]:
    return (ApplicationStatus.trial_in_progress, ApplicationStatus.balance_paid)


async def _get_order_for_update(db: AsyncSession, order_id: int) -> Order:
    """
    改写订单状态/生成资金流水前先锁定订单行，串行化同一订单的并发操作
    （如双管理员同时开试课）。SQLite 忽略 FOR UPDATE，MySQL 下生效。
    """
    result = await db.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order


async def _get_managed_application(
    application_id: int,
    payload: TokenPayload,
    db: AsyncSession,
) -> Application:
    """
    资金/状态端点的统一取数入口，锁序全局固定为 order → application：
    先普通读定位 order_id 并做租户校验，锁订单行后再锁投递行。
    订单侧路径（状态流转/重开招聘/批量操作）都是先持订单锁再动投递行；
    若这里先锁 application 再锁 order，两个方向并发即成环
    （InnoDB 1213 死锁，资金接口随机 500）。SQLite 忽略 FOR UPDATE，MySQL 下生效。
    """
    locate = await db.execute(
        select(Application.id, Application.order_id, Application.tenant_id).where(
            Application.id == application_id
        )
    )
    row = locate.first()
    if not row:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    _, order_id, tenant_id = row
    assert_tenant_scope(payload, tenant_id, detail="投递记录不存在")

    await _get_order_for_update(db, order_id)

    result = await db.execute(
        select(Application)
        .options(
            selectinload(Application.teacher),
            selectinload(Application.resume),
            selectinload(Application.order),
            selectinload(Application.tenant),
        )
        .where(Application.id == application_id)
        .with_for_update()
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    return application


def _add_financial_record(
    db: AsyncSession,
    application: Application,
    amount: float | Decimal,
    record_type: FinancialType,
    remark: str,
    operator_role: str = "",
) -> None:
    db.add(
        FinancialRecord(
            order_id=application.order_id,
            tenant_id=application.tenant_id,
            teacher_id=application.teacher_id,
            amount=Decimal(str(amount)),
            type=record_type,
            remark=remark,
            operator_role=operator_role or None,
        )
    )


def _notify_teacher(
    db: AsyncSession,
    application: Application,
    title: str,
    content: str,
    grade_subject: str | None = None,
) -> None:
    """投递流转结果写入教员站内通知；标题/正文截断到列长，防止超长报错。"""
    db.add(
        Notification(
            teacher_id=application.teacher_id,
            title=title[:50],
            content=(content or "")[:255],
            application_id=application.id,
            order_id=application.order_id,
        )
    )


def _order_subject(application: Application, order: Order | None = None) -> str:
    source = order or getattr(application, "order", None)
    return getattr(source, "grade_subject", None) or "该订单"


def _refresh_order_expiry(order: Order, now: datetime.datetime) -> None:
    """重开招聘统一的有效期策略：从现在起重新计时（含周期标记，见 order_maintenance）。"""
    refresh_order_expiry(order, now)


def _settle_order_after_disposal(
    order: Order,
    now: datetime.datetime,
    *,
    was_current_trial_teacher: bool,
) -> None:
    """
    资金处置（试课失败/没收/取消）后的订单收尾：
    仅试课中且回退对象是当前试课教员时才重开招聘，防止踩掉他人进行中的试课
    或复活已完成/已归档订单；重开时清空选中标记并刷新有效期。
    """
    if order.status == OrderStatus.trial_in_progress and was_current_trial_teacher:
        order.status = OrderStatus.recruiting
    if was_current_trial_teacher:
        order.selected_teacher_id = None
    if order.status == OrderStatus.recruiting:
        _refresh_order_expiry(order, now)


def _application_fee(order: Order, application: Application) -> dict:
    """
    该投递适用的费用基准（金额一律 Decimal，与精算模块口径一致）：
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
        "total_info_fee": Decimal(str(order.calculated_info_fee)),
        "deposit": Decimal(str(order.deposit_amount)),
        "balance": Decimal(str(order.balance_amount)),
    }


def _fee_locked(order: Order, application: Application) -> dict:
    """
    收款/退费节点的费率基准：优先读确认定金时写入的费率快照，
    教员付定金后中介改价不影响该投递的尾款与退款口径；
    无快照（历史数据）回退按订单现状现算，保持旧行为。
    """
    if None not in (application.fee_total, application.fee_deposit, application.fee_balance):
        return {
            "total_info_fee": Decimal(str(application.fee_total)),
            "deposit": Decimal(str(application.fee_deposit)),
            "balance": Decimal(str(application.fee_balance)),
        }
    return _application_fee(order, application)


@router.post("/", response_model=ApplicationResponse)
async def apply_order(
    body: ApplyOrderRequest,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """教员投递简历到某个订单。自带价订单需传入 proposed_price。"""
    order_id = body.order_id
    resume_id = body.resume_id
    proposed_price = body.proposed_price
    # 封禁教员不可投递
    teacher = await db.get(Teacher, payload.teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="教员不存在")
    if teacher.is_banned:
        raise HTTPException(status_code=403, detail="账号已被平台限制投递，请联系客服")

    # 检查订单是否可投递
    order = await db.get(Order, order_id)
    if not order or order.status != OrderStatus.recruiting:
        raise HTTPException(status_code=400, detail="该订单已不可投递")
    if order.expired_at and order.expired_at < datetime.datetime.utcnow():
        raise HTTPException(status_code=400, detail="该订单已过期")

    # 停用中介的订单不可投递
    tenant = await db.get(Tenant, order.tenant_id)
    if tenant is None or not tenant.is_active:
        raise HTTPException(status_code=403, detail="该中介已停用，暂不可投递")

    # 中介级黑名单：被该中介拉黑的教员不可投递其订单
    from models.domain import TenantTeacherBlacklist
    blacklisted = await db.scalar(
        select(TenantTeacherBlacklist.id).where(
            TenantTeacherBlacklist.tenant_id == order.tenant_id,
            TenantTeacherBlacklist.teacher_id == payload.teacher_id,
        )
    )
    if blacklisted:
        raise HTTPException(
            status_code=403,
            detail="您已被该中介限制投递，如有疑问请联系中介",
        )

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

    # 检查是否已投递：未终结的投递不可重复；被拒/已退款的允许重新投递
    existing_result = await db.execute(
        select(Application).where(
            Application.order_id == order_id,
            Application.teacher_id == payload.teacher_id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing and existing.status not in (
        ApplicationStatus.rejected,
        ApplicationStatus.refunded,
        ApplicationStatus.forfeited,
    ):
        raise HTTPException(status_code=409, detail="您已投递过该订单，请等待中介处理")

    now = datetime.datetime.utcnow()
    if existing:
        # 复用历史投递行（uk_teacher_order 唯一约束），重置为待审核并清空上一轮痕迹
        application = existing
        application.status = ApplicationStatus.pending
        application.resume_id = resume_id
        application.proposed_price = proposed_price
        application.applied_at = now
        application.shortlisted_at = None
        application.deposit_paid_at = None
        application.balance_paid_at = None
        application.rejected_at = None
        application.refunded_at = None
        # 上一轮的费率快照随之作废：新一轮的口径在下一次确认定金时重新锁定
        application.fee_total = None
        application.fee_deposit = None
        application.fee_balance = None
    else:
        application = Application(
            order_id=order_id,
            teacher_id=payload.teacher_id,
            tenant_id=order.tenant_id,
            resume_id=resume_id,
            status=ApplicationStatus.pending,
            proposed_price=proposed_price,
        )

    # 报价仅记录在投递上，不回写订单级价格；任何报价都在投递入口精算校验，
    # 防止恶意低价流入后在确认定金/退款精算阶段抛错导致流程卡死。
    if proposed_price:
        try:
            calculate_info_fee(
                base_price=proposed_price,
                weekly_frequency=order.weekly_frequency,
                is_summer_vacation=order.is_summer_vacation,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e

    if not existing:
        db.add(application)
    try:
        await db.flush()
    except IntegrityError as e:
        # 并发双击投递命中 uk_teacher_order 唯一约束
        raise HTTPException(status_code=409, detail="您已投递过该订单") from e
    # applied_at 是 server_default：flush 后未回读，MySQL 下响应序列化会触发
    # 懒加载 IO 报 MissingGreenlet（SQLite 测试环境不触发，上线彩排实测抓出）
    await db.refresh(application)

    # 通知中介有新投递
    db.add(Notification(
        tenant_id=order.tenant_id,
        title="收到新投递",
        content=f"「{order.grade_subject}」收到教员 {teacher.name} 的新投递，请及时审核。",
        application_id=application.id,
        order_id=order_id,
    ))
    application.teacher = await db.get(Teacher, payload.teacher_id)
    application.resume = resume
    application.order = order
    application.tenant = await db.get(Tenant, order.tenant_id)
    return _build_application_response(application)


@router.get("/summary", response_model=ApplicationSummaryResponse)
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
    query = tenant_scoped(query, payload, Application.tenant_id)
    query = query.group_by(Application.order_id)

    result = await db.execute(query)
    order_counts = {str(order_id): int(count) for order_id, count in result.all()}
    total_applications = sum(order_counts.values())

    # 每单最新投递时间：审核页左栏"紧迫度"标记用（一周没投递的单要凸显）
    last_query = (
        select(Application.order_id, func.max(Application.applied_at))
        .join(Order, Order.id == Application.order_id)
        .where(Application.status == ApplicationStatus.pending)
        .where(Order.status.in_((OrderStatus.recruiting, OrderStatus.trial_in_progress)))
        .where((Order.status != OrderStatus.recruiting) | (Order.expired_at > datetime.datetime.utcnow()))
    )
    last_query = tenant_scoped(last_query, payload, Application.tenant_id)
    last_query = last_query.group_by(Application.order_id)
    last_rows = (await db.execute(last_query)).all()
    last_application_at = {
        str(order_id): (ts.isoformat() if ts else None) for order_id, ts in last_rows
    }
    return {
        "total_applications": total_applications,
        "order_counts": order_counts,
        "last_application_at": last_application_at,
    }


@router.get("/mine", response_model=list[ApplicationResponse])
async def list_my_applications(
    page: int = 1,
    page_size: int = 20,
    order_id: int | None = None,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """
    查看我的投递记录，分页返回（page_size<=0 一律按默认页长 20 处理，不再支持全量）。
    order_id 供订单详情页按单查询"我在该订单的投递"，避免拉全量列表再内存过滤。
    排序：进行中的投递按订单到期时间升序（最紧急在最上）；终态（未通过/退款/没收/成交）沉底。
    """
    page = max(1, page)
    page_size = 20 if page_size <= 0 else min(page_size, 50)
    is_terminal = case(
        (Application.status.in_((
            ApplicationStatus.rejected,
            ApplicationStatus.refunded,
            ApplicationStatus.forfeited,
            ApplicationStatus.completed,
        )), 1),
        else_=0,
    )
    query = (
        select(Application)
        .options(
            selectinload(Application.teacher),
            selectinload(Application.resume),
            selectinload(Application.order),
            selectinload(Application.tenant),
        )
        .join(Order, Order.id == Application.order_id)
        .where(Application.teacher_id == payload.teacher_id)
        .order_by(
            is_terminal.asc(),
            Order.expired_at.asc(),
            Application.applied_at.desc(),
            Application.id.desc(),
        )
    )
    if order_id is not None:
        query = query.where(Application.order_id == order_id)
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    applications = result.scalars().all()
    return [_build_application_response(a) for a in applications]


@router.get("/order/{order_id}", response_model=list[ApplicationResponse])
async def list_order_applications(
    order_id: int,
    page: int = 1,
    page_size: int = 100,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    B 端：查看某订单的所有投递记录，分页返回（热门订单投递数会破百，不再无上限）。
    返回裸列表，"是否还有下一页"由返回条数是否等于 page_size 判断。
    """
    # 租户隔离
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    assert_tenant_scope(payload, order.tenant_id, detail="订单不存在")

    page = max(1, page)
    page_size = 100 if page_size <= 0 else min(page_size, 200)
    result = await db.execute(
        select(Application)
        .options(
            selectinload(Application.teacher),
            selectinload(Application.resume),
            selectinload(Application.order),
            selectinload(Application.tenant),
        )
        .where(Application.order_id == order_id)
        .order_by(Application.applied_at.desc(), Application.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    applications = result.scalars().all()
    credit_map = await teacher_credit_map(db, [a.teacher_id for a in applications])
    return [_build_application_response(a, credit_map) for a in applications]


@router.post("/{application_id}/shortlist", response_model=ApplicationResponse)
async def shortlist_application(
    application_id: int,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：将教员加入候选队列（shortlisted）。"""
    application = await _get_managed_application(application_id, payload, db)
    if application.status != ApplicationStatus.pending:
        raise HTTPException(status_code=400, detail="仅 pending 状态的投递可被选中")

    order = await _get_order_for_update(db, application.order_id)
    if order.status != OrderStatus.recruiting:
        raise HTTPException(status_code=409, detail="订单已不在招聘中，不能再加入候选")

    application.status = ApplicationStatus.shortlisted
    application.shortlisted_at = datetime.datetime.utcnow()
    _notify_teacher(
        db, application, "进入候选名单",
        f"您在「{_order_subject(application)}」订单中进入候选，请耐心等待中介安排。",
    )

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
    _notify_teacher(
        db, application, "投递未通过",
        f"很遗憾，「{_order_subject(application)}」的投递未被选中，可继续投递其他订单。",
    )
    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/restore", response_model=ApplicationResponse)
async def restore_application(
    application_id: int,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    B 端：误操作的"已拒绝"恢复为待审核（安全回退）。
    仅限未产生任何资金往来、订单仍在招聘中、教员未被拉黑/封禁的投递；
    资金处置终态（已没收/已退款/已成交）不可回退，保证台账与状态一致。
    """
    application = await _get_managed_application(application_id, payload, db)
    if application.status != ApplicationStatus.rejected:
        raise HTTPException(status_code=400, detail="仅已拒绝的投递可恢复为待审核")

    order = await _get_order_for_update(db, application.order_id)
    if order.status != OrderStatus.recruiting:
        raise HTTPException(status_code=409, detail="订单已不在招聘中，无法恢复投递")

    # 有资金往来的投递不可恢复（历史数据中没收曾与拒绝共用状态）：恢复会导致台账与状态矛盾
    money_exists = await db.scalar(
        select(FinancialRecord.id).where(
            FinancialRecord.order_id == application.order_id,
            FinancialRecord.teacher_id == application.teacher_id,
        )
    )
    if money_exists:
        raise HTTPException(status_code=409, detail="该投递已有资金往来记录，不可恢复")

    banned = await db.scalar(select(Teacher.is_banned).where(Teacher.id == application.teacher_id))
    if banned:
        raise HTTPException(status_code=403, detail="该教员已被平台封禁")
    from models.domain import TenantTeacherBlacklist

    blacklisted = await db.scalar(
        select(TenantTeacherBlacklist.id).where(
            TenantTeacherBlacklist.tenant_id == application.tenant_id,
            TenantTeacherBlacklist.teacher_id == application.teacher_id,
        )
    )
    if blacklisted:
        raise HTTPException(status_code=403, detail="该教员已被本中介拉黑")

    application.status = ApplicationStatus.pending
    application.rejected_at = None
    _notify_teacher(
        db, application, "投递已恢复",
        f"您在「{_order_subject(application)}」的投递已恢复为待审核，请耐心等待中介处理。",
    )
    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/start-trial", response_model=ApplicationResponse)
async def start_trial_application(
    application_id: int,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：从候选队列中选择一位教员开始试课，同一订单同时只允许一位。"""
    application = await _get_managed_application(application_id, payload, db)
    if application.status != ApplicationStatus.deposit_paid:
        raise HTTPException(status_code=400, detail="必须先支付定金才能开始试课，防止教员绕过中介获取家长联系方式")

    # 必须锁定订单行后校验：只有招聘中的订单可开试课，
    # 否则已完成/已归档订单会被残留候选"复活"并二次收款
    order = await _get_order_for_update(db, application.order_id)
    if order.status != OrderStatus.recruiting:
        raise HTTPException(status_code=409, detail="订单已不在招聘中，不能开始试课")

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
    _notify_teacher(
        db, application, "试课开始",
        f"您已开始「{_order_subject(application, order)}」试课，可在订单页查看家长联系方式。",
        grade_subject=order.grade_subject,
    )
    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/confirm-deposit", response_model=ApplicationResponse)
async def confirm_deposit(
    application_id: int,
    request: Request,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：线下确认已收到教员定金，并生成财务流水。"""
    application = await _get_managed_application(application_id, payload, db)
    if application.status != ApplicationStatus.shortlisted:
        raise HTTPException(status_code=400, detail="仅候选队列中的教员可确认定金")

    order = await _get_order_for_update(db, application.order_id)
    if order.status != OrderStatus.recruiting:
        raise HTTPException(status_code=409, detail="订单已不在招聘中，不能确认定金")

    application.status = ApplicationStatus.deposit_paid
    application.deposit_paid_at = datetime.datetime.utcnow()
    order.selected_teacher_id = application.teacher_id
    _notify_teacher(
        db, application, "定金已确认",
        f"中介已确认收到您在「{_order_subject(application, order)}」的定金，等待安排试课。",
    )
    # 订单保持 recruiting（候选已付定金，等待开始试课）；自带价订单按投递报价精算
    fee = _application_fee(order, application)
    # 费率快照在收款首刻锁定（P1-2）：之后尾款/退款/没收一律读快照，中介改价不追溯
    application.fee_total = fee["total_info_fee"]
    application.fee_deposit = fee["deposit"]
    application.fee_balance = fee["balance"]
    _add_financial_record(
        db,
        application,
        fee["deposit"],
        FinancialType.deposit_in,
        "线下确认定金",
        operator_role=payload.role,
    )
    await record_audit(
        db,
        actor_role=payload.role,
        actor_id=payload.tenant_id or 0,
        action=ACTION_CONFIRM_DEPOSIT,
        object_id=application.id,
        tenant_id=application.tenant_id,
        request=request,
    )
    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/confirm-balance", response_model=ApplicationResponse)
async def confirm_balance(
    application_id: int,
    request: Request,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：线下确认已收到尾款，并生成财务流水。"""
    application = await _get_managed_application(application_id, payload, db)
    if application.status != ApplicationStatus.trial_in_progress:
        raise HTTPException(status_code=400, detail="仅试课中的教员可确认尾款")

    order = await _get_order_for_update(db, application.order_id)
    if order.status != OrderStatus.trial_in_progress:
        raise HTTPException(status_code=409, detail="订单不在试课中，不能确认尾款")

    application.status = ApplicationStatus.balance_paid
    application.balance_paid_at = datetime.datetime.utcnow()
    order.selected_teacher_id = application.teacher_id
    _notify_teacher(
        db, application, "尾款已确认",
        f"中介已确认收到「{_order_subject(application, order)}」尾款，试课顺利请等待成交确认。",
    )
    # 订单保持 trial_in_progress，直到中介确认完成（complete）
    fee = _fee_locked(order, application)
    _add_financial_record(
        db,
        application,
        fee["balance"],
        FinancialType.balance_in,
        "线下确认尾款",
        operator_role=payload.role,
    )
    await record_audit(
        db,
        actor_role=payload.role,
        actor_id=payload.tenant_id or 0,
        action=ACTION_CONFIRM_BALANCE,
        object_id=application.id,
        tenant_id=application.tenant_id,
        request=request,
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

    order = await _get_order_for_update(db, application.order_id)
    if order.status != OrderStatus.trial_in_progress:
        raise HTTPException(status_code=409, detail="订单不在试课中，不能确认完成")

    order.selected_teacher_id = application.teacher_id
    order.status = OrderStatus.completed
    # 投递进入终态，避免卡片停留在"尾款已付"导致重复点击确认完成
    application.status = ApplicationStatus.completed
    _notify_teacher(
        db, application, "恭喜成交",
        f"「{_order_subject(application, order)}」订单已完成，感谢配合，期待下次合作。",
    )

    # 成交即关闭同单其余未终结投递：既不让落选教员无限等待，
    # 也消除残留候选把已完成订单"复活"的入口。
    # 资金去向守卫（P1-1）：已付定金的候选必须登记退款流水，否则台账上凭空消失；
    # 试课中/尾款已付的兄弟投递属不变量破坏（同单同时只允许一场试课），拒绝成交人工排查。
    now = datetime.datetime.utcnow()
    result = await db.execute(
        select(Application)
        .where(
            Application.order_id == application.order_id,
            Application.id != application.id,
            Application.status.in_((
                ApplicationStatus.pending,
                ApplicationStatus.shortlisted,
                ApplicationStatus.deposit_paid,
                ApplicationStatus.trial_in_progress,
                ApplicationStatus.balance_paid,
            )),
        )
        .with_for_update()
    )
    siblings = result.scalars().all()
    if any(
        s.status in (ApplicationStatus.trial_in_progress, ApplicationStatus.balance_paid)
        for s in siblings
    ):
        raise HTTPException(
            status_code=409,
            detail="该订单存在进行中试课的其他投递，请先完成退款或没收处置，再确认成交",
        )

    refunded_siblings = 0
    for sibling in siblings:
        if sibling.status == ApplicationStatus.deposit_paid:
            deposit_fee = _fee_locked(order, sibling)
            sibling.status = ApplicationStatus.refunded
            sibling.refunded_at = now
            _add_financial_record(
                db, sibling, deposit_fee["deposit"], FinancialType.refund_out,
                "其他教员成交，退还定金",
                operator_role=payload.role,
            )
            refunded_siblings += 1
            _notify_teacher(
                db, sibling, "未被选中，定金退还",
                f"「{order.grade_subject}」订单已有其他教员成交，您的定金 {deposit_fee['deposit']} 元将退还，请联系中介领取。",
            )
        else:
            sibling.status = ApplicationStatus.rejected
            sibling.rejected_at = now
            _notify_teacher(
                db, sibling, "未被选中",
                f"「{order.grade_subject}」订单已有其他教员成交，期待下次合作。",
            )

    if refunded_siblings:
        # 退款是线下动作：让中介立即知情，拖延易引发投诉（与教员取消退款的通知口径一致）
        db.add(Notification(
            tenant_id=order.tenant_id,
            title="成交后待退定金",
            content=f"「{order.grade_subject}」已成交，{refunded_siblings} 位未成交候选的定金已登记退款，请及时处理。",
            order_id=order.id,
        ))

    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/trial-failed", response_model=ApplicationResponse)
async def trial_failed(
    application_id: int,
    request: Request,
    # 默认实例：无 body 调用等价全缺省（零退款走没收分支），与旧 query 参数行为一致
    body: TrialFailedRequest = _TRIAL_FAILED_DEFAULT,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    B 端：试课失败，重新开放订单。

    退费规则：
    - 教员违约（is_teacher_violated=true）：没收已交信息费，不退款，记违约；
    - 正常失败：按精算公式 退费 = max(0, 已交信息费 − 家长支付试课酬 × 70%)；
      零退款也按正常处置（不记违约）；
    - 兼容旧调用：显式传 refund_amount 时以其为准。
    """
    refund_amount = body.refund_amount
    trial_paid_by_parent = body.trial_paid_by_parent
    is_teacher_violated = body.is_teacher_violated
    if refund_amount < 0 or trial_paid_by_parent < 0:
        raise HTTPException(status_code=422, detail="退款金额不能为负数")

    application = await _get_managed_application(application_id, payload, db)
    if application.status not in (
        ApplicationStatus.deposit_paid,
        ApplicationStatus.trial_in_progress,
        ApplicationStatus.balance_paid,
    ):
        raise HTTPException(status_code=400, detail="当前状态不能标记试课失败")

    order = await _get_order_for_update(db, application.order_id)
    # 资金处置在任何订单状态下都允许（含归档单的补处置），
    # 但订单状态的回退是条件化的：仅试课中且回退对象是当前试课教员时才重开招聘，
    # 保证已完成/已归档订单不会被残留候选"复活"。

    now = datetime.datetime.utcnow()
    fee = _fee_locked(order, application)
    paid_amount = fee["deposit"] + (
        fee["balance"] if application.status == ApplicationStatus.balance_paid else 0
    )

    if is_teacher_violated:
        # 教员违约：没收已交信息费（定金 + 已付尾款）
        _add_financial_record(
            db, application, paid_amount, FinancialType.forfeit, "教员违约，没收信息费",
            operator_role=payload.role,
        )
        application.status = ApplicationStatus.forfeited
        _notify_teacher(
            db, application, "试课失败",
            f"「{_order_subject(application, order)}」试课未成功，因教员违约信息费按约没收。",
        )
    else:
        if trial_paid_by_parent > 0:
            refund = calculate_refund(
                total_info_fee_paid=paid_amount,
                trial_paid_by_parent=trial_paid_by_parent,
                is_trial_success=False,
                is_teacher_violated=False,
            )
        else:
            refund = refund_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        # 退款封顶为实收金额，防止录入超额退款造成账实不符
        refund = min(refund, paid_amount)

        if refund > 0:
            application.status = ApplicationStatus.refunded
            application.refunded_at = now
            _add_financial_record(
                db, application, refund, FinancialType.refund_out, "试课失败退款",
                operator_role=payload.role,
            )
            _notify_teacher(
                db, application, "试课失败，退款已登记",
                f"「{_order_subject(application, order)}」试课未成功，应退 {refund} 元，请联系中介领取。",
            )
        else:
            # 正常试课失败（含零退款）：不记教员违约。
            # 状态置 refunded；零退款时补一条 0 元退款流水留台账痕迹。
            # 绝不能写 forfeit——违约次数按没收流水统计，会把正常失败计成教员违约。
            application.status = ApplicationStatus.refunded
            application.refunded_at = now
            if paid_amount > 0:
                _add_financial_record(
                    db, application, Decimal("0"), FinancialType.refund_out,
                    "试课失败正常处置，零退款",
                    operator_role=payload.role,
                )
            _notify_teacher(
                db, application, "试课失败",
                f"「{_order_subject(application, order)}」试课未成功，本次未产生退款；如有疑问请联系中介。",
            )

    # 仅当订单确实因本次试课处于试课中时才回退招聘，
    # 防止处置残留候选时踩掉他人进行中的试课或复活已完成/已归档订单
    _settle_order_after_disposal(
        order, now,
        was_current_trial_teacher=order.selected_teacher_id == application.teacher_id,
    )

    await record_audit(
        db,
        actor_role=payload.role,
        actor_id=payload.tenant_id or 0,
        action=ACTION_TRIAL_FAILED,
        object_id=application.id,
        tenant_id=application.tenant_id,
        request=request,
    )
    await db.flush()
    return _build_application_response(application)


@router.post("/{application_id}/forfeit", response_model=ApplicationResponse)
async def forfeit_deposit(
    application_id: int,
    request: Request,
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

    order = await _get_order_for_update(db, application.order_id)
    # 同 trial-failed：处置不设订单状态门槛，但只有试课中且回退对象正确时才重开招聘

    now = datetime.datetime.utcnow()
    fee = _fee_locked(order, application)
    forfeited = fee["deposit"] + (
        fee["balance"] if application.status == ApplicationStatus.balance_paid else 0
    )
    _add_financial_record(
        db, application, forfeited, FinancialType.forfeit, "教员违约，没收信息费",
        operator_role=payload.role,
    )

    application.status = ApplicationStatus.forfeited
    _notify_teacher(
        db, application, "投递已关闭",
        f"您在「{_order_subject(application, order)}」的投递因违约被关闭，已付信息费按约没收。",
    )
    # 与 trial-failed 一致：只有没收的是当前试课教员时才把订单从试课中回退
    _settle_order_after_disposal(
        order, now,
        was_current_trial_teacher=order.selected_teacher_id == application.teacher_id,
    )

    await record_audit(
        db,
        actor_role=payload.role,
        actor_id=payload.tenant_id or 0,
        action=ACTION_FORFEIT,
        object_id=application.id,
        tenant_id=application.tenant_id,
        request=request,
    )
    await db.flush()
    return _build_application_response(application)


@router.get("/reviews/mine", response_model=list[OrderReviewResponse])
async def my_reviews(
    page: int = 1,
    page_size: int = 20,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
    # FastAPI 对 Response 注解参数自动注入实例，忽略默认值；仅因语法限制需排在带默认值参数之后
    response: Response = None,
):
    """
    教员查看自己收到的评价，分页返回（page_size<=0 一律按默认页长 20 处理，不再支持全量）。
    X-Total-Count 返回评价总数，供角标等计数场景免拉全量。
    """
    page = max(1, page)
    page_size = 20 if page_size <= 0 else min(page_size, 50)
    if response is not None:
        total = await db.scalar(
            select(func.count()).select_from(OrderReview).where(OrderReview.teacher_id == payload.teacher_id)
        )
        response.headers["X-Total-Count"] = str(total or 0)
    query = (
        select(OrderReview)
        .where(OrderReview.teacher_id == payload.teacher_id)
        .order_by(OrderReview.created_at.desc(), OrderReview.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/{application_id}/review", response_model=OrderReviewResponse)
async def review_application(
    application_id: int,
    body: ReviewCreateRequest,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：对已成交的教员评价（一单一评，可修改）。"""
    application = await _get_managed_application(application_id, payload, db)
    if application.status != ApplicationStatus.completed:
        raise HTTPException(status_code=400, detail="仅已成交的投递可评价")

    order = await db.get(Order, application.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    result = await db.execute(
        select(OrderReview).where(OrderReview.order_id == application.order_id)
    )
    review = result.scalar_one_or_none()
    if review is None:
        review = OrderReview(
            order_id=application.order_id,
            application_id=application.id,
            tenant_id=application.tenant_id,
            teacher_id=application.teacher_id,
        )
        db.add(review)
        _notify_teacher(
            db, application, "收到新评价",
            f"「{order.grade_subject}」获得 {body.rating} 星评价，可在个人中心查看。",
        )
    review.rating = body.rating
    review.comment = (body.comment or "")[:255] or None

    await db.flush()
    # onupdate 后 updated_at 已过期，回读避免序列化失败
    await db.refresh(review)
    return review


@router.post("/{application_id}/cancel", response_model=ApplicationResponse)
async def cancel_application(
    application_id: int,
    request: Request,
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
        .with_for_update()
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

    # 已付定金的取消会写退款流水：锁订单行，串行化与 B 端资金操作的并发
    order = await _get_order_for_update(db, application.order_id)

    now = datetime.datetime.utcnow()

    if application.status == ApplicationStatus.deposit_paid:
        fee = _fee_locked(order, application)
        _add_financial_record(
            db, application, fee["deposit"], FinancialType.refund_out, "教员取消投递，退还定金",
            operator_role="teacher",
        )
        application.status = ApplicationStatus.refunded
        application.refunded_at = now
    else:
        application.status = ApplicationStatus.rejected
        application.rejected_at = now

    # 订单若因此失去候选/已付定金教员，重新开放招聘；
    # 仅当被选中的正是本人时才清空选中标记，避免误清其他候选的状态
    if order.status == OrderStatus.recruiting:
        if order.selected_teacher_id == application.teacher_id:
            order.selected_teacher_id = None
        _refresh_order_expiry(order, now)

    # 教员侧取消要让中介立即知情：已付定金的取消涉及线下退款，拖延易引发投诉
    teacher_name = getattr(application, "teacher", None)
    cancel_note = "，定金将登记退款，请及时处理" if application.status == ApplicationStatus.refunded else ""
    db.add(Notification(
        tenant_id=order.tenant_id,
        title="教员取消投递",
        content=f"教员 {teacher_name.name if teacher_name else application.teacher_id} 取消了「{order.grade_subject}」的投递{cancel_note}。",
        application_id=application.id,
        order_id=order.id,
    ))

    await record_audit(
        db,
        actor_role=payload.role,
        actor_id=payload.teacher_id or 0,
        action=ACTION_CANCEL,
        object_id=application.id,
        tenant_id=application.tenant_id or order.tenant_id,
        request=request,
    )
    await db.flush()
    return _build_application_response(application)
