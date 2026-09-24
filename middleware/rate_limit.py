"""
频率限制：优先 Redis（多 worker/多实例共享），Redis 不可用时降级进程内计数。

- AI 解析限流：按租户，防刷爆 DeepSeek 账单；
- 登录限流：按 IP+账号，防密码爆破。
"""
import logging
import time
from collections import defaultdict, deque

from fastapi import HTTPException

from config import settings

logger = logging.getLogger(__name__)

# 进程内降级计数（仅 Redis 不可用时使用，多实例下只保护单进程）
_parse_calls: dict[int, deque[float]] = defaultdict(deque)
_login_calls: dict[str, deque[float]] = defaultdict(deque)

# Redis 降级告警节流：降级期间每个窗口最多告警一次，避免高频请求刷爆日志
_DEGRADE_LOG_INTERVAL = 300.0
_last_degrade_log = 0.0


def _log_degrade_once() -> None:
    """Redis 不可用降级进程内限流时告警：此时限流按进程数放大、防护打折，必须可观测。"""
    global _last_degrade_log
    now = time.monotonic()
    if now - _last_degrade_log < _DEGRADE_LOG_INTERVAL:
        return
    _last_degrade_log = now
    logger.critical(
        "限流降级：Redis 不可用，已退化为进程内计数（多 worker/多实例下防护按进程数放大）；"
        "请尽快检查 Redis 连接",
        exc_info=True,
    )


async def _redis_hit(key: str, limit: int, window_seconds: int, now: float | None = None) -> bool | None:
    """
    用 Redis 固定窗口计数；返回 None 表示 Redis 不可用（调用方降级）。
    now 仅供测试注入固定时钟：固定窗口按秒取整分桶，真实时钟下测试调用
    跨过窗口秒边界会把计数分到两个桶，导致"超限不触发"的偶发假阴性。
    """
    try:
        from services.order_maintenance import get_redis_client
        redis = await get_redis_client()
        bucket = f"rate:{key}:{int(now if now is not None else time.time()) // window_seconds}"
        # INCR 与 EXPIRE 原子提交，避免进程在两步之间崩溃留下永不过期的计数 key
        pipe = redis.pipeline()
        pipe.incr(bucket)
        pipe.expire(bucket, window_seconds)
        count = (await pipe.execute())[0]
        return count > limit
    except Exception:
        _log_degrade_once()
        return None


def _trim(bucket: deque, window_start: float) -> None:
    while bucket and bucket[0] < window_start:
        bucket.popleft()


def _purge_stale(store: dict, window_start: float, max_keys: int = 4096) -> None:
    """进程内兜底字典按账号无限增长，超阈值时清掉窗口外的空/过期 key。"""
    if len(store) <= max_keys:
        return
    for key in [k for k, b in store.items() if not b or b[0] < window_start]:
        store.pop(key, None)


async def check_parse_rate_limit(payload) -> None:
    """每租户每分钟最多 MAX_PARSE_PER_MINUTE 次 AI 解析；超管不限。"""
    if payload.role == "super_admin":
        return

    tenant_key = payload.tenant_id or 0
    limit = settings.MAX_PARSE_PER_MINUTE

    hit = await _redis_hit(f"parse:{tenant_key}", limit, 60)
    if hit is not None:
        if hit:
            raise HTTPException(
                status_code=429,
                detail=f"AI 解析过于频繁，每分钟最多 {limit} 次，请稍后再试",
            )
        return

    # Redis 不可用：进程内滑动窗口兜底
    now = time.monotonic()
    window_start = now - 60.0
    _purge_stale(_parse_calls, window_start)
    bucket = _parse_calls[tenant_key]
    _trim(bucket, window_start)
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"AI 解析过于频繁，每分钟最多 {limit} 次，请稍后再试",
        )
    bucket.append(now)


async def check_login_rate_limit(key: str, *, now: float | None = None) -> None:
    """
    登录尝试限流（每 key 每分钟最多 MAX_LOGIN_PER_MINUTE 次）。
    key 应组合 IP 与账号标识（手机号/邀请码）。now 仅供测试注入固定时钟。
    """
    limit = settings.MAX_LOGIN_PER_MINUTE

    hit = await _redis_hit(f"login:{key}", limit, 60, now=now)
    if hit is not None:
        if hit:
            raise HTTPException(
                status_code=429,
                detail=f"尝试过于频繁，每分钟最多 {limit} 次，请稍后再试",
            )
        return

    now = time.monotonic()
    window_start = now - 60.0
    _purge_stale(_login_calls, window_start)
    bucket = _login_calls[key]
    _trim(bucket, window_start)
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"尝试过于频繁，每分钟最多 {limit} 次，请稍后再试",
        )
    bucket.append(now)
