"""F14 回归：orders.parent_phone 列宽必须容纳 ADR-0005 密文；落库 DataError 转 422 不再 500。

背景：parent_phone 建库 VARCHAR(20)（a9a54481a950）且无加宽迁移，encrypt_pii 产出
"v1:"+base64(12B nonce+ct+16B tag) 的 11 位手机号密文即 55 字符——生产
（PII_ENC_KEY + MySQL 严格模式）B 端录单带家长电话必 1406 → 未捕获 500。

本地 SQLite 不强制列宽，"MySQL 严格模式"以 monkeypatch 在 flush/commit 注入
sqlalchemy.exc.DataError 模拟（MySQL 1406 的 SQLAlchemy 形态，与服务器复现一致）；
设 TEST_DATABASE_URL=mysql://... 时额外跑真实 MySQL 严格模式端到端（CI 可用）。
"""
import base64
import os

import pytest
from conftest import make_tenant, tenant_token
from httpx import AsyncClient
from sqlalchemy.exc import DataError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.domain import Order
from services.pii_crypto import encrypt_pii

_KEY = base64.b64encode(bytes(range(32))).decode("ascii")
_PHONE = "13800001234"


def _import_item(raw_id: str, **extra) -> dict:
    return {
        "raw_id": raw_id,
        "raw_text": "【" + raw_id + "】初三数学 200/次",
        "grade_subject": "初三数学",
        "price_total": "200/次",
        "base_price": 200.0,
        "weekly_frequency": 2,
        "is_summer_vacation": False,
        "fuzzy_address": "成都市锦江区",
        "lng": 104.065735,
        "lat": 30.659462,
        "calculated_info_fee": 400.0,
        "deposit_amount": 100.0,
        "balance_amount": 300.0,
        **extra,
    }


def _order_detail_url(order_id: int) -> str:
    return f"/api/v1/orders/{order_id}"


def _arm_strict_mode(monkeypatch, method: str) -> None:
    """一次性武装：该方法首次调用抛 DataError（MySQL 1406 严格模式形态），之后放行。"""
    orig = getattr(AsyncSession, method)
    armed = {"on": True}

    async def strict_first(self, *args, **kwargs):
        if armed["on"]:
            armed["on"] = False
            raise DataError(
                '(pymysql.exceptions.DataError) (1406, "Data too long for column \'parent_phone\' at row 1")',
                None,
                Exception("Data too long for column 'parent_phone'"),
            )
        return await orig(self, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, method, strict_first)


async def test_cipher_fits_widened_column_but_exceeded_old_width(monkeypatch):
    """列宽不变式：11 位手机号密文必须 ≤ 新列宽 80，且 > 旧列宽 20（旧库必溢出的回归锚）。"""
    monkeypatch.setattr(settings, "PII_ENC_KEY", _KEY)
    cipher = encrypt_pii(_PHONE)
    column_len = Order.__table__.c.parent_phone.type.length

    assert cipher.startswith("v1:")
    assert len(cipher) == 55
    assert len(cipher) > 20, "旧列宽下密文必溢出（F14 根因锚点）"
    assert column_len == 80
    assert len(cipher) <= column_len


async def test_batch_import_parent_phone_ciphertext_roundtrip(client: AsyncClient, db, monkeypatch):
    """带 PII_ENC_KEY 正常录单：密文落库不超宽，B 端详情解密回读明文。"""
    monkeypatch.setattr(settings, "PII_ENC_KEY", _KEY)
    tenant = await make_tenant(db, "f14t001")
    await db.commit()
    headers = {"Authorization": "Bearer " + tenant_token(tenant.id)}

    resp = await client.post(
        "/api/v1/orders/batch-import",
        json={"items": [_import_item("F14-RT1", parent_phone=_PHONE)]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 1

    # 每用例独立全新库：首张订单主键恒为 1，按主键直取
    row = await db.get(Order, 1)
    assert row is not None and row.raw_id == "F14-RT1"
    assert row.parent_phone is not None and row.parent_phone.startswith("v1:")
    assert len(row.parent_phone) <= Order.__table__.c.parent_phone.type.length

    detail = await client.get(_order_detail_url(row.id), headers=headers)
    assert detail.status_code == 200
    assert detail.json()["parent_phone"] == _PHONE


async def test_batch_import_overlong_dataerror_returns_422_not_500(client: AsyncClient, db, monkeypatch):
    """MySQL 严格模式（模拟）：flush 抛 DataError → 422 带可操作提示，不再 500。"""
    monkeypatch.setattr(settings, "PII_ENC_KEY", _KEY)
    tenant = await make_tenant(db, "f14t002")
    await db.commit()
    _arm_strict_mode(monkeypatch, "flush")
    headers = {"Authorization": "Bearer " + tenant_token(tenant.id)}

    resp = await client.post(
        "/api/v1/orders/batch-import",
        json={"items": [_import_item("F14-DE1", parent_phone=_PHONE)]},
        headers=headers,
    )
    assert resp.status_code == 422, resp.text
    assert "超长" in resp.json()["detail"]


async def test_update_order_overlong_dataerror_returns_422_not_500(client: AsyncClient, db, monkeypatch):
    """编辑路径同修：PATCH 家长电话遇严格模式 DataError → 422（commit 阶段抛出）。"""
    monkeypatch.setattr(settings, "PII_ENC_KEY", _KEY)
    tenant = await make_tenant(db, "f14t003")
    await db.commit()
    headers = {"Authorization": "Bearer " + tenant_token(tenant.id)}

    imported = await client.post(
        "/api/v1/orders/batch-import",
        json={"items": [_import_item("F14-DE2")]},
        headers=headers,
    )
    assert imported.status_code == 200, imported.text

    _arm_strict_mode(monkeypatch, "commit")
    patched = await client.patch("/api/v1/orders/1", json={"parent_phone": _PHONE}, headers=headers)
    assert patched.status_code == 422, patched.text
    assert "超长" in patched.json()["detail"]


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", "").startswith("mysql"),
    reason="真实 MySQL 严格模式端到端需 TEST_DATABASE_URL 指向 MySQL 测试库（本地 SQLite 不强制列宽）",
)
async def test_real_mysql_strict_mode_import_with_parent_phone(client: AsyncClient, db, monkeypatch):
    """真 MySQL：加宽后 11 位手机号密文（55 字符）在严格模式下正常落库并解密回读。"""
    monkeypatch.setattr(settings, "PII_ENC_KEY", _KEY)
    tenant = await make_tenant(db, "f14t004")
    await db.commit()
    headers = {"Authorization": "Bearer " + tenant_token(tenant.id)}

    resp = await client.post(
        "/api/v1/orders/batch-import",
        json={"items": [_import_item("F14-MYSQL1", parent_phone=_PHONE)]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    row = await db.get(Order, 1)
    assert row is not None and row.raw_id == "F14-MYSQL1"
    assert row.parent_phone.startswith("v1:")
    assert len(row.parent_phone) <= 80
    detail = await client.get(_order_detail_url(row.id), headers=headers)
    assert detail.json()["parent_phone"] == _PHONE
