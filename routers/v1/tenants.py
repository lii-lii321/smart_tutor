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
    TenantAdminResponse,
    TenantCreateRequest,
    TenantStatusUpdate,
)

router = APIRouter(prefix="/api/v1/tenants", tags=["中介管理"])


def _generate_invite_code(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
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

    tenant = Tenant(
        tenant_name=body.tenant_name,
        invite_code=invite_code,
        contact_wechat=body.contact_wechat,
        is_active=True,
    )
    db.add(tenant)
    await db.flush()
    return tenant


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
