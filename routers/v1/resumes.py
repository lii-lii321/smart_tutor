"""
教员简历库：教员维护多份简历，投递时选择其中一份。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from middleware.auth import TokenPayload, require_role
from models.domain import TeacherResume
from models.schemas import TeacherResumeCreate, TeacherResumeResponse, TeacherResumeUpdate

router = APIRouter(prefix="/api/v1/teacher/resumes", tags=["教员简历"])


async def _unset_default_resumes(db: AsyncSession, teacher_id: int) -> None:
    result = await db.execute(
        select(TeacherResume).where(TeacherResume.teacher_id == teacher_id)
    )
    for resume in result.scalars().all():
        resume.is_default = False


@router.get("/", response_model=list[TeacherResumeResponse])
async def list_resumes(
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TeacherResume)
        .where(TeacherResume.teacher_id == payload.teacher_id)
        .order_by(TeacherResume.is_default.desc(), TeacherResume.created_at.desc())
    )
    return result.scalars().all()


@router.post("/", response_model=TeacherResumeResponse)
async def create_resume(
    body: TeacherResumeCreate,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    count_result = await db.execute(
        select(func.count()).select_from(TeacherResume).where(TeacherResume.teacher_id == payload.teacher_id)
    )
    is_first = count_result.scalar_one() == 0

    if body.is_default or is_first:
        await _unset_default_resumes(db, payload.teacher_id)

    resume = TeacherResume(
        teacher_id=payload.teacher_id,
        title=body.title,
        teaching_subjects=body.teaching_subjects,
        teaching_grades=body.teaching_grades,
        experience=body.experience,
        strengths=body.strengths,
        availability=body.availability,
        expected_rate=body.expected_rate,
        is_default=body.is_default or is_first,
    )
    db.add(resume)
    await db.flush()
    return resume


@router.patch("/{resume_id}", response_model=TeacherResumeResponse)
async def update_resume(
    resume_id: int,
    body: TeacherResumeUpdate,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(TeacherResume, resume_id)
    if not resume or resume.teacher_id != payload.teacher_id:
        raise HTTPException(status_code=404, detail="简历不存在")

    updates = body.model_dump(exclude_unset=True)
    if updates.get("is_default") is True:
        await _unset_default_resumes(db, payload.teacher_id)

    for key, value in updates.items():
        setattr(resume, key, value)

    await db.flush()
    return resume


@router.post("/{resume_id}/default", response_model=TeacherResumeResponse)
async def set_default_resume(
    resume_id: int,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(TeacherResume, resume_id)
    if not resume or resume.teacher_id != payload.teacher_id:
        raise HTTPException(status_code=404, detail="简历不存在")

    await _unset_default_resumes(db, payload.teacher_id)
    resume.is_default = True
    await db.flush()
    return resume


@router.delete("/{resume_id}")
async def delete_resume(
    resume_id: int,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    resume = await db.get(TeacherResume, resume_id)
    if not resume or resume.teacher_id != payload.teacher_id:
        raise HTTPException(status_code=404, detail="简历不存在")

    was_default = resume.is_default
    await db.delete(resume)
    await db.flush()

    if was_default:
        result = await db.execute(
            select(TeacherResume)
            .where(TeacherResume.teacher_id == payload.teacher_id)
            .order_by(TeacherResume.created_at.desc())
            .limit(1)
        )
        next_resume = result.scalar_one_or_none()
        if next_resume:
            next_resume.is_default = True

    return {"ok": True}
