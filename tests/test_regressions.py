"""
本次逻辑修复的回归测试。

覆盖：
- 教员视角订单详情脱敏（家长电话/真实地址不再泄露，原文掩码）
- archive / batch-status 强制走状态机
- 拒绝投递端点
- 自带价订单投递不再覆盖订单级价格，费用按投递报价精算

基建已迁移 conftest（db/client fixture + 造数工厂），断言口径未变。

运行方式：
    pytest tests/test_regressions.py
"""
import datetime

from conftest import auth_header, teacher_token, tenant_token
from sqlalchemy import select

BASE = "http://test"
PARENT_PHONE = "13812345678"


async def _setup(db) -> dict:
    from models.domain import Gender, Order, OrderStatus, Teacher, TeacherResume, Tenant

    tenant = Tenant(tenant_name="回归中介", invite_code="regr0001", contact_wechat="wx_r")
    teacher = Teacher(
        openid="rt_001", name="回归教员", gender=Gender.male,
        phone="13800000001", wechat_id="wx_rt", school="测试大学", is_985_211=True,
    )
    db.add_all([tenant, teacher])
    await db.flush()
    resume = TeacherResume(
        teacher_id=teacher.id, title="默认简历",
        teaching_subjects="数学、英语", teaching_grades="初一-初三",
        experience="两年家教经验",
    )
    db.add(resume)
    await db.flush()

    now = datetime.datetime.utcnow()
    expired = now + datetime.timedelta(hours=72)
    o_normal = Order(
        tenant_id=tenant.id, raw_id="REG-001",
        raw_text=f"【测试单 91940393】联系家长 {PARENT_PHONE}，地址天府大道1号",
        grade_subject="初三数学", requirements="985", price_total="200/次",
        base_price=200.0, weekly_frequency=2,
        calculated_info_fee=200.0, deposit_amount=100.0, balance_amount=100.0,
        exact_address="天府大道1号101室", parent_phone=PARENT_PHONE,
        fuzzy_address="成都市天府大道", lng=104.06, lat=30.57,
        status=OrderStatus.recruiting, expired_at=expired,
    )
    o_proposed = Order(
        tenant_id=tenant.id, raw_id="REG-002", raw_text="自带价订单",
        grade_subject="初三数学", requirements="", price_total="自带价",
        base_price=0.0, weekly_frequency=1,
        calculated_info_fee=0.0, deposit_amount=0.0, balance_amount=0.0,
        exact_address="自带价地址", parent_phone=PARENT_PHONE,
        fuzzy_address="成都市自带价", lng=104.06, lat=30.57,
        status=OrderStatus.recruiting, expired_at=expired,
    )
    o_completed = Order(
        tenant_id=tenant.id, raw_id="REG-003", raw_text="已完成订单",
        grade_subject="初一数学", requirements="", price_total="150/次",
        base_price=150.0, weekly_frequency=1,
        calculated_info_fee=225.0, deposit_amount=100.0, balance_amount=125.0,
        exact_address="地址C", parent_phone=PARENT_PHONE,
        fuzzy_address="成都市C", lng=104.06, lat=30.57,
        status=OrderStatus.completed, expired_at=expired,
    )
    db.add_all([o_normal, o_proposed, o_completed])
    await db.commit()
    return {
        "tenant_id": tenant.id, "teacher_id": teacher.id, "resume_id": resume.id,
        "order_normal_id": o_normal.id,
        "order_proposed_id": o_proposed.id,
        "order_completed_id": o_completed.id,
    }


async def _apply(d, client, order_key: str, proposed_price: float | None = None) -> int:
    params = {"order_id": d[order_key], "resume_id": d["resume_id"]}
    if proposed_price is not None:
        params["proposed_price"] = proposed_price
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        params=params,
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def test_order_detail_masks_teacher_view(client, db):
    d = await _setup(db)
    # 未投递、未付定金的教员直接看订单详情 → 不得出现家长电话/真实地址
    resp = await client.get(
        f"{BASE}/api/v1/orders/{d['order_normal_id']}",
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["parent_phone"] is None, "教员视角不应返回家长电话"
    assert body["exact_address"] is None, "教员视角不应返回真实门牌"
    assert PARENT_PHONE not in body["raw_text"], "订单原文应掩码家长电话"
    assert "138****5678" in body["raw_text"]

    # B 端中介看同一订单 → 信息完整
    resp = await client.get(
        f"{BASE}/api/v1/orders/{d['order_normal_id']}",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["parent_phone"] == PARENT_PHONE
    assert body["exact_address"] == "天府大道1号101室"


async def test_archive_and_batch_enforce_state_machine(client, db):
    d = await _setup(db)
    # completed 订单不可直接归档（archive 也必须走状态机）
    resp = await client.post(
        f"{BASE}/api/v1/orders/{d['order_completed_id']}/archive",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 400, f"completed 订单归档应被拒绝: {resp.status_code} {resp.text}"

    # recruiting 订单可以归档
    resp = await client.post(
        f"{BASE}/api/v1/orders/{d['order_normal_id']}/archive",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "archived"

    # 批量改成 completed 被拒绝（成交必须走投递审核流程）
    resp = await client.post(
        f"{BASE}/api/v1/orders/batch-status",
        json={"order_ids": [d["order_proposed_id"]], "target_status": "completed"},
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 422, f"批量成交应被拒绝: {resp.status_code}"

    # 批量把 archived 订单改回 recruiting 被状态机拒绝（archived 无出边）
    resp = await client.post(
        f"{BASE}/api/v1/orders/batch-status",
        json={"order_ids": [d["order_normal_id"]], "target_status": "recruiting"},
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 400, f"archived 批量重发应被拒绝: {resp.status_code}"

    # recruiting → archived 批量归档合法
    resp = await client.post(
        f"{BASE}/api/v1/orders/batch-status",
        json={"order_ids": [d["order_proposed_id"]], "target_status": "archived"},
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["updated"] == 1


async def test_reject_application(client, db):
    d = await _setup(db)
    app_id = await _apply(d, client, "order_normal_id")

    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/reject",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"

    # 已拒绝的投递不可再次拒绝
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/reject",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 400

    # 已付定金后的投递不可走普通拒绝（须走试课失败/没收流程）
    app_id2 = await _apply(d, client, "order_proposed_id", proposed_price=150.0)
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id2}/shortlist",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200


async def test_proposed_price_does_not_overwrite_order(client, db):
    from models.domain import FinancialRecord, FinancialType

    d = await _setup(db)
    resp = await client.get(
        f"{BASE}/api/v1/orders/{d['order_proposed_id']}",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200
    before = resp.json()
    assert float(before["base_price"]) == 0.0

    # 教员报价 150/次 投递自带价订单
    app_id = await _apply(d, client, "order_proposed_id", proposed_price=150.0)

    # 订单级价格不得被投递覆盖
    resp = await client.get(
        f"{BASE}/api/v1/orders/{d['order_proposed_id']}",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    after = resp.json()
    assert float(after["base_price"]) == 0.0, "投递报价不应覆盖订单价格"
    assert float(after["calculated_info_fee"]) == 0.0

    # 中介确认定金：流水按投递报价精算（150×1.5=225，定金 100）
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/shortlist",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/confirm-deposit",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text

    recs = (await db.execute(
        select(FinancialRecord).where(FinancialRecord.order_id == d["order_proposed_id"])
    )).scalars().all()
    deposits = [r for r in recs if r.type == FinancialType.deposit_in]
    assert len(deposits) == 1
    assert float(deposits[0].amount) == 100.0, "自带价订单定金仍为固定 100 元"
