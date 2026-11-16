"""
按编号批量线下成交（batch-complete-by-codes）：编号解析与归档接口同构（混合分隔符/
大小写/raw_id 与数字 id）、非招聘中单跳过、not_found 回显、租户隔离、已收款投递
护栏（blocked，防资金悬空）、completed_at 落库、从公开橱窗消失。
"""
from conftest import make_order, make_teacher, make_tenant

from models.domain import Application, ApplicationStatus, OrderStatus, Tenant
from utils.clock import utcnow


async def _seed(db, invite: str, raw_ids: list[str]) -> tuple:
    tenant = await make_tenant(db, invite)
    orders = []
    for rid in raw_ids:
        orders.append(await make_order(db, tenant.id, rid))
    await db.commit()
    return tenant, orders


def _auth(tenant: Tenant) -> dict:
    import conftest

    return {"Authorization": "Bearer " + conftest.tenant_token(tenant.id)}


async def test_complete_by_codes_happy_path(client, db):
    """混合分隔符/大小写不敏感/raw_id+数字 id 粘贴：全部直达已完成，
    selected_teacher_id 保持空（线下单无平台投递，与正规成交流程一致）。"""
    tenant, orders = await _seed(db, "bc001a", ["BC-001", "BC-002", "BC-003"])

    resp = await client.post(
        "/api/v1/orders/batch-complete-by-codes",
        json={"codes": ["BC-001,bc-002\nBC-003；" + str(orders[0].id)]},
        headers=_auth(tenant),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["completed"] == 3
    assert body["skipped"] == 0
    assert body["blocked"] == []
    assert body["not_found"] == []
    for order in orders:
        await db.refresh(order)
        assert order.status == OrderStatus.completed
        assert order.selected_teacher_id is None


async def test_complete_by_codes_skip_not_found_and_blocked(client, db):
    """已完成/已归档计 skipped；有已收款投递的单 blocked（资金悬空护栏）；
    对不上的编号原样回 not_found。"""
    tenant, orders = await _seed(db, "bc002a", ["BC-101", "BC-102", "BC-103"])
    teacher = await make_teacher(db, "bc_teacher")
    orders[1].status = OrderStatus.completed
    await db.commit()
    application = Application(
        order_id=orders[2].id,
        teacher_id=teacher.id,
        tenant_id=tenant.id,
        status=ApplicationStatus.deposit_paid,
        deposit_paid_at=utcnow(),
    )
    db.add(application)
    await db.commit()

    resp = await client.post(
        "/api/v1/orders/batch-complete-by-codes",
        json={"codes": ["BC-101", "BC-102", "BC-103", "GHOST-1"]},
        headers=_auth(tenant),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["completed"] == 1
    assert body["skipped"] == 1
    assert body["blocked"] == ["BC-103"]
    assert body["not_found"] == ["GHOST-1"]
    await db.refresh(orders[2])
    # 被拦截的单保持招聘中：必须走投递审核完成，防资金悬空
    assert orders[2].status == OrderStatus.recruiting


async def test_complete_by_codes_tenant_isolation(client, db):
    """他租户的编号不可见（不泄露存在性，进 not_found）。"""
    mine, _ = await _seed(db, "bc003a", ["BC-201"])
    other, other_orders = await _seed(db, "bc003b", ["BC-202"])

    resp = await client.post(
        "/api/v1/orders/batch-complete-by-codes",
        json={"codes": ["BC-201", "BC-202"]},
        headers=_auth(mine),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["completed"] == 1
    assert body["not_found"] == ["BC-202"]
    await db.refresh(other_orders[0])
    assert other_orders[0].status == OrderStatus.recruiting


async def test_complete_by_codes_empty_codes_422(client, db):
    """全空白/分隔符粘贴 → 422。"""
    tenant, _ = await _seed(db, "bc004a", ["BC-301"])
    resp = await client.post(
        "/api/v1/orders/batch-complete-by-codes",
        json={"codes": ["  ", "，", "\n"]},
        headers=_auth(tenant),
    )
    assert resp.status_code == 422


async def test_complete_by_codes_removes_from_board(client, db):
    """线下成交后订单从公开橱窗消失（缓存失效钩子生效）。"""
    tenant, orders = await _seed(db, "bc005a", ["BC-401"])
    resp = await client.post(
        "/api/v1/orders/batch-complete-by-codes",
        json={"codes": ["BC-401"]},
        headers=_auth(tenant),
    )
    assert resp.status_code == 200
    assert resp.json()["completed"] == 1

    board = await client.get(f"/api/v1/public/agent/{tenant.invite_code}/board")
    assert board.status_code == 200
    board_ids = {o["id"] for o in board.json()["orders"]}
    assert orders[0].id not in board_ids
