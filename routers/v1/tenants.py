"""
老板端：中介账号与邀请码管理。
"""
import datetime
import secrets
from decimal import Decimal
import string
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db, seed_demo_data
from middleware.auth import require_role
from models.domain import (
    Application, ApplicationStatus, FinancialRecord, FinancialType,
    Notification, Order, OrderReview, OrderStatus,
    Teacher, TeacherResume, Tenant, TenantTeacherBlacklist,
)
from models.schemas import (
    BlacklistCreateRequest,
    BlacklistItem,
    DemoCountsResponse,
    DemoDataResponse,
    DemoTeacherResponse,
    MyTeacherItem,
    OwnerFunnelStats,
    OwnerStatsResponse,
    OwnerTenantRankItem,
    TeacherAdminItem,
    TeacherBanRequest,
    TenantAdminResponse,
    TenantCreateRequest,
    TenantStatusUpdate,
)
from services.auth import hash_password

router = APIRouter(prefix="/api/v1/tenants", tags=["中介管理"])


def _generate_invite_code(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _generate_password(length: int = 10) -> str:
    # 去掉易混淆字符，方便老板线下口头转达给中介
    alphabet = "23456789abcdefghjkmnpqrstuvwxyz"
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def _build_demo_data(db: AsyncSession) -> DemoDataResponse:
    tenant_result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    tenants = tenant_result.scalars().all()

    teacher_result = await db.execute(select(Teacher).order_by(Teacher.created_at.desc()))
    teachers = teacher_result.scalars().all()
    teacher_ids = [teacher.id for teacher in teachers]

    resumes_by_teacher: dict[int, TeacherResume] = {}
    if teacher_ids:
        resume_result = await db.execute(
            select(TeacherResume)
            .where(TeacherResume.teacher_id.in_(teacher_ids))
            .order_by(TeacherResume.is_default.desc(), TeacherResume.created_at.desc())
        )
        for resume in resume_result.scalars().all():
            resumes_by_teacher.setdefault(resume.teacher_id, resume)

    resume_count = await db.scalar(select(func.count()).select_from(TeacherResume))

    return DemoDataResponse(
        counts=DemoCountsResponse(
            tenants=len(tenants),
            teachers=len(teachers),
            resumes=resume_count or 0,
        ),
        tenants=tenants,
        teachers=[
            DemoTeacherResponse(
                id=teacher.id,
                name=teacher.name,
                phone=teacher.phone,
                school=teacher.school,
                major=teacher.major,
                grade=teacher.grade,
                highlights=teacher.highlights,
                teaching_subjects=resumes_by_teacher.get(teacher.id).teaching_subjects
                if teacher.id in resumes_by_teacher
                else None,
                teaching_grades=resumes_by_teacher.get(teacher.id).teaching_grades
                if teacher.id in resumes_by_teacher
                else None,
            )
            for teacher in teachers
        ],
    )


@router.get("/", response_model=list[TenantAdminResponse])
async def list_tenants(
    _payload=Depends(require_role("super_admin")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))
    return result.scalars().all()


@router.get("/demo-data", response_model=DemoDataResponse)
async def get_demo_data(
    _payload=Depends(require_role("super_admin")),
    db: AsyncSession = Depends(get_db),
):
    return await _build_demo_data(db)


@router.post("/seed-demo", response_model=DemoDataResponse)
async def seed_demo(
    _payload=Depends(require_role("super_admin")),
    db: AsyncSession = Depends(get_db),
):
    await seed_demo_data()
    return await _build_demo_data(db)


@router.post("/", response_model=TenantAdminResponse)
async def create_tenant(
    body: TenantCreateRequest,
    _payload=Depends(require_role("super_admin")),
    db: AsyncSession = Depends(get_db),
):
    invite_code = body.invite_code or _generate_invite_code()
    for _ in range(5):
        existing = await db.execute(select(Tenant).where(Tenant.invite_code == invite_code))
        if not existing.scalar_one_or_none():
            break
        if body.invite_code:
            raise HTTPException(status_code=409, detail="该邀请码已存在")
        invite_code = _generate_invite_code()
    else:
        raise HTTPException(status_code=500, detail="邀请码生成失败，请重试")

    plain_password = body.password or _generate_password()
    tenant = Tenant(
        tenant_name=body.tenant_name,
        invite_code=invite_code,
        contact_wechat=body.contact_wechat,
        is_active=True,
        password_hash=hash_password(plain_password),
    )
    db.add(tenant)
    await db.flush()

    response = TenantAdminResponse.model_validate(tenant)
    response.initial_password = plain_password
    return response


@router.post("/{tenant_id}/reset-password", response_model=TenantAdminResponse)
async def reset_tenant_password(
    tenant_id: int,
    _payload=Depends(require_role("super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """老板重置中介登录密码，新密码明文仅本次返回，请立即转达中介。"""
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="中介不存在")

    plain_password = _generate_password()
    tenant.password_hash = hash_password(plain_password)
    # 已签发的旧 token 立即失效
    tenant.token_valid_after = datetime.datetime.utcnow()
    await db.flush()

    response = TenantAdminResponse.model_validate(tenant)
    response.initial_password = plain_password
    return response


@router.patch("/{tenant_id}/status", response_model=TenantAdminResponse)
async def update_tenant_status(
    tenant_id: int,
    body: TenantStatusUpdate,
    _payload=Depends(require_role("super_admin")),
    db: AsyncSession = Depends(get_db),
):
    tenant = await db.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="中介不存在")
    tenant.is_active = body.is_active
    await db.flush()
    return tenant


@router.get("/stats", response_model=OwnerStatsResponse)
async def owner_stats(
    _payload=Depends(require_role("super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """老板端经营看板：平台规模、资金总览、投递漏斗与中介排行。"""
    tenant_count = await db.scalar(select(func.count()).select_from(Tenant)) or 0
    active_tenant_count = await db.scalar(
        select(func.count()).select_from(Tenant).where(Tenant.is_active.is_(True))
    ) or 0
    teacher_count = await db.scalar(select(func.count()).select_from(Teacher)) or 0

    order_rows = (await db.execute(
        select(Order.status, func.count())
        .group_by(Order.status)
    )).all()
    orders_by_status = {status: int(count) for status, count in order_rows}

    fin_rows = (await db.execute(
        select(FinancialRecord.type, func.coalesce(func.sum(FinancialRecord.amount), 0))
        .group_by(FinancialRecord.type)
    )).all()
    fin_by_type = {ftype: Decimal(str(total)) for ftype, total in fin_rows}

    app_rows = (await db.execute(
        select(Application.status, func.count())
        .group_by(Application.status)
    )).all()
    apps_by_status = {status: int(count) for status, count in app_rows}

    # 漏斗按"历史到达过该阶段"统计（快照口径会在成交后丢失中间阶段）
    funnel_shortlisted = await db.scalar(
        select(func.count()).select_from(Application).where(Application.shortlisted_at.is_not(None))
    ) or 0
    funnel_deposit = await db.scalar(
        select(func.count()).select_from(Application).where(Application.deposit_paid_at.is_not(None))
    ) or 0

    # 中介排行：订单与投递按租户聚合，GMV = 定金 + 尾款
    order_tenant_rows = (await db.execute(
        select(Order.tenant_id, Order.status, func.count())
        .group_by(Order.tenant_id, Order.status)
    )).all()
    app_tenant_rows = (await db.execute(
        select(Application.tenant_id, func.count())
        .group_by(Application.tenant_id)
    )).all()
    gmv_tenant_rows = (await db.execute(
        select(FinancialRecord.tenant_id, func.coalesce(func.sum(FinancialRecord.amount), 0))
        .where(FinancialRecord.type.in_((FinancialType.deposit_in, FinancialType.balance_in)))
        .group_by(FinancialRecord.tenant_id)
    )).all()
    tenants = (await db.execute(select(Tenant).order_by(Tenant.created_at.desc()))).scalars().all()

    per_tenant_orders: dict[int, dict[str, int]] = {}
    for tenant_id, status, count in order_tenant_rows:
        per_tenant_orders.setdefault(tenant_id, {"total": 0})
        per_tenant_orders[tenant_id]["total"] += int(count)
        per_tenant_orders[tenant_id][status.value] = int(count)
    per_tenant_apps = {tenant_id: int(count) for tenant_id, count in app_tenant_rows}
    per_tenant_gmv = {tenant_id: float(total) for tenant_id, total in gmv_tenant_rows}

    ranking = []
    for tenant in tenants:
        stats = per_tenant_orders.get(tenant.id, {})
        ranking.append(OwnerTenantRankItem(
            tenant_id=tenant.id,
            tenant_name=tenant.tenant_name,
            invite_code=tenant.invite_code,
            is_active=tenant.is_active,
            orders_total=stats.get("total", 0),
            orders_recruiting=stats.get(OrderStatus.recruiting.value, 0),
            orders_completed=stats.get(OrderStatus.completed.value, 0),
            applications_total=per_tenant_apps.get(tenant.id, 0),
            gmv=round(per_tenant_gmv.get(tenant.id, 0.0), 2),
        ))
    ranking.sort(key=lambda item: (-item.gmv, -item.orders_completed))

    return OwnerStatsResponse(
        tenant_count=int(tenant_count),
        active_tenant_count=int(active_tenant_count),
        teacher_count=int(teacher_count),
        orders_recruiting=orders_by_status.get(OrderStatus.recruiting, 0),
        orders_trial=orders_by_status.get(OrderStatus.trial_in_progress, 0),
        orders_completed=orders_by_status.get(OrderStatus.completed, 0),
        orders_archived=orders_by_status.get(OrderStatus.archived, 0),
        gmv_total=float(fin_by_type.get(FinancialType.deposit_in, 0) + fin_by_type.get(FinancialType.balance_in, 0)),
        refund_total=float(fin_by_type.get(FinancialType.refund_out, 0)),
        forfeit_total=float(fin_by_type.get(FinancialType.forfeit, 0)),
        funnel=OwnerFunnelStats(
            applications_total=sum(apps_by_status.values()),
            shortlisted=int(funnel_shortlisted),
            deposit_paid=int(funnel_deposit),
            completed=apps_by_status.get(ApplicationStatus.completed, 0),
        ),
        ranking=ranking,
    )


async def _teacher_credit_for(db: AsyncSession, teacher_id: int) -> dict:
    """单教员信用聚合（成交/违约/均分）。"""
    completed = await db.scalar(
        select(func.count()).select_from(Application)
        .where(Application.teacher_id == teacher_id, Application.status == ApplicationStatus.completed)
    ) or 0
    violations = await db.scalar(
        select(func.count()).select_from(FinancialRecord)
        .where(FinancialRecord.teacher_id == teacher_id, FinancialRecord.type == FinancialType.forfeit)
    ) or 0
    avg_rating = await db.scalar(
        select(func.avg(OrderReview.rating)).where(OrderReview.teacher_id == teacher_id)
    )
    return {
        "completed_count": int(completed),
        "violation_count": int(violations),
        "avg_rating": round(float(avg_rating), 1) if avg_rating is not None else None,
    }


@router.get("/my-teachers", response_model=list[MyTeacherItem])
async def my_teachers(
    payload=Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """中介教员管理：与本租户发生过投递关系的教员档案 + 黑名单状态。"""
    query = (
        select(
            Teacher,
            func.count(Application.id).label("apps_total"),
            func.max(Application.applied_at).label("last_applied"),
        )
        .join(Application, Application.teacher_id == Teacher.id)
        .group_by(Teacher.id)
        .order_by(func.max(Application.applied_at).desc())
    )
    if payload.role != "super_admin":
        query = query.where(Application.tenant_id == payload.tenant_id)
    rows = (await db.execute(query)).all()

    blacklisted_ids = set()
    if rows:
        if payload.role == "super_admin":
            # 超管视角：全量黑名单
            bl_rows = (await db.execute(select(TenantTeacherBlacklist.teacher_id))).all()
        else:
            bl_rows = (await db.execute(
                select(TenantTeacherBlacklist.teacher_id)
                .where(TenantTeacherBlacklist.tenant_id == payload.tenant_id)
            )).all()
        blacklisted_ids = {r[0] for r in bl_rows}

    items = []
    for teacher, apps_total, last_applied in rows:
        credit = await _teacher_credit_for(db, teacher.id)
        items.append(MyTeacherItem(
            teacher_id=teacher.id,
            name=teacher.name,
            phone=teacher.phone,
            school=teacher.school,
            gender=teacher.gender,
            applications_total=int(apps_total),
            last_applied_at=last_applied,
            is_blacklisted=teacher.id in blacklisted_ids,
            **credit,
        ))
    return items


@router.post("/teachers/{teacher_id}/blacklist", response_model=BlacklistItem)
async def blacklist_teacher(
    teacher_id: int,
    body: BlacklistCreateRequest,
    payload=Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """
    中介拉黑教员：仅限制本租户（投递被拒、推荐屏蔽），
    并自动拒绝该教员在本租户所有待审核投递。全局封禁仍是老板权限。
    """
    teacher = await db.get(Teacher, teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="教员不存在")

    tenant_id = payload.tenant_id
    result = await db.execute(
        select(TenantTeacherBlacklist).where(
            TenantTeacherBlacklist.tenant_id == tenant_id,
            TenantTeacherBlacklist.teacher_id == teacher_id,
        )
    )
    record = result.scalar_one_or_none()
    if record:
        raise HTTPException(status_code=409, detail="该教员已在黑名单中")
    db.add(TenantTeacherBlacklist(
        tenant_id=tenant_id,
        teacher_id=teacher_id,
        reason=(body.reason or "")[:255] or None,
    ))

    # 拉黑即清场：拒绝本租户所有 pending 投递，防止黑名单教员继续占用候选位
    pending_apps = (await db.execute(
        select(Application).where(
            Application.teacher_id == teacher_id,
            Application.tenant_id == tenant_id,
            Application.status == ApplicationStatus.pending,
        )
    )).scalars().all()
    now = datetime.datetime.utcnow()
    for app in pending_apps:
        app.status = ApplicationStatus.rejected
        app.rejected_at = now
        db.add(Notification(
            teacher_id=teacher_id,
            title="投递未通过",
            content="您在该中介的投递已被关闭，如需沟通请联系中介。",
            application_id=app.id,
            order_id=app.order_id,
        ))

    await db.flush()
    return BlacklistItem(
        teacher_id=teacher_id,
        name=teacher.name,
        phone=teacher.phone,
        reason=(body.reason or "")[:255] or None,
        created_at=now,
    )


@router.delete("/teachers/{teacher_id}/blacklist")
async def unblacklist_teacher(
    teacher_id: int,
    payload=Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """移出黑名单，恢复该教员在本租户的投递与推荐资格。"""
    result = await db.execute(
        select(TenantTeacherBlacklist).where(
            TenantTeacherBlacklist.tenant_id == payload.tenant_id,
            TenantTeacherBlacklist.teacher_id == teacher_id,
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="该教员不在黑名单中")
    await db.delete(record)
    await db.flush()
    return {"ok": True}


@router.get("/teachers", response_model=list[TeacherAdminItem])
async def list_teachers(
    q: str | None = None,
    banned: bool | None = None,
    page: int = 1,
    page_size: int = 20,
    _payload=Depends(require_role("super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """老板端：教员管理列表，支持姓名/手机号关键字与封禁状态筛选。"""
    page = max(1, page)
    page_size = min(max(1, page_size), 100)

    query = select(Teacher).order_by(Teacher.created_at.desc())
    if q and q.strip():
        keyword = q.strip()
        query = query.where(
            (Teacher.name.contains(keyword)) | (Teacher.phone.contains(keyword))
        )
    if banned is not None:
        query = query.where(Teacher.is_banned == banned)

    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    return result.scalars().all()


@router.patch("/teachers/{teacher_id}/ban", response_model=TeacherAdminItem)
async def set_teacher_banned(
    teacher_id: int,
    body: TeacherBanRequest,
    _payload=Depends(require_role("super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """老板端：封禁/解封教员。封禁后不可投递、不可被推荐。"""
    teacher = await db.get(Teacher, teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="教员不存在")
    teacher.is_banned = body.is_banned
    await db.flush()
    return teacher
