"""
公开橱窗订单详情（免登录轻薄版）：脱敏白名单、租户/状态/有效期过滤、掩码覆盖
原文与要求文本。无需登录（router 级限流，用例间由 conftest autouse 清空计数）。
"""
import datetime

from conftest import make_order, make_tenant

from models.domain import OrderStatus
from utils.clock import utcnow

BASE = "http://test"


async def _seed_order_with_contacts(db, raw_id: str):
    tenant = await make_tenant(db, raw_id.lower().replace("-", "")[:8])
    order = await make_order(db, tenant.id, raw_id)
    # 模拟真实录单：原文与要求里都可能出现家长联系方式
    order.raw_text = f"【{raw_id}】初三数学，联系家长 13812345678"
    order.requirements = "要求女教员，微信号: parent_wx_88 有耐心"
    await db.commit()
    return tenant, order


async def test_public_detail_masked_for_guest(client, db):
    """免登录 200：原文/要求打码、敏感键不在响应面、坐标粗化、微信在。"""
    tenant, order = await _seed_order_with_contacts(db, "LT-001")
    resp = await client.get(f"{BASE}/api/v1/public/agent/{tenant.invite_code}/orders/{order.id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # 白名单面：敏感键一律不下发
    for key in ("parent_phone", "exact_address", "raw_id", "status", "expired_at"):
        assert key not in body, f"响应泄漏了 {key}"
    # 掩码：完整号码不存在，掩码形态存在；微信号整体打掉
    assert "13812345678" not in resp.text
    assert "138****5678" in body["raw_text"]
    assert "parent_wx_88" not in resp.text
    # 中介微信与金额口径在
    assert body["contact_wechat"] == "wx_test"
    assert body["calculated_info_fee"] == 400.0
    # 坐标粗化到 3 位小数（小区级，±110m）
    assert len(str(body["lng"]).split(".")[-1]) <= 3
    assert len(str(body["lat"]).split(".")[-1]) <= 3


async def test_public_detail_contact_fields_in_requirements_masked(client, db):
    """requirements 是免登录场景的额外泄漏面：座机/微信/QQ 形态也要打掉。"""
    tenant, order = await _seed_order_with_contacts(db, "LT-002")
    order.requirements = "座机 028-87654321，QQ: 12345678"
    await db.commit()

    resp = await client.get(f"{BASE}/api/v1/public/agent/{tenant.invite_code}/orders/{order.id}")
    assert resp.status_code == 200
    assert "028-87654321" not in resp.text
    assert "12345678" not in resp.text


async def test_public_detail_404_matrix(client, db):
    """404：错邀请码 / 停用中介 / 归档单 / 过期单 / 他租户订单。"""
    tenant, order = await _seed_order_with_contacts(db, "LT-003")
    other, other_order = await _seed_order_with_contacts(db, "LT-004")

    resp = await client.get(f"{BASE}/api/v1/public/agent/no_such_code/orders/{order.id}")
    assert resp.status_code == 404

    tenant.is_active = False
    await db.commit()
    resp = await client.get(f"{BASE}/api/v1/public/agent/{tenant.invite_code}/orders/{order.id}")
    assert resp.status_code == 404
    tenant.is_active = True
    await db.commit()

    order.status = OrderStatus.archived
    await db.commit()
    resp = await client.get(f"{BASE}/api/v1/public/agent/{tenant.invite_code}/orders/{order.id}")
    assert resp.status_code == 404
    order.status = OrderStatus.recruiting
    await db.commit()

    order.expired_at = utcnow() - datetime.timedelta(hours=1)
    await db.commit()
    resp = await client.get(f"{BASE}/api/v1/public/agent/{tenant.invite_code}/orders/{order.id}")
    assert resp.status_code == 404
    order.expired_at = utcnow() + datetime.timedelta(hours=72)
    await db.commit()

    # 他租户订单 id：不泄露存在性，同文案 404
    resp = await client.get(f"{BASE}/api/v1/public/agent/{tenant.invite_code}/orders/{other_order.id}")
    assert resp.status_code == 404
