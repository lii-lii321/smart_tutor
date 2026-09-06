"""
老板端：中介账号与邀请码管理。
"""
import secrets
import string
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db, seed_demo_data
from middleware.auth import require_role
from models.domain import Teacher, TeacherResume, Tenant
from models.schemas import (
    DemoCountsResponse,
    DemoDataResponse,
    DemoTeacherResponse,
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
