"""
频率限制：优先 Redis（多 worker/多实例共享），Redis 不可用时降级进程内计数。

- AI 解析限流：按租户，防刷爆 DeepSeek 账单；
- AI 助手限流：按租户，找单/问答共用入口；
- 登录限流：按 IP+账号，防密码爆破；
- 公开橱窗限流：按 IP，防爬虫批量扒中介订单资产。
"""

import datetime
import logging
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from config import settings

logger = logging.getLogger(__name__)

# 进程内降级计数（仅 Redis 不可用时使用，多实例下只保护单进程）
_parse_calls: dict[int, deque[float]] = defaultdict(deque)
_ai_query_calls: dict[int, deque[float]] = defaultdict(deque)
_login_calls: dict[str, deque[float]] = defaultdict(deque)
_public_calls: dict[str, deque[float]] = defaultdict(deque)
_teacher_daily_calls: dict[int, deque[float]] = defaultdict(deque)
_tenant_daily_calls: dict[int, deque[float]] = defaultdict(deque)

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


async def _redis_hit(
    key: str, limit: int, window_seconds: int, now: float | None = None
) -> bool | None:
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


async def check_ai_query_rate_limit(payload) -> None:
    """每租户每分钟最多 MAX_AI_QUERY_PER_MINUTE 次 AI 助手调用；超管不限。"""
    if payload.role == "super_admin":
        return

    tenant_key = payload.tenant_id or 0
    limit = settings.MAX_AI_QUERY_PER_MINUTE

    hit = await _redis_hit(f"aiqa:{tenant_key}", limit, 60)
    if hit is not None:
        if hit:
            raise HTTPException(
                status_code=429,
                detail=f"AI 助手调用过于频繁，每分钟最多 {limit} 次，请稍后再试",
            )
        return

    # Redis 不可用：进程内滑动窗口兜底
    now = time.monotonic()
    window_start = now - 60.0
    _purge_stale(_ai_query_calls, window_start)
    bucket = _ai_query_calls[tenant_key]
    _trim(bucket, window_start)
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"AI 助手调用过于频繁，每分钟最多 {limit} 次，请稍后再试",
        )
    bucket.append(now)


def _beijing_day() -> str:
    """日配额按北京时间自然日重置：用户全在国内，UTC 桶会让额度早上 8 点才回满。"""
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime(
        "%Y%m%d"
    )


async def check_teacher_ai_daily_quota(payload, *, now: float | None = None) -> None:
    """
    教员 AI 找单每日配额（获客成本闸门）：教员侧 AI 搜索烧平台 token，
    按"每教员 / 每租户全体教员"双层日限额封顶，配额北京时间自然日重置。

    与分钟级限流的差异：这里是成本上限而非防刷——超限文案引导订阅推送，
    而不是"稍后再试"。Redis 不可用时降级进程内计数（近似滑动 24h 窗口，
    与分钟级降级同款口径；降级期只会更严不会更松）。
    """
    teacher_key = payload.teacher_id or 0
    tenant_key = payload.tenant_id or 0
    teacher_limit = settings.TEACHER_AI_DAILY_LIMIT
    tenant_limit = settings.TENANT_AI_DAILY_LIMIT
    day = _beijing_day()
    teacher_msg = (
        f"今日 AI 找单次数已用完（每人每天 {teacher_limit} 次），明天再来；"
        "设置订阅偏好后，新单会自动推送给你"
    )
    tenant_msg = f"本中介今日教员 AI 找单总次数已用完（每天 {tenant_limit} 次），明天恢复"

    hit_teacher = await _redis_hit(f"aiqday:t:{teacher_key}:{day}", teacher_limit, 172800, now=now)
    if hit_teacher:
        raise HTTPException(status_code=429, detail=teacher_msg)
    hit_tenant = None
    if hit_teacher is not None:
        hit_tenant = await _redis_hit(
            f"aiqday:tn:{tenant_key}:{day}", tenant_limit, 172800, now=now
        )
        if hit_tenant:
            raise HTTPException(status_code=429, detail=tenant_msg)
    if hit_teacher is not None and hit_tenant is not None:
        return  # 双桶均由 Redis 正常计数

    # 任一桶 Redis 不可用：进程内按自然日附近近似（滑动 24h）兜底
    now_ts = time.time() if now is None else now
    window_start = now_ts - 86400.0
    _purge_stale(_teacher_daily_calls, window_start)
    bucket = _teacher_daily_calls[teacher_key]
    _trim(bucket, window_start)
    if len(bucket) >= teacher_limit:
        raise HTTPException(status_code=429, detail=teacher_msg)
    bucket.append(now_ts)

    _purge_stale(_tenant_daily_calls, window_start)
    bucket = _tenant_daily_calls[tenant_key]
    _trim(bucket, window_start)
    if len(bucket) >= tenant_limit:
        raise HTTPException(status_code=429, detail=tenant_msg)
    bucket.append(now_ts)


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


def _client_ip(request: Request) -> str:
    """与 services/audit.client_ip_from 同口径：生产经 nginx 覆写 X-Real-IP，本地回退 socket 地址。"""
    forwarded = request.headers.get("x-real-ip")
    if forwarded:
        return forwarded.strip()[:45]
    return request.client.host if request.client else "unknown"


async def check_public_rate_limit(request: Request, *, now: float | None = None) -> None:
    """公开橱窗接口限流（每 IP 每分钟最多 MAX_PUBLIC_PER_MINUTE 次）。

    无鉴权数据面是中介订单资产的唯一敞口，按 IP 兜底防爬；超限 429 文案
    对真人友好（正常浏览远达不到该量级，触发者基本是脚本）。
    now 仅供测试注入固定时钟（与 login 同款，防跨秒分桶假阴性）。
    """
    limit = settings.MAX_PUBLIC_PER_MINUTE
    ip = _client_ip(request)

    hit = await _redis_hit(f"public:{ip}", limit, 60, now=now)
    if hit is not None:
        if hit:
            raise HTTPException(
                status_code=429,
                detail="访问过于频繁，请稍后再试",
            )
        return

    now = time.monotonic()
    window_start = now - 60.0
    _purge_stale(_public_calls, window_start)
    bucket = _public_calls[ip]
    _trim(bucket, window_start)
    if len(bucket) >= limit:
        raise HTTPException(
            status_code=429,
            detail="访问过于频繁，请稍后再试",
        )
    bucket.append(now)
