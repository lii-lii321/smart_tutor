"""
按编号批量归档（batch-archive-by-codes）：编号解析（混合分隔符/大小写/raw_id 与
数字 id 混合）、非招聘中单跳过、not_found 回显、租户隔离、复用 batch-status 主体
的状态机与缓存失效。
"""
from conftest import make_order, make_tenant

from models.domain import OrderStatus


async def _seed(db, invite: str, raw_ids: list[str]) -> tuple:
    tenant = await make_tenant(db, invite)
    orders = []
    for rid in raw_ids:
        orders.append(await make_order(db, tenant.id, rid))
    await db.commit()
    return tenant, orders


async def test_archive_by_codes_happy_path(client, db):
    """混合分隔符/大小写不敏感/raw_id+数字 id 粘贴。4 个 token 指向 3 张单
    （BA-001 与数字 id=orders[0].id 同单），按单去重全部归档。"""
    tenant, orders = await _seed(db, "ba001a", ["BA-001", "BA-002", "BA-003"])
    await db.commit()

    resp = await client.post(
        "/api/v1/orders/batch-archive-by-codes",
        json={"codes": ["BA-001,ba-002\nBA-003；" + str(orders[0].id)]},
        headers={"Authorization": "Bearer " + __import__("conftest").tenant_token(tenant.id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["archived"] == 3
    assert body["not_found"] == []
    for order in orders:
        await db.refresh(order)
        assert order.status == OrderStatus.archived


async def test_archive_by_codes_skip_and_not_found(client, db):
    """已完成/已归档计入 skipped；对不上的编号原样回 not_found。"""
    tenant, orders = await _seed(db, "ba002a", ["BA-101", "BA-102"])
    orders[1].status = OrderStatus.completed
    await db.commit()

    resp = await client.post(
        "/api/v1/orders/batch-archive-by-codes",
        json={"codes": ["BA-101", "BA-102", "GHOST-1", "GHOST-2"]},
        headers={"Authorization": "Bearer " + __import__("conftest").tenant_token(tenant.id)},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["archived"] == 1
    assert body["skipped"] == 1
    assert body["not_found"] == ["GHOST-1", "GHOST-2"]


async def test_archive_by_codes_tenant_isolation(client, db):
    """他租户的编号不可见（不泄露存在性，进 not_found）。"""
    mine, _ = await _seed(db, "ba003a", ["BA-201"])
    other, other_orders = await _seed(db, "ba003b", ["BA-202"])

    resp = await client.post(
        "/api/v1/orders/batch-archive-by-codes",
        json={"codes": ["BA-201", "BA-202"]},
        headers={"Authorization": "Bearer " + __import__("conftest").tenant_token(mine.id)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["archived"] == 1
    assert body["not_found"] == ["BA-202"]
    await db.refresh(other_orders[0])
    assert other_orders[0].status == OrderStatus.recruiting


async def test_archive_by_codes_empty_codes_422(client, db):
    """全空白/分隔符粘贴 → 422。"""
    tenant, _ = await _seed(db, "ba004a", ["BA-301"])
    resp = await client.post(
        "/api/v1/orders/batch-archive-by-codes",
        json={"codes": ["  ", "，", "\n"]},
        headers={"Authorization": "Bearer " + __import__("conftest").tenant_token(tenant.id)},
    )
    assert resp.status_code == 422


async def test_archive_by_codes_removes_from_board(client, db):
    """归档后订单从公开橱窗消失（缓存失效钩子生效）。"""
    from conftest import tenant_token

    tenant, orders = await _seed(db, "ba005a", ["BA-401"])
    resp = await client.post(
        "/api/v1/orders/batch-archive-by-codes",
        json={"codes": ["BA-401"]},
        headers={"Authorization": "Bearer " + tenant_token(tenant.id)},
    )
    assert resp.status_code == 200
    assert resp.json()["archived"] == 1

    board = await client.get(f"/api/v1/public/agent/{tenant.invite_code}/board")
    assert board.status_code == 200
    board_ids = {o["id"] for o in board.json()["orders"]}
    assert orders[0].id not in board_ids
