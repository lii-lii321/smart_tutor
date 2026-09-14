"""
Redis 真实路径回归测试（fakeredis，第 5 阶段）。

此前测试环境无 Redis，以下代码只走过进程内降级分支、从未被验证：
- services/geo 的 GEO 写入/查询/惰性重建/空租户标记；
- middleware/rate_limit 的 Redis 固定窗口计数；
- services/scheduler 的分布式调度锁；
- order_maintenance 的看板缓存失效与过期归档的 GEO 清理。

运行方式：
    pytest tests/test_redis_paths.py
"""
import datetime

import pytest
from conftest import make_order, make_tenant
from fakeredis import aioredis as fakeredis_aioredis
from fastapi import HTTPException

import services.order_maintenance as order_maintenance
from models.domain import Order, OrderStatus
from services.geo import (
    batch_sync_to_redis,
    ensure_geo_cache,
    query_all_active,
    remove_from_redis,
)


@pytest.fixture()
async def fake_redis(monkeypatch):
    """把全局 Redis 单例替换为 fakeredis，使 get_redis_client 的所有调用方走真实 Redis 协议。"""
    redis = fakeredis_aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(order_maintenance, "_redis_client", redis)
    yield redis
    await redis.flushall()
    await redis.aclose()


async def test_geo_batch_sync_query_and_remove(fake_redis, db):
    tenant = await make_tenant(db, "rdt0001")
    o1 = await make_order(db, tenant.id, "RD-001", lng=104.06, lat=30.65)
    o2 = await make_order(db, tenant.id, "RD-002", lng=104.10, lat=30.66)
    await db.commit()

    await batch_sync_to_redis([o1, o2], fake_redis)
    members = await query_all_active(tenant.id, fake_redis)
    assert {m["order_id"] for m in members} == {o1.id, o2.id}
    for m in members:
        assert 103.0 < m["lng"] < 106.0
        assert 29.0 < m["lat"] < 32.0

    await remove_from_redis(tenant.id, o1.id, fake_redis)
    members = await query_all_active(tenant.id, fake_redis)
    assert {m["order_id"] for m in members} == {o2.id}


async def test_geo_ensure_cache_rebuilds_and_marks_empty(fake_redis, db):
    tenant = await make_tenant(db, "rdt0002")
    order = await make_order(db, tenant.id, "RD-101")
    await db.commit()

    # key 不存在 → 从 MySQL 惰性重建
    await ensure_geo_cache(tenant.id, db, fake_redis)
    members = await query_all_active(tenant.id, fake_redis)
    assert {m["order_id"] for m in members} == {order.id}

    # key 存在时幂等短路：DB 新增订单也不会被立即重建进缓存（惰性策略的语义）
    other = await make_order(db, tenant.id, "RD-102")
    await db.commit()
    await ensure_geo_cache(tenant.id, db, fake_redis)
    members = await query_all_active(tenant.id, fake_redis)
    assert {m["order_id"] for m in members} == {order.id}

    # 空租户 → 写短 TTL 空标记，避免每次请求回源 MySQL
    empty_tenant = await make_tenant(db, "rdt0003")
    await db.commit()
    await ensure_geo_cache(empty_tenant.id, db, fake_redis)
    assert await fake_redis.exists(f"smart_tutor:orders:geo:{empty_tenant.id}") == 0
    ttl = await fake_redis.ttl(f"smart_tutor:orders:geo:{empty_tenant.id}:empty")
    assert 0 < ttl <= 120


async def test_login_rate_limit_uses_redis_window(fake_redis):
    from middleware.rate_limit import check_login_rate_limit

    key = "rd-limit|case1"
    for _ in range(10):
        await check_login_rate_limit(key)  # 前 10 次放行

    with pytest.raises(HTTPException) as exc_info:
        await check_login_rate_limit(key)
    assert exc_info.value.status_code == 429

    # 计数确实落在 Redis（多 worker 共享），而不是进程内字典
    keys = await fake_redis.keys("rate:login:rd-limit|case1:*")
    assert keys, "限流计数应写入 Redis"


async def test_scheduler_lock_shared_via_redis(fake_redis):
    from services.scheduler import _acquire_schedule_lock

    first = await _acquire_schedule_lock(ttl_seconds=60)
    second = await _acquire_schedule_lock(ttl_seconds=60)
    assert first is True
    assert second is False, "同一 TTL 窗口内第二个调度方不得重复执行"
    ttl = await fake_redis.ttl("smart_tutor:scheduler:order_maintenance")
    assert 0 < ttl <= 60


async def test_board_cache_invalidation(fake_redis):
    await fake_redis.set(order_maintenance.board_cache_key(7), "payload")
    await fake_redis.set(order_maintenance.board_cache_key(8), "payload")

    await order_maintenance.invalidate_board_cache(7, None, 8)

    assert await fake_redis.exists(order_maintenance.board_cache_key(7)) == 0
    assert await fake_redis.exists(order_maintenance.board_cache_key(8)) == 0


async def test_archive_expired_removes_geo_members(fake_redis, db):
    tenant = await make_tenant(db, "rdt0004")
    expired = Order(
        tenant_id=tenant.id, raw_id="RD-201", raw_text="过期订单",
        grade_subject="初三数学", requirements="", price_total="200/次",
        base_price=200.0, weekly_frequency=2, is_summer_vacation=False,
        calculated_info_fee=200.0, deposit_amount=100.0, balance_amount=100.0,
        fuzzy_address="成都市天府大道", lng=104.06, lat=30.65,
        status=OrderStatus.recruiting,
        expired_at=datetime.datetime.utcnow() - datetime.timedelta(hours=1),
    )
    db.add(expired)
    await db.commit()

    await batch_sync_to_redis([expired], fake_redis)
    assert await query_all_active(tenant.id, fake_redis)

    count = await order_maintenance.archive_expired_recruiting_orders(db)
    assert count == 1
    members = await query_all_active(tenant.id, fake_redis)
    assert members == [], "过期归档后坐标必须从地图索引移除"
