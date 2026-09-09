"""
认证路由：微信登录 + 教员注册 + 开发模式。
"""
import datetime
import secrets
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.domain import Teacher, Tenant, Gender
from models.schemas import (
    WxLoginRequest, TokenResponse, TeacherRegisterRequest, TeacherResponse,
    TeacherProfileUpdate, TenantBrief, PhoneInviteLoginRequest,
    PhoneInviteRegisterRequest, OwnerLoginRequest, TenantLoginRequest,
    PasswordChangeRequest,
)
from services.auth import (
    wx_code2session, create_jwt, hash_password_async, verify_password_async,
)
from services.parser import geocode_address
from middleware.auth import get_current_user, TokenPayload
from middleware.rate_limit import check_login_rate_limit
from config import settings

router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


def _phone_openid(phone: str) -> str:
    return f"phone_{phone}"


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


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
        password_hash=await hash_password_async("dev123456"),
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
    try:
        wx_user = await wx_code2session(body.code)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
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
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    C 端：手机号 + 密码 + 中介邀请码登录。
    手机号未注册时返回 404，由前端引导进入注册表单；密码错误统一返回同一提示。
    """
    await check_login_rate_limit(f"teacher|{_client_ip(request)}|{body.phone}")

    tenant_result = await db.execute(
        select(Tenant).where(Tenant.invite_code == body.invite_code)
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="邀请码无效，请确认中介提供的邀请码")
    if not tenant.is_active:
        # 与 tenant_login 口径一致：停用中介的邀请码不得继续放行教员登录/注册
        raise HTTPException(status_code=403, detail="该中介邀请码已停用")

    result = await db.execute(
        select(Teacher).where(Teacher.phone == body.phone).limit(1)
    )
    teacher = result.scalar_one_or_none()

    if not teacher:
        raise HTTPException(status_code=404, detail="手机号未注册，请先完善教员资料")

    if not teacher.password_hash:
        raise HTTPException(
            status_code=400,
            detail="该账号未设置密码，请使用微信登录或联系中介重置",
        )
    if not await verify_password_async(body.password, teacher.password_hash):
        raise HTTPException(status_code=400, detail="手机号或密码错误")

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
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """C 端：手机号 + 邀请码注册，注册完成后直接登录。"""
    # 注册会写库并触发 bcrypt（CPU 密集），按 IP 限流防脚本批量刷账号
    await check_login_rate_limit(f"teacher-register|{_client_ip(request)}")

    tenant_result = await db.execute(
        select(Tenant).where(Tenant.invite_code == body.invite_code)
    )
    tenant = tenant_result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="邀请码无效，请确认中介提供的邀请码")
    if not tenant.is_active:
        raise HTTPException(status_code=403, detail="该中介邀请码已停用")

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
        password_hash=await hash_password_async(body.password),
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
async def owner_login(body: OwnerLoginRequest, request: Request):
    """老板入口：用于小范围管理中介邀请码。"""
    await check_login_rate_limit(f"owner|{_client_ip(request)}")
    if not secrets.compare_digest(body.access_code, settings.OWNER_ACCESS_CODE):
        raise HTTPException(status_code=403, detail="老板访问码不正确")

    token = create_jwt(sub="super_admin_1", role="super_admin")
    return TokenResponse(token=token, role="super_admin")


@router.post("/tenant-login", response_model=TokenResponse)
async def tenant_login(
    body: TenantLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """中介入口：邀请码 + 密码登录，邀请码由老板创建并启用。"""
    await check_login_rate_limit(f"tenant|{_client_ip(request)}|{body.invite_code}")

    result = await db.execute(
        select(Tenant).where(Tenant.invite_code == body.invite_code)
    )
    tenant = result.scalar_one_or_none()
    if not tenant or not await verify_password_async(body.password, tenant.password_hash):
        # 无效邀请码与密码错误返回同一提示，避免探测有效邀请码
        raise HTTPException(status_code=401, detail="邀请码或密码错误")
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


@router.post("/teacher-change-password")
async def teacher_change_password(
    body: PasswordChangeRequest,
    payload: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """教员修改自己的登录密码。"""
    teacher_id = payload.teacher_id
    if payload.role != "teacher" or teacher_id is None:
        raise HTTPException(status_code=403, detail="仅教员可修改教员密码")

    teacher = await db.get(Teacher, teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="教员不存在")
    if not teacher.password_hash or not await verify_password_async(body.old_password, teacher.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")

    teacher.password_hash = await hash_password_async(body.new_password)
    # 使所有已签发的旧 token 立即失效，强迫重新登录
    teacher.token_valid_after = datetime.datetime.utcnow()
    await db.flush()
    return {"detail": "密码已更新"}


@router.patch("/teacher/profile", response_model=TeacherResponse)
async def update_teacher_profile(
    body: TeacherProfileUpdate,
    payload: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    教员更新基础资料与常驻地；未传字段不修改。
    常驻地文本未带坐标时尝试高德地理编码，编码失败不阻塞保存（距离分退回中性分支）。
    """
    if payload.role != "teacher" or payload.teacher_id is None:
        raise HTTPException(status_code=403, detail="仅教员可编辑教员资料")

    teacher = await db.get(Teacher, payload.teacher_id)
    if not teacher:
        raise HTTPException(status_code=404, detail="教员不存在")

    updates = body.model_dump(exclude_unset=True)
    lng = updates.pop("lng", None)
    lat = updates.pop("lat", None)
    home_area = updates.pop("home_area", None)

    for field, value in updates.items():
        setattr(teacher, field, value)

    if home_area is not None:
        teacher.home_area = home_area.strip() or None
    if teacher.home_area and (lng is None or lat is None) and (teacher.lng is None or teacher.lat is None):
        coords = None
        if settings.AMAP_API_KEY:
            try:
                coords = await geocode_address(teacher.home_area)
            except Exception:
                coords = None
        if coords:
            teacher.lng = Decimal(str(coords[0]))
            teacher.lat = Decimal(str(coords[1]))
    if lng is not None and lat is not None:
        teacher.lng = Decimal(str(lng))
        teacher.lat = Decimal(str(lat))

    await db.flush()
    await db.refresh(teacher)
    return TeacherResponse.model_validate(teacher)


@router.post("/tenant-change-password")
async def tenant_change_password(
    body: PasswordChangeRequest,
    payload: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """中介管理员修改本租户的登录密码。"""
    if payload.role != "tenant_admin" or payload.tenant_id is None:
        raise HTTPException(status_code=403, detail="仅中介管理员可修改中介密码")

    tenant = await db.get(Tenant, payload.tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="中介不存在")
    if not tenant.password_hash or not await verify_password_async(body.old_password, tenant.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")

    tenant.password_hash = await hash_password_async(body.new_password)
    tenant.token_valid_after = datetime.datetime.utcnow()
    await db.flush()
    return {"detail": "密码已更新"}


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
    try:
        wx_user = await wx_code2session(code)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
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
            password_hash=await hash_password_async("dev123456"),
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
async def get_me_profile(    payload: TokenPayload = Depends(get_current_user),
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
