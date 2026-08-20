"""
认证路由：微信登录 + 教员注册 + 开发模式。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.domain import Teacher, Tenant, Gender
from models.schemas import (
    WxLoginRequest, TokenResponse, TeacherRegisterRequest, TeacherResponse,
    TenantBrief, PhoneInviteLoginRequest, PhoneInviteRegisterRequest,
    OwnerLoginRequest, TenantLoginRequest,
)
from services.auth import wx_code2session, create_jwt
from middleware.auth import get_current_user, TokenPayload
from config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


def _phone_openid(phone: str) -> str:
    return f"phone_{phone}"


@router.post("/dev-login", response_model=TokenResponse)
async def dev_login(openid: str = "dev_test_001", db: AsyncSession = Depends(get_db)):
    """
    开发模式：直接用 openid 登录，跳过微信 OAuth。
    生产环境请关闭 config.DEV_MODE。
    """
    if not settings.DEV_MODE:
        raise HTTPException(status_code=403, detail="开发模式未开启")

    result = await db.execute(select(Teacher).where(Teacher.openid == openid))
    teacher = result.scalar_one_or_none()

    if not teacher:
        raise HTTPException(status_code=404, detail="未注册教员，请先调用 /dev-register")

    token = create_jwt(sub=f"teacher_{teacher.id}", role="teacher")
    return TokenResponse(
        token=token,
        role="teacher",
        teacher=TeacherResponse.model_validate(teacher),
    )


@router.post("/dev-register", response_model=TokenResponse)
async def dev_register(
    openid: str = "dev_test_001",
    name: str = "测试教员",
    gender: Gender = Gender.male,
    phone: str = "13800000001",
    db: AsyncSession = Depends(get_db),
):
    """开发模式：快速注册测试教员。"""
    if not settings.DEV_MODE:
        raise HTTPException(status_code=403, detail="开发模式未开启")

    existing = await db.execute(select(Teacher).where(Teacher.openid == openid))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该 openid 已注册")

    teacher = Teacher(
        openid=openid,
        name=name,
        gender=gender,
        phone=phone,
        wechat_id=f"wxid_{openid}",
        school="测试大学",
        is_985_211=True,
        is_985=True,
        is_211=True,
        is_double_first_class=True,
        major="计算机科学",
        grade="研二",
        highlights="测试账号",
    )
    db.add(teacher)
    await db.flush()

    token = create_jwt(sub=f"teacher_{teacher.id}", role="teacher")
    return TokenResponse(
        token=token,
        role="teacher",
        teacher=TeacherResponse.model_validate(teacher),
    )


@router.post("/teacher-login", response_model=TokenResponse)
async def teacher_login(body: WxLoginRequest, db: AsyncSession = Depends(get_db)):
    """C 端：微信 code 换取 JWT。未注册用户返回 404。"""
    wx_user = await wx_code2session(body.code)
    openid = wx_user["openid"]

    result = await db.execute(select(Teacher).where(Teacher.openid == openid))
    teacher = result.scalar_one_or_none()

    if not teacher:
        raise HTTPException(status_code=404, detail="未注册教员，请先完成注册")

    token = create_jwt(sub=f"teacher_{teacher.id}", role="teacher")
    return TokenResponse(
        token=token,
        role="teacher",
        teacher=TeacherResponse.model_validate(teacher),
    )


@router.post("/teacher-phone-login", response_model=TokenResponse)
async def teacher_phone_login(
    body: PhoneInviteLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    C 端：手机号 + 中介邀请码登录。
    小范围使用阶段不发短信验证码；手机号未注册时提示前端跳转注册表单。
    """
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.invite_code == body.invite_code)
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="邀请码无效，请确认中介提供的邀请码")

    result = await db.execute(
        select(Teacher).where(Teacher.phone == body.phone).limit(1)
    )
    teacher = result.scalar_one_or_none()

    if not teacher:
        raise HTTPException(status_code=404, detail="手机号未注册，请先完善教员资料")

    token = create_jwt(sub=f"teacher_{teacher.id}", role="teacher")
    return TokenResponse(
        token=token,
        role="teacher",
        teacher=TeacherResponse.model_validate(teacher),
        tenant=TenantBrief.model_validate(tenant),
    )


@router.post("/teacher-phone-register", response_model=TokenResponse)
async def teacher_phone_register(
    body: PhoneInviteRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """C 端：手机号 + 邀请码注册，注册完成后直接登录。"""
    tenant_result = await db.execute(
        select(Tenant).where(Tenant.invite_code == body.invite_code)
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="邀请码无效，请确认中介提供的邀请码")

    existing = await db.execute(
        select(Teacher).where(Teacher.phone == body.phone).limit(1)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该手机号已注册，请直接登录")

    teacher = Teacher(
        openid=_phone_openid(body.phone),
        name=body.name,
        gender=body.gender,
        phone=body.phone,
        wechat_id=body.wechat_id,
        school=body.school,
        is_985_211=body.is_985 or body.is_211 or body.is_985_211,
        is_985=body.is_985,
        is_211=body.is_211,
        is_double_first_class=body.is_double_first_class,
        major=body.major,
        grade=body.grade,
        highlights=body.highlights,
    )
    db.add(teacher)
    await db.flush()

    token = create_jwt(sub=f"teacher_{teacher.id}", role="teacher")
    return TokenResponse(
        token=token,
        role="teacher",
        teacher=TeacherResponse.model_validate(teacher),
        tenant=TenantBrief.model_validate(tenant),
    )


@router.post("/owner-login", response_model=TokenResponse)
async def owner_login(body: OwnerLoginRequest):
    """老板入口：用于小范围管理中介邀请码。"""
    if body.access_code != settings.OWNER_ACCESS_CODE:
        raise HTTPException(status_code=403, detail="老板访问码不正确")

    token = create_jwt(sub="super_admin_1", role="super_admin")
    return TokenResponse(token=token, role="super_admin")


@router.post("/tenant-login", response_model=TokenResponse)
async def tenant_login(body: TenantLoginRequest, db: AsyncSession = Depends(get_db)):
    """中介入口：只能使用老板已创建且启用的邀请码登录。"""
    result = await db.execute(
        select(Tenant).where(Tenant.invite_code == body.invite_code)
    )
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="邀请码无效，请联系平台老板开通")
    if not tenant.is_active:
        raise HTTPException(status_code=403, detail="该中介邀请码已停用")

    token = create_jwt(
        sub=f"tenant_admin_{tenant.id}", role="tenant_admin", tenant_id=tenant.id
    )
    return TokenResponse(
        token=token,
        role="tenant_admin",
        tenant=TenantBrief.model_validate(tenant),
    )


@router.post("/teacher-register", response_model=TokenResponse)
async def teacher_register(
    body: TeacherRegisterRequest,
    code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    C 端：微信注册。
    前端先调 wx.login() 获取 code，连同注册表单一起提交。
    """
    wx_user = await wx_code2session(code)
    openid = wx_user["openid"]

    existing = await db.execute(select(Teacher).where(Teacher.openid == openid))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="该微信已注册，请直接登录")

    teacher = Teacher(
        openid=openid,
        name=body.name,
        gender=body.gender,
        phone=body.phone,
        wechat_id=body.wechat_id,
        school=body.school,
        is_985_211=body.is_985 or body.is_211 or body.is_985_211,
        is_985=body.is_985,
        is_211=body.is_211,
        is_double_first_class=body.is_double_first_class,
        major=body.major,
        grade=body.grade,
        highlights=body.highlights,
        lng=body.lng,
        lat=body.lat,
    )
    db.add(teacher)
    await db.flush()

    token = create_jwt(sub=f"teacher_{teacher.id}", role="teacher")
    return TokenResponse(
        token=token,
        role="teacher",
        teacher=TeacherResponse.model_validate(teacher),
    )


@router.post("/dev-tenant", response_model=TokenResponse)
async def dev_tenant(
    invite_code: str = "tx886",
    tenant_name: str = "测试中介",
    db: AsyncSession = Depends(get_db),
):
    """开发模式：创建测试租户并返回 B 端 admin token。"""
    if not settings.DEV_MODE:
        raise HTTPException(status_code=403, detail="开发模式未开启")

    existing = await db.execute(
        select(Tenant).where(Tenant.invite_code == invite_code)
    )
    tenant = existing.scalar_one_or_none()

    if not tenant:
        tenant = Tenant(
            tenant_name=tenant_name,
            invite_code=invite_code,
            contact_wechat="wxid_test_agent",
        )
        db.add(tenant)
        await db.flush()

    token = create_jwt(
        sub=f"tenant_admin_{tenant.id}", role="tenant_admin", tenant_id=tenant.id
    )
    return TokenResponse(
        token=token,
        role="tenant_admin",
        tenant=TenantBrief.model_validate(tenant),
    )


@router.get("/me/profile")
async def get_me_profile(
    payload: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    response = {"sub": payload.sub, "role": payload.role, "tenant_id": payload.tenant_id}

    if payload.role == "teacher" and payload.sub.startswith("teacher_"):
        teacher_id = int(payload.sub.replace("teacher_", "", 1))
        result = await db.execute(select(Teacher).where(Teacher.id == teacher_id))
        teacher = result.scalar_one_or_none()
        if not teacher:
            raise HTTPException(status_code=404, detail="教员不存在")
        response["teacher"] = TeacherResponse.model_validate(teacher)

    if payload.role == "tenant_admin" and payload.tenant_id:
        result = await db.execute(select(Tenant).where(Tenant.id == payload.tenant_id))
        tenant = result.scalar_one_or_none()
        if tenant:
            response["tenant"] = TenantBrief.model_validate(tenant)

    return response


@router.get("/me")
async def get_me(payload: TokenPayload = Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return {"sub": payload.sub, "role": payload.role, "tenant_id": payload.tenant_id}
