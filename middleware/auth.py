"""
鉴权依赖注入：JWT 解析 + 角色守卫 + 租户隔离。
"""
import calendar
import time
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from services.auth import create_jwt, decode_jwt

security = HTTPBearer()

# token 签发超过该时长后，下一次有效请求换发新 token（滑动续期阈值）
TOKEN_REISSUE_AFTER_HOURS = 24


def _maybe_reissue_token(response, payload: dict, issued_at: int) -> None:
    """活跃用户滑动续期：签发超阈值的有效 token 换发新 token，经响应头下发。
    只在全部鉴权检查通过后调用。"""
    if response is None or not issued_at:
        return
    age = int(time.time()) - issued_at
    if age < TOKEN_REISSUE_AFTER_HOURS * 3600:
        return
    sub, role = payload.get("sub"), payload.get("role")
    if not sub or not role:
        return
    new_token = create_jwt(sub=sub, role=role, tenant_id=payload.get("tid"))
    response.headers["X-Reissued-Token"] = new_token


@dataclass
class TokenPayload:
    sub: str
    role: str
    tenant_id: int | None
    issued_at: int = 0

    @property
    def teacher_id(self) -> int | None:
        if self.sub.startswith("teacher_"):
            try:
                return int(self.sub.split("_", 1)[1])
            except ValueError:
                # 畸形 sub（历史脏数据/手工签发）按未认证处理而非 500
                return None
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
    # FastAPI 对 Response 注解参数自动注入实例；带默认值仅为满足"无默认参数不可跟在默认参数后"的语法
    response: Response = None,
) -> TokenPayload:
    """
    解析 JWT 获取当前用户。
    所有需登录的接口注入此依赖；中介账号每请求回查启用状态，
    保证停用后已签发 token 立即失效。

    滑动续期：token 签发超过 TOKEN_REISSUE_AFTER_HOURS 且仍有效时，
    通过 X-Reissued-Token 响应头下发新 token（前端静默接管）。
    活跃用户不再每 72h 被突然踢回登录页丢表单；不活跃用户过期口径不变。
    不引入 refresh token 体系（无独立刷新端点、无长期凭证存储面）。
    """
    try:
        payload = decode_jwt(credentials.credentials)
    except InvalidTokenError as e:
        raise HTTPException(status_code=401, detail="Token 无效或已过期") from e

    sub = payload.get("sub")
    role = payload.get("role")
    if not sub or not role:
        raise HTTPException(status_code=401, detail="Token 载荷不完整")

    tenant_id = payload.get("tid")
    issued_at = int(payload.get("iat") or 0)

    if role == "tenant_admin":
        if tenant_id is None:
            raise HTTPException(status_code=403, detail="未关联租户，无法操作")
        from models.domain import Tenant
        tenant = await db.get(Tenant, tenant_id)
        if tenant is None:
            raise HTTPException(status_code=403, detail="该中介不存在")
        if not tenant.is_active:
            raise HTTPException(status_code=403, detail="该中介账号已被停用，请联系平台")
        _reject_stale_token(tenant.token_valid_after, issued_at)

    elif role == "teacher":
        from models.domain import Teacher
        if sub.startswith("teacher_"):
            try:
                teacher_pk = int(sub.split("_", 1)[1])
            except ValueError as e:
                raise HTTPException(status_code=401, detail="Token 载荷不完整") from e
            teacher = await db.get(Teacher, teacher_pk)
            if teacher is not None:
                # 先查 token 失效再查封禁：注销/改密场景保持 401 契约（前端静默登出），
                # 封禁且持有有效 token 的教员才落 403。
                # 封禁在鉴权层整体拦截：否则被封教员重新登录拿到新 token 后，
                # 仍可走 address-unlock 等未单独检查 is_banned 的接口
                _reject_stale_token(teacher.token_valid_after, issued_at)
                if teacher.is_banned:
                    raise HTTPException(status_code=403, detail="账号已被平台限制，请联系客服")

    elif role == "super_admin":
        # 老板 token 无账号行可挂 token_valid_after：用全局配置时间戳吊销
        # （轮换 OWNER_ACCESS_CODE 时同步设置即可失效存量老板会话）
        from config import settings
        if settings.OWNER_TOKEN_VALID_AFTER is not None:
            _reject_stale_token_by_ts(settings.OWNER_TOKEN_VALID_AFTER, issued_at)

    # 滑动续期放在所有安全检查之后：被封禁/停用/吊销的请求绝不能拿到续期 token
    _maybe_reissue_token(response, payload, issued_at)

    return TokenPayload(
        sub=sub,
        role=role,
        tenant_id=tenant_id,
        issued_at=issued_at,
    )


def _reject_stale_token(token_valid_after, issued_at: int) -> None:
    """改密/重置后签发时间早于 token_valid_after 的 token 立即作废。"""
    if token_valid_after is None:
        return
    _reject_stale_token_by_ts(token_valid_after, issued_at)


def _reject_stale_token_by_ts(token_valid_after, issued_at: int) -> None:
    if token_valid_after is None:
        return
    # 库中统一存 naive UTC（MySQL 会话时区已固定 +00:00），
    # 必须按 UTC 解释为 epoch，不能用 timestamp()（按本地时区解释会误杀）。
    # 比较用 <=：同秒内签发的 token 与改密时刻无法区分，一并吊销（宁可多踢一次登录）
    valid_after_ts = calendar.timegm(token_valid_after.timetuple())
    if issued_at <= valid_after_ts:
        raise HTTPException(status_code=401, detail="凭证已失效，请重新登录")


def require_role(*roles: str):
    """
    角色守卫工厂。
    用法: Depends(require_role("tenant_admin", "super_admin"))
    """
    async def checker(payload: TokenPayload = Depends(get_current_user)) -> TokenPayload:
        if payload.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"权限不足：需要角色 {'/'.join(roles)}",
            )
        return payload

    return checker


def require_tenant_owner():
    """
    租户隔离守卫：确保 B 端用户只能操作自己的数据。
    仅在 TokenPayload.tenant_id 存在时生效。
    """
    async def checker(
        payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    ) -> TokenPayload:
        if payload.role != "super_admin" and payload.tenant_id is None:
            raise HTTPException(status_code=403, detail="未关联租户，无法操作")
        return payload

    return checker


def assert_tenant_scope(payload: TokenPayload, tenant_id: int | None, *, detail: str = "资源不存在") -> None:
    """
    租户隔离守卫：非超管访问他租户资源一律 404（与"不存在"同响应，不泄露资源存在性）。
    detail 由调用方传入资源口径（如"订单不存在"），保持各路由历史文案。
    """
    if payload.role != "super_admin" and tenant_id != payload.tenant_id:
        raise HTTPException(status_code=404, detail=detail)


def tenant_scoped(query, payload: TokenPayload, tenant_column):
    """
    查询租户过滤：仅 super_admin 不过滤；其余按 tenant_column == payload.tenant_id 收窄。
    tenant_admin 携带 tid=None 的异常 token 时不再放行全量（过滤为 NULL 集合，返回空列表）。
    """
    if payload.role == "super_admin":
        return query
    return query.where(tenant_column == payload.tenant_id)
