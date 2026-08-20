"""
认证服务：JWT 签发/校验 + 微信 code2session。
"""
import time
import httpx
from jose import jwt, JWTError
from config import settings


def create_jwt(*, sub: str, role: str, tenant_id: int | None = None) -> str:
    """签发 JWT。"""
    now = int(time.time())
    payload = {
        "sub": sub,
        "role": role,
        "tid": tenant_id,
        "iat": now,
        "exp": now + settings.JWT_EXPIRE_HOURS * 3600,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_jwt(token: str) -> dict:
    """校验并解码 JWT。无效时抛出 JWTError。"""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


async def wx_code2session(code: str) -> dict:
    """
    微信 code2session 接口。
    返回 {"openid": "...", "session_key": "...", "unionid": "..."}
    """
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/sns/jscode2session",
            params={
                "appid": settings.WX_APPID,
                "secret": settings.WX_SECRET,
                "js_code": code,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if "errcode" in data and data["errcode"] != 0:
            raise ValueError(f"微信登录失败: {data.get('errmsg', 'unknown error')}")
        return data
