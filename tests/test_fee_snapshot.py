"""
费率快照与成交资金守卫测试（审查 P1-1 / P1-2）。

覆盖：
- 确认定金写入费率快照；重复确认定金被拒且不重复记流水；
- 定金后中介改价：尾款、试课失败退款、没收一律按快照，不随新价漂移；
- 成交时已付定金的兄弟投递自动登记退款流水（台账有去向）并通知中介；
- 成交时未产生资金往来的候选照旧拒绝（无流水）；
- 试课中的兄弟投递（不变量破坏）拒绝成交且不落任何变更；
- 教员重新投递后上一轮快照清空。

运行方式：
    pytest tests/test_fee_snapshot.py
"""
from decimal import Decimal

from conftest import (
    auth_header,
    make_order,
    make_teacher,
    make_tenant,
    teacher_token,
    tenant_token,
)
from sqlalchemy import select

from models.domain import (
    Application,
    ApplicationStatus,
    FinancialRecord,
    FinancialType,
    Notification,
    Order,
    OrderStatus,
)

BASE = "http://test"


async def _setup(db) -> dict:
    """一个租户 + 一个订单（base 200/周2次 → 信息费200/定金100/尾款100）+ 两个教员。"""
    tenant = await make_tenant(db, "fee0001")
    teacher_a = await make_teacher(db, "fee_teacher_a", name="教员A")
    teacher_b = await make_teacher(db, "fee_teacher_b", name="教员B")

    from models.domain import TeacherResume
    resume_a = TeacherResume(
        teacher_id=teacher_a.id, title="默认简历",
        teaching_subjects="数学", teaching_grades="初一-初三", experience="两年经验",
    )
    resume_b = TeacherResume(
        teacher_id=teacher_b.id, title="默认简历",
        teaching_subjects="数学", teaching_grades="初一-初三", experience="三年经验",
    )
    db.add_all([resume_a, resume_b])
    order = await make_order(db, tenant.id, "FEE-001")
    await db.commit()
    return {
        "tenant_id": tenant.id,
        "order_id": order.id,
        "teacher_a": teacher_a.id, "resume_a": resume_a.id,
        "teacher_b": teacher_b.id, "resume_b": resume_b.id,
    }


async def _apply(client, d: dict, key: str) -> int:
    """key 为 "a"/"b"，对应 _setup 返回的教员/简历键。"""
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        json={"order_id": d["order_id"], "resume_id": d[f"resume_{key}"]},
        headers=auth_header(teacher_token(d[f"teacher_{key}"])),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _to_deposit_paid(client, d: dict, app_id: int) -> None:
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/shortlist",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/confirm-deposit",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text


def _tenant_headers(d: dict) -> dict:
    return auth_header(tenant_token(d["tenant_id"]))


async def _records(db, order_id: int, record_type: FinancialType) -> list[FinancialRecord]:
    result = await db.execute(
        select(FinancialRecord).where(
            FinancialRecord.order_id == order_id,
            FinancialRecord.type == record_type,
        )
    )
    return list(result.scalars().all())


async def _order_net(db, order_id: int) -> Decimal:
    """台账净收入：收款为正（定金/尾款），支出为负（退款/没收）。"""
    result = await db.execute(
        select(FinancialRecord).where(FinancialRecord.order_id == order_id)
    )
    net = Decimal("0")
    for record in result.scalars():
        amount = Decimal(str(record.amount))
        if record.type in (FinancialType.deposit_in, FinancialType.balance_in):
            net += amount
        else:
            net -= amount
    return net


async def test_confirm_deposit_writes_fee_snapshot(client, db):
    d = await _setup(db)
    app_id = await _apply(client, d, "a")
    await _to_deposit_paid(client, d, app_id)

    app = (await db.execute(select(Application).where(Application.id == app_id))).scalar_one()
    assert Decimal(str(app.fee_total)) == Decimal("200.00")
    assert Decimal(str(app.fee_deposit)) == Decimal("100.00")
    assert Decimal(str(app.fee_balance)) == Decimal("100.00")


async def test_confirm_deposit_second_call_rejected(client, db):
    d = await _setup(db)
    app_id = await _apply(client, d, "a")
    await _to_deposit_paid(client, d, app_id)

    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/confirm-deposit",
        headers=_tenant_headers(d),
    )
    assert resp.status_code == 400
    deposits = await _records(db, d["order_id"], FinancialType.deposit_in)
    assert len(deposits) == 1


async def test_balance_follows_snapshot_after_price_change(client, db):
    d = await _setup(db)
    app_id = await _apply(client, d, "a")
    await _to_deposit_paid(client, d, app_id)

    # 定金后中介把课酬 200 → 300（新口径：信息费300/定金100/尾款200）
    resp = await client.patch(
        f"{BASE}/api/v1/orders/{d['order_id']}",
        json={"base_price": 300},
        headers=_tenant_headers(d),
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/start-trial", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/confirm-balance", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text

    balances = await _records(db, d["order_id"], FinancialType.balance_in)
    assert len(balances) == 1
    # 尾款按定金确认时的快照收 100，而不是改价后的 200
    assert Decimal(str(balances[0].amount)) == Decimal("100.00")


async def test_trial_failed_refund_uses_snapshot_after_price_change(client, db):
    d = await _setup(db)
    app_id = await _apply(client, d, "a")
    await _to_deposit_paid(client, d, app_id)

    resp = await client.patch(
        f"{BASE}/api/v1/orders/{d['order_id']}",
        json={"base_price": 300},
        headers=_tenant_headers(d),
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/start-trial", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/confirm-balance", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text

    # 试课失败，家长已付试课酬 100：退费 = max(0, 已收200 − 100×0.7) = 130
    # 若按改价后现算会漂移成 max(0, 300 − 70) = 230
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/trial-failed",
        params={"trial_paid_by_parent": "100"},
        headers=_tenant_headers(d),
    )
    assert resp.status_code == 200, resp.text

    refunds = await _records(db, d["order_id"], FinancialType.refund_out)
    assert len(refunds) == 1
    assert Decimal(str(refunds[0].amount)) == Decimal("130.00")


async def test_forfeit_uses_snapshot_after_price_change(client, db):
    d = await _setup(db)
    app_id = await _apply(client, d, "a")
    await _to_deposit_paid(client, d, app_id)

    resp = await client.patch(
        f"{BASE}/api/v1/orders/{d['order_id']}",
        json={"base_price": 300},
        headers=_tenant_headers(d),
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/start-trial", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/confirm-balance", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/forfeit", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text

    forfeits = await _records(db, d["order_id"], FinancialType.forfeit)
    assert len(forfeits) == 1
    # 没收按快照实收 200，而不是改价后的 300
    assert Decimal(str(forfeits[0].amount)) == Decimal("200.00")


async def test_complete_auto_refunds_deposit_paid_siblings(client, db):
    d = await _setup(db)
    app_a = await _apply(client, d, "a")
    app_b = await _apply(client, d, "b")
    await _to_deposit_paid(client, d, app_a)
    await _to_deposit_paid(client, d, app_b)

    # A 走完试课收款并成交；B 仍停在已付定金
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/start-trial", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/confirm-balance", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/complete", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text

    app_b_row = (await db.execute(select(Application).where(Application.id == app_b))).scalar_one()
    assert app_b_row.status == ApplicationStatus.refunded
    assert app_b_row.refunded_at is not None

    refunds = [
        r for r in await _records(db, d["order_id"], FinancialType.refund_out)
        if r.teacher_id == d["teacher_b"]
    ]
    assert len(refunds) == 1
    assert Decimal(str(refunds[0].amount)) == Decimal("100.00")

    # 台账守恒：净收入 = A 的全额信息费（100+100 收入 + 100 收入 − 100 退款）
    assert await _order_net(db, d["order_id"]) == Decimal("200.00")

    # 中介收到待退定金提醒
    notif = (await db.execute(
        select(Notification).where(
            Notification.tenant_id == d["tenant_id"],
            Notification.title == "成交后待退定金",
        )
    )).scalar_one_or_none()
    assert notif is not None

    app_a_row = (await db.execute(select(Application).where(Application.id == app_a))).scalar_one()
    assert app_a_row.status == ApplicationStatus.completed
    order = (await db.execute(select(Order).where(Order.id == d["order_id"]))).scalar_one()
    assert order.status == OrderStatus.completed


async def test_complete_rejects_money_free_siblings(client, db):
    d = await _setup(db)
    app_a = await _apply(client, d, "a")
    app_b = await _apply(client, d, "b")  # B 保持 pending，未产生资金往来
    await _to_deposit_paid(client, d, app_a)

    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/start-trial", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/confirm-balance", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/complete", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text

    app_b_row = (await db.execute(select(Application).where(Application.id == app_b))).scalar_one()
    assert app_b_row.status == ApplicationStatus.rejected
    # 无资金往来的候选不应有任何流水
    assert await _order_net(db, d["order_id"]) == Decimal("200.00")
    b_records = [
        r for r in (await db.execute(
            select(FinancialRecord).where(FinancialRecord.order_id == d["order_id"])
        )).scalars()
        if r.teacher_id == d["teacher_b"]
    ]
    assert b_records == []


async def test_complete_blocks_active_trial_sibling(client, db):
    d = await _setup(db)
    app_a = await _apply(client, d, "a")
    app_b = await _apply(client, d, "b")
    await _to_deposit_paid(client, d, app_a)
    await _to_deposit_paid(client, d, app_b)
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/start-trial", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/confirm-balance", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text

    # 人为构造不变量破坏（同单两个试课中，正常流程不可达），验证防御性守卫
    app_b_row = (await db.execute(select(Application).where(Application.id == app_b))).scalar_one()
    app_b_row.status = ApplicationStatus.trial_in_progress
    await db.commit()

    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/complete", headers=_tenant_headers(d)
    )
    assert resp.status_code == 409

    # 409 整体回滚：订单与投递保持原状，未产生任何终态写入
    app_a_row = (await db.execute(select(Application).where(Application.id == app_a))).scalar_one()
    assert app_a_row.status == ApplicationStatus.balance_paid
    order = (await db.execute(select(Order).where(Order.id == d["order_id"]))).scalar_one()
    assert order.status == OrderStatus.trial_in_progress


async def test_reapply_clears_fee_snapshot(client, db):
    d = await _setup(db)
    app_id = await _apply(client, d, "a")
    await _to_deposit_paid(client, d, app_id)

    # 教员取消（定金登记退款）
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/cancel",
        headers=auth_header(teacher_token(d["teacher_a"])),
    )
    assert resp.status_code == 200, resp.text

    # 重新投递复用同一行：上一轮快照必须作废
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        json={"order_id": d["order_id"], "resume_id": d["resume_a"]},
        headers=auth_header(teacher_token(d["teacher_a"])),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["id"] == app_id

    app = (await db.execute(select(Application).where(Application.id == app_id))).scalar_one()
    assert app.status == ApplicationStatus.pending
    assert app.fee_total is None
    assert app.fee_deposit is None
    assert app.fee_balance is None
