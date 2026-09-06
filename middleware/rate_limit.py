"""
简单的进程内频率限制（按租户）。

AI 解析每次调用都消耗 DeepSeek token，费用由平台承担。
在接入 Redis 分布式限流之前，先用进程内滑动窗口防止单个中介刷爆账单。
多 worker 部署时应替换为 Redis 实现。
"""
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from config import settings
from middleware.auth import TokenPayload

# key: tenant_id → deque of call timestamps（仅保留最近一分钟）
_calls: dict[int, deque[float]] = defaultdict(deque)

# 登录限流：key 形如 "ip:1.2.3.4|phone:13900000001"
_login_calls: dict[str, deque[float]] = defaultdict(deque)


def check_parse_rate_limit(payload: TokenPayload) -> None:
    """每租户每分钟最多 MAX_PARSE_PER_MINUTE 次 AI 解析；超管不限。"""
    if payload.role == "super_admin":
        return

    key = payload.tenant_id or 0
    now = time.monotonic()
    window_start = now - 60.0

    bucket = _calls[key]
    while bucket and bucket[0] < window_start:
        bucket.popleft()

    if len(bucket) >= settings.MAX_PARSE_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail=f"AI 解析过于频繁，每分钟最多 {settings.MAX_PARSE_PER_MINUTE} 次，请稍后再试",
        )

    bucket.append(now)


def check_login_rate_limit(key: str) -> None:
    """
    登录尝试限流（进程内，按 key 每分钟最多 MAX_LOGIN_PER_MINUTE 次）。
    key 应组合 IP 与账号标识（手机号/邀请码）。多实例部署需替换为 Redis 实现。
    """
    now = time.monotonic()
    window_start = now - 60.0

    bucket = _login_calls[key]
    while bucket and bucket[0] < window_start:
        bucket.popleft()

    if len(bucket) >= settings.MAX_LOGIN_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail=f"尝试过于频繁，每分钟最多 {settings.MAX_LOGIN_PER_MINUTE} 次，请稍后再试",
        )

    bucket.append(now)
