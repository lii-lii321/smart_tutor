"""
「待完善」订单筛选（status=incomplete 伪状态）回归：

- 口径：招聘中且（待定价 base_price<=0 或 无有效坐标 lng/lat=0）；
- 终态订单（已完成/已归档）即使缺价也不进队列——催办只对可运营的单有意义；
- 未知状态 422 拒绝；导出与列表同一口径。

运行方式：
    pytest tests/test_incomplete_orders.py
"""
from conftest import BASE, auth_header, make_order, make_tenant, tenant_token


async def test_incomplete_filter_picks_price_or_coords_gaps(client, db):
    tenant = await make_tenant(db, "incq001")

    no_price = await make_order(db, tenant.id, "INC-P1")  # 待定价（坐标正常）
    no_price.base_price = 0.0

    no_coords = await make_order(db, tenant.id, "INC-G1")  # 坐标缺失（价格正常）
    no_coords.lng = 0.0
    no_coords.lat = 0.0

    healthy = await make_order(db, tenant.id, "INC-OK")  # 健康单

    from models.domain import OrderStatus

    done_no_price = await make_order(db, tenant.id, "INC-D1")  # 终态缺价：不进队列
    done_no_price.base_price = 0.0
    done_no_price.status = OrderStatus.completed

    archived_no_price = await make_order(db, tenant.id, "INC-A1")
    archived_no_price.base_price = 0.0
    archived_no_price.status = OrderStatus.archived
    await db.commit()

    resp = await client.get(
        f"{BASE}/api/v1/orders/",
        params={"status": "incomplete"},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 200, resp.text
    ids = {item["raw_id"] for item in resp.json()["items"]}
    assert ids == {"INC-P1", "INC-G1"}, f"待完善队列应只含缺价/缺坐标的招聘中单: {ids}"
    assert healthy.id  # 三个对照单都真实存在（防 make_order 静默失败的假绿）


async def test_incomplete_unknown_status_rejected(client, db):
    tenant = await make_tenant(db, "incq002")
    await db.commit()

    resp = await client.get(
        f"{BASE}/api/v1/orders/",
        params={"status": "nonsense"},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 422
