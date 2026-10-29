"""F15 回归：精算金额列容量与落库前容量守卫。

背景：base_price 在 schema 上限（le=999999.99）内合法输入，经服务端精算
（信息费 = 课酬 × 每周次数 × 频次倍率，最小综合倍率 1.5）可得超出 DECIMAL(8,2)
上限 999999.99 的金额（如 700000×1×1.5 = 1,050,000.00），生产 MySQL 严格模式
落库必 1264 DataError（修复前 500；F14 兜底后为误导性 422）。

修复：orders 三列精算值 + applications 三列费率快照 + financial_records.amount
加宽为 DECIMAL(10,2)（迁移 m3b9e2c6f8a4），并在导入/改价落库前做容量守卫转 422。

本地 SQLite 无 DECIMAL 精度语义，容量守卫与金额正确性在本地可验证；
真实 MySQL 严格模式端到端设 TEST_DATABASE_URL=mysql://... 后运行（CI 可用）。
"""
import os
from decimal import Decimal

import pytest
from conftest import make_tenant, tenant_token
from httpx import AsyncClient

import routers.v1.orders as orders_router
from config import settings  # noqa: F401  保持与其他测试文件一致的 config 初始化
from models.domain import Order
from services.calculator import calculate_info_fee

_LARGE_BASE = 700000.0  # ×1×1.5 = 1,050,000.00：旧 DECIMAL(8,2) 上限 999999.99 必溢出


def _import_item(raw_id: str, base_price: float) -> dict:
    # 客户端金额字段仅过 schema 校验（le=999999.99）；服务端 price_fields 一律按费率重算
    return {
        "raw_id": raw_id,
        "raw_text": "【" + raw_id + "】初三数学 700000/次",
        "grade_subject": "初三数学",
        "price_total": "700000/次",
        "base_price": base_price,
        "weekly_frequency": 1,
        "is_summer_vacation": False,
        "fuzzy_address": "成都市锦江区",
        "lng": 104.065735,
        "lat": 30.659462,
        "calculated_info_fee": 180.0,
        "deposit_amount": 100.0,
        "balance_amount": 80.0,
    }


def _order_detail_url(order_id: int) -> str:
    return f"/api/v1/orders/{order_id}"


def _oversized_fee() -> dict:
    cap = orders_router._fee_capacity()
    return {
        "total_info_fee": cap + Decimal("0.01"),
        "deposit": Decimal("100.00"),
        "balance": cap + Decimal("0.01") - Decimal("100.00"),
    }


def test_fee_arithmetic_within_widened_capacity():
    """极值精算必须落在加宽后的 DECIMAL(10,2) 内，且仍超旧 (8,2) 上限（回归锚）。"""
    fee = calculate_info_fee(999999.99, 14, False)
    assert fee["total_info_fee"] == Decimal("11199999.89")
    assert fee["total_info_fee"] > Decimal("999999.99"), "旧 (8,2) 上限内精算即溢出（F15 根因锚点）"
    assert orders_router._fee_capacity() == Decimal("99999999.99")
    assert fee["total_info_fee"] <= orders_router._fee_capacity()
    assert Order.__table__.c.calculated_info_fee.type.precision == 10


async def test_large_base_price_import_and_patch_roundtrip(client: AsyncClient, db):
    """加宽后 schema 上限内的大额单正常导入与改价，金额精算正确落库。"""
    tenant = await make_tenant(db, "f15t001")
    await db.commit()
    headers = {"Authorization": "Bearer " + tenant_token(tenant.id)}

    resp = await client.post(
        "/api/v1/orders/batch-import",
        json={"items": [_import_item("F15-LARGE", _LARGE_BASE)]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 1

    # 每用例独立全新库：首张订单主键恒为 1，按主键直取
    row = await db.get(Order, 1)
    assert row is not None and row.raw_id == "F15-LARGE"
    assert row.calculated_info_fee == Decimal("1050000.00")
    assert row.balance_amount == Decimal("1049900.00")

    patched = await client.patch(
        _order_detail_url(row.id), json={"base_price": 300000.0, "weekly_frequency": 2}, headers=headers
    )
    assert patched.status_code == 200, patched.text
    assert Decimal(str(patched.json()["calculated_info_fee"])) == Decimal("600000.00")


async def test_capacity_guard_returns_422_on_import(client: AsyncClient, db, monkeypatch):
    """容量守卫：精算值超列容量时导入路径转 422（消息指向金额容量，不误导为超长字段）。"""
    tenant = await make_tenant(db, "f15t002")
    await db.commit()
    headers = {"Authorization": "Bearer " + tenant_token(tenant.id)}
    monkeypatch.setattr(orders_router, "calculate_info_fee", lambda *a, **kw: _oversized_fee())

    resp = await client.post(
        "/api/v1/orders/batch-import",
        json={"items": [_import_item("F15-GUARD", _LARGE_BASE)]},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text
    assert "金额容量" in resp.json()["detail"]


async def test_capacity_guard_returns_422_on_patch(client: AsyncClient, db, monkeypatch):
    """改价路径同守卫：recalc 精算超容量 → 422。"""
    tenant = await make_tenant(db, "f15t003")
    await db.commit()
    headers = {"Authorization": "Bearer " + tenant_token(tenant.id)}

    imported = await client.post(
        "/api/v1/orders/batch-import",
        json={"items": [_import_item("F15-GUARD2", 120.0)]},
        headers=headers,
    )
    assert imported.status_code == 200, imported.text

    monkeypatch.setattr(orders_router, "calculate_info_fee", lambda *a, **kw: _oversized_fee())
    patched = await client.patch(
        _order_detail_url(1), json={"base_price": _LARGE_BASE}, headers=headers
    )
    assert patched.status_code == 422, patched.text
    assert "金额容量" in patched.json()["detail"]


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("mysql"),
    reason="真实 MySQL 严格模式端到端需 TEST_DATABASE_URL 指向 MySQL 测试库（本地 SQLite 不强制 DECIMAL 精度）",
)
async def test_real_mysql_large_fee_persists(client: AsyncClient, db):
    """真 MySQL：加宽后 1,050,000.00 精算值在严格模式下正常落库并回读。"""
    tenant = await make_tenant(db, "f15t004")
    await db.commit()
    headers = {"Authorization": "Bearer " + tenant_token(tenant.id)}

    resp = await client.post(
        "/api/v1/orders/batch-import",
        json={"items": [_import_item("F15-MYSQL1", _LARGE_BASE)]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    row = await db.get(Order, 1)
    assert row is not None and row.calculated_info_fee == Decimal("1050000.00")
    detail = await client.get(_order_detail_url(row.id), headers=headers)
    assert detail.json()["calculated_info_fee"] == 1050000.0
