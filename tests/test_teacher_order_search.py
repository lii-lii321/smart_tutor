"""
教员端 AI 找单测试：跨租户口径、教员脱敏、拉黑/已投递排除、常驻地距离。
运行：pytest tests/test_teacher_order_search.py
"""

import datetime

from conftest import make_order, make_teacher, make_tenant

from middleware.auth import TokenPayload
from models.domain import Application, TenantTeacherBlacklist
from services.teacher_order_search import find_orders_for_teacher
from utils.clock import utcnow


def _teacher_payload(teacher_id: int) -> TokenPayload:
    return TokenPayload(sub=f"teacher_{teacher_id}", role="teacher", tenant_id=None, issued_at=0)


async def _set_teacher_location(teacher, lng: float, lat: float) -> None:
    from decimal import Decimal

    teacher.lng = Decimal(str(lng))
    teacher.lat = Decimal(str(lat))


async def test_teacher_find_cross_tenant_and_sanitized(db):
    """教员跨租户找单：命中两个租户的单，payload 为教员脱敏口径（坐标降精度）。"""
    t1 = await make_tenant(db, "tfs_a")
    t2 = await make_tenant(db, "tfs_b")
    teacher = await make_teacher(db, "tfs_t")
    await make_order(db, t1.id, "A1", lng=104.061234, lat=30.612345)
    await make_order(db, t2.id, "B1", lng=104.061234, lat=30.612345)
    await db.flush()

    result = await find_orders_for_teacher(db, teacher, {"subject": "数学"}, [])
    assert result["total_matched"] == 2
    assert {item["raw_id"] for item in result["items"]} == {"A1", "B1"}
    # 教员脱敏口径：坐标降精度到 3 位小数（B 端精确坐标不得出教员接口）
    for item in result["items"]:
        assert len(str(item["lng"]).split(".")[-1]) <= 3


async def test_teacher_find_excludes_blacklisted_and_applied(db):
    tenant_a = await make_tenant(db, "tfs_xa")
    tenant_b = await make_tenant(db, "tfs_xb")
    teacher = await make_teacher(db, "tfs_x")
    await make_order(db, tenant_a.id, "A_OK", lng=104.06, lat=30.66)
    order_b = await make_order(db, tenant_b.id, "B_BLACK", lng=104.06, lat=30.66)
    order_c = await make_order(db, tenant_b.id, "C_APPLIED", lng=104.06, lat=30.66)
    db.add(Application(order_id=order_c.id, teacher_id=teacher.id, tenant_id=tenant_b.id))
    db.add(TenantTeacherBlacklist(tenant_id=tenant_b.id, teacher_id=teacher.id, reason="测试"))
    await db.flush()

    result = await find_orders_for_teacher(db, teacher, {"subject": "数学"}, [])
    raw_ids = {item["raw_id"] for item in result["items"]}
    assert "A_OK" in raw_ids
    assert "B_BLACK" not in raw_ids, "被租户拉黑的教员不得看到该租户订单"
    assert "C_APPLIED" not in raw_ids, "已投递订单不得重复出现在找单结果"


async def test_teacher_find_radius_by_home_location(db):
    tenant = await make_tenant(db, "tfs_geo")
    teacher = await make_teacher(db, "tfs_geo1")
    await make_order(db, tenant.id, "NEAR", lng=104.34, lat=30.66)
    await make_order(db, tenant.id, "FAR", lng=105.20, lat=30.66)
    await _set_teacher_location(teacher, 104.35, 30.66)
    await db.flush()

    result = await find_orders_for_teacher(db, teacher, {"subject": "数学", "radius_km": 10}, [])
    assert [item["raw_id"] for item in result["items"]] == ["NEAR"]
    assert result["items"][0]["distance_km"] is not None


async def test_teacher_find_no_location_ignores_radius_with_warning(db):
    tenant = await make_tenant(db, "tfs_noloc")
    teacher = await make_teacher(db, "tfs_noloc1")  # 无常驻地
    await make_order(db, tenant.id, "ANY", lng=104.06, lat=30.66)
    await db.flush()

    warnings: list[str] = []
    result = await find_orders_for_teacher(
        db, teacher, {"subject": "数学", "radius_km": 10}, warnings
    )
    assert result["total_matched"] == 1
    assert any("常驻地" in w for w in warnings)


async def test_teacher_find_expired_excluded(db):
    tenant = await make_tenant(db, "tfs_exp")
    teacher = await make_teacher(db, "tfs_exp1")
    await make_order(db, tenant.id, "LIVE", lng=104.06, lat=30.66)
    expired = await make_order(db, tenant.id, "DEAD", lng=104.06, lat=30.66)
    expired.expired_at = utcnow() - datetime.timedelta(hours=1)
    await db.flush()

    result = await find_orders_for_teacher(db, teacher, {"subject": "数学"}, [])
    assert [item["raw_id"] for item in result["items"]] == ["LIVE"]


async def test_teacher_find_scan_limit_warns(db, monkeypatch):
    """候选达到扫描上限时如实告警（与 B 端 order_search 同口径）：更早的有效单可能漏在窗口外。"""
    from services import teacher_order_search

    monkeypatch.setattr(teacher_order_search, "_SCAN_LIMIT", 2)
    tenant = await make_tenant(db, "tfs_cap")
    teacher = await make_teacher(db, "tfs_cap1")
    await make_order(db, tenant.id, "CAP1", lng=104.06, lat=30.66)
    await make_order(db, tenant.id, "CAP2", lng=104.06, lat=30.66)
    await db.flush()

    warnings: list[str] = []
    result = await teacher_order_search.find_orders_for_teacher(
        db, teacher, {"subject": "数学"}, warnings
    )
    assert result["scanned"] == 2
    assert result["total_matched"] == 2
    assert any("仅扫描了最近 2 条" in w for w in warnings)
