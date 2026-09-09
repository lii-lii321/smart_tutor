"""
认证服务：JWT 签发/校验 + 密码哈希 + 微信 code2session。
"""
import asyncio
import time
import bcrypt
import httpx
import jwt
from config import settings


async def hash_password_async(plain: str) -> str:
    """bcrypt 哈希。CPU 密集（单次约百毫秒），放线程池执行避免阻塞事件循环。"""
    return await asyncio.to_thread(hash_password, plain)


def hash_password(plain: str) -> str:
    """bcrypt 哈希。截断 72 字节是 bcrypt 算法本身的输入上限。"""
    return bcrypt.hashpw(plain.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


async def verify_password_async(plain: str, hashed: str | None) -> bool:
    return await asyncio.to_thread(verify_password, plain, hashed)


def verify_password(plain: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8")[:72], hashed.encode("utf-8"))
    except ValueError:
        return False


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
    """校验并解码 JWT。无效时抛出 PyJWT 的 InvalidTokenError。"""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


async def wx_code2session(code: str) -> dict:
    """
    微信 code2session 接口。
    返回 {"openid": "...", "session_key": "...", "unionid": "..."}
    网络/配置问题统一转为 ValueError，由路由层映射为业务错误而非 500。
    """
    if not settings.WX_APPID or not settings.WX_SECRET:
        raise ValueError("微信登录未配置，请使用手机号登录")
    try:
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
    except httpx.HTTPError:
        raise ValueError("微信服务暂不可用，请稍后再试")
    if "errcode" in data and data["errcode"] != 0:
        raise ValueError(f"微信登录失败: {data.get('errmsg', 'unknown error')}")
    return data
