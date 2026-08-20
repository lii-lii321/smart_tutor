"""
鉴权依赖注入：JWT 解析 + 角色守卫 + 租户隔离。
"""
from dataclasses import dataclass
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from services.auth import decode_jwt

security = HTTPBearer()


@dataclass
class TokenPayload:
    sub: str
    role: str
    tenant_id: int | None

    @property
    def teacher_id(self) -> int | None:
        if self.sub.startswith("teacher_"):
            return int(self.sub.split("_", 1)[1])
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    """
    解析 JWT 获取当前用户。
    所有需登录的接口注入此依赖。
    """
    try:
        payload = decode_jwt(credentials.credentials)
    except JWTError:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    sub = payload.get("sub")
    role = payload.get("role")
    if not sub or not role:
        raise HTTPException(status_code=401, detail="Token 载荷不完整")

    return TokenPayload(
        sub=sub,
        role=role,
        tenant_id=payload.get("tid"),
    )


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
