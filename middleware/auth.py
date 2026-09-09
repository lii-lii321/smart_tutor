"""
鉴权依赖注入：JWT 解析 + 角色守卫 + 租户隔离。
"""
import calendar
from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from services.auth import decode_jwt

security = HTTPBearer()


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
) -> TokenPayload:
    """
    解析 JWT 获取当前用户。
    所有需登录的接口注入此依赖；中介账号每请求回查启用状态，
    保证停用后已签发 token 立即失效。
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
                _reject_stale_token(teacher.token_valid_after, issued_at)

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
    # 库中统一存 naive UTC（MySQL 会话时区已固定 +00:00），
    # 必须按 UTC 解释为 epoch，不能用 timestamp()（按本地时区解释会误杀）
    valid_after_ts = calendar.timegm(token_valid_after.timetuple())
    if issued_at < valid_after_ts:
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
    查询租户过滤：超管不过滤；无租户 token 不在此处拦截（上游守卫负责），
    其余按 tenant_column == payload.tenant_id 收窄。
    """
    if payload.role == "super_admin":
        return query
    if payload.tenant_id is None:
        return query
    return query.where(tenant_column == payload.tenant_id)
