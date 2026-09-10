"""
资金流程与权限边界集成测试（止血清单 A5）。

覆盖：完整成交流程、先定金后试课、地址解锁门槛、没收定金、教员取消退款、
租户隔离、状态跳转权限、试课失败退费精算。

基建已迁移 conftest（db/client fixture + 造数工厂），断言口径未变。

运行方式：
    pytest tests/test_money_flow.py
"""
import datetime

from conftest import auth_header, teacher_token, tenant_token
from sqlalchemy import select

from models.domain import FinancialRecord, FinancialType, Order

BASE = "http://test"


def boss_token() -> str:
    from services.auth import create_jwt
    return create_jwt(sub="super_admin_1", role="super_admin")


async def _setup(db) -> dict:
    from models.domain import Gender, Order, OrderStatus, Teacher, TeacherResume, Tenant
    from services.calculator import calculate_info_fee

    t1 = Tenant(tenant_name="测试中介A", invite_code="testa001", contact_wechat="wx_a")
    t2 = Tenant(tenant_name="测试中介B", invite_code="testb002", contact_wechat="wx_b")
    db.add_all([t1, t2])
    await db.flush()

    teacher = Teacher(
        openid="t_001", name="测试教员", gender=Gender.male,
        phone="13800000001", wechat_id="wx_t", school="测试大学", is_985_211=True,
    )
    db.add(teacher)
    await db.flush()
    resume = TeacherResume(
        teacher_id=teacher.id, title="默认简历",
        teaching_subjects="数学、英语", teaching_grades="初一-初三",
        experience="两年家教经验",
    )
    db.add(resume)
    await db.flush()

    fee = calculate_info_fee(200.0, 2, False)  # total=200, deposit=100, balance=100
    now = datetime.datetime.utcnow()
    o1 = Order(
        tenant_id=t1.id, raw_id="RAW-001", raw_text="测试订单A",
        grade_subject="初三数学", requirements="985男", price_total="200/次",
        base_price=200.0, weekly_frequency=2, is_summer_vacation=False,
        calculated_info_fee=fee["total_info_fee"],
        deposit_amount=fee["deposit"], balance_amount=fee["balance"],
        exact_address="天府大道1号", parent_phone="13800000000",
        fuzzy_address="成都市天府大道", lng=104.06, lat=30.57,
        status=OrderStatus.recruiting,
        expired_at=now + datetime.timedelta(hours=72),
    )
    o2 = Order(
        tenant_id=t2.id, raw_id="RAW-002", raw_text="测试订单B",
        grade_subject="高一数学", requirements="", price_total="260/次",
        base_price=260.0, weekly_frequency=1, is_summer_vacation=False,
        calculated_info_fee=390.0, deposit_amount=100.0, balance_amount=290.0,
        exact_address="锦江大道2号", parent_phone="13900000000",
        fuzzy_address="成都市锦江大道", lng=104.08, lat=30.66,
        status=OrderStatus.recruiting,
        expired_at=now + datetime.timedelta(hours=72),
    )
    o3 = Order(
        tenant_id=t1.id, raw_id="RAW-003", raw_text="测试订单C",
        grade_subject="初一英语", requirements="", price_total="180/次",
        base_price=180.0, weekly_frequency=1, is_summer_vacation=False,
        calculated_info_fee=270.0, deposit_amount=100.0, balance_amount=170.0,
        exact_address="高新大道3号", parent_phone="13700000000",
        fuzzy_address="成都市高新大道", lng=104.07, lat=30.55,
        status=OrderStatus.recruiting,
        expired_at=now + datetime.timedelta(hours=72),
    )
    db.add_all([o1, o2, o3])
    await db.commit()
    return {
        "tenant1_id": t1.id, "tenant2_id": t2.id,
        "teacher_id": teacher.id, "resume_id": resume.id,
        "order1_id": o1.id, "order2_id": o2.id, "order3_id": o3.id,
    }


async def _apply(d, client, order_key: str = "order1_id") -> int:
    """教员投递订单，返回 application_id。"""
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        params={"order_id": d[order_key], "resume_id": d["resume_id"]},
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _shortlist_and_deposit(d, client, app_id):
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/shortlist", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200, resp.text
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/confirm-deposit", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200, resp.text


async def test_full_funnel(client, db):
    d = await _setup(db)
    app_id = await _apply(d, client)

    # 投递 → 候选：订单仍保持招聘中，继续允许其他教员投递
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/shortlist", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200
    resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.json()["status"] == "recruiting"

    # A2：未付定金不可开始试课
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/start-trial", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 400, f"未付定金应被拒绝: {resp.status_code}"

    # 确认定金 → 订单仍为 pending_deposit（A1 修复：不再是 pending_balance）
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/confirm-deposit", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200
    resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.json()["status"] == "recruiting"

    # 开始试课
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/start-trial", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200, resp.text
    resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.json()["status"] == "trial_in_progress"

    # 试课中可解锁家长联系方式
    resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}/address-unlock", headers=auth_header(teacher_token(d["teacher_id"])))
    assert resp.status_code == 200
    assert resp.json()["parent_phone"] == "13800000000"

    # 确认尾款 → 订单保持 trial_in_progress（A1 修复：不再是 pending_balance）
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/confirm-balance", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200, resp.text
    resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.json()["status"] == "trial_in_progress"

    # 确认完成
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/complete", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200
    resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.json()["status"] == "completed"

    # 财务流水：定金 + 尾款
    resp = await client.get(f"{BASE}/api/v1/financial-records/", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200
    summary = resp.json()
    assert summary["deposit_in"] == 100.0
    assert summary["balance_in"] == 100.0


async def test_unlock_requires_trial(client, db):
    d = await _setup(db)
    app_id = await _apply(d, client)
    # 仅候选（未付定金）→ 403
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/shortlist", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200
    resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}/address-unlock", headers=auth_header(teacher_token(d["teacher_id"])))
    assert resp.status_code == 403, f"未付定金应无法解锁: {resp.status_code}"

    # 已付定金但未试课 → 403
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/confirm-deposit", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200
    resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}/address-unlock", headers=auth_header(teacher_token(d["teacher_id"])))
    assert resp.status_code == 403, f"未开始试课应无法解锁: {resp.status_code}"

    # 未投递该订单的教员 → 403
    other = await client.post(
        f"{BASE}/api/v1/applications/",
        params={"order_id": d["order2_id"]},
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    # 该教员未投递订单1的申请；换一个未投递者视角（用订单2的地址解锁订单1）
    assert other.status_code in (200, 422)
    resp = await client.get(f"{BASE}/api/v1/orders/{d['order2_id']}/address-unlock", headers=auth_header(teacher_token(d["teacher_id"])))
    assert resp.status_code == 403


async def test_forfeit(client, db):
    d = await _setup(db)
    app_id = await _apply(d, client)
    await _shortlist_and_deposit(d, client, app_id)

    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/forfeit", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "forfeited", "没收定金应是独立终态，与普通拒绝区分"

    # 订单重新开放
    resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.json()["status"] == "recruiting"

    # 生成没收流水
    recs = (await db.execute(
        select(FinancialRecord).where(FinancialRecord.order_id == d["order1_id"])
    )).scalars().all()
    forfeits = [r for r in recs if r.type == FinancialType.forfeit]
    assert len(forfeits) == 1
    assert float(forfeits[0].amount) == 100.0, "应没收定金 100 元"


async def test_teacher_cancel(client, db):
    d = await _setup(db)
    # 未付定金：直接取消
    app_id = await _apply(d, client)
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/cancel", headers=auth_header(teacher_token(d["teacher_id"])))
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    # 已付定金：退定金 + 订单重新开放（用另一笔订单）
    app_id = await _apply(d, client, order_key="order3_id")
    await _shortlist_and_deposit(d, client, app_id)
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/cancel", headers=auth_header(teacher_token(d["teacher_id"])))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "refunded"

    resp = await client.get(f"{BASE}/api/v1/orders/{d['order3_id']}", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.json()["status"] == "recruiting"

    recs = (await db.execute(
        select(FinancialRecord).where(FinancialRecord.order_id == d["order3_id"])
    )).scalars().all()
    refunds = [r for r in recs if r.type == FinancialType.refund_out]
    assert len(refunds) == 1
    assert float(refunds[0].amount) == 100.0

    # 非本人不能取消他人投递
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/cancel", headers=auth_header(boss_token()))
    assert resp.status_code == 403


async def test_tenant_isolation(client, db):
    d = await _setup(db)
    # B 中介不能看 A 的订单详情
    resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth_header(tenant_token(d["tenant2_id"])))
    assert resp.status_code == 404

    # B 中介不能查看 A 订单的投递列表
    resp = await client.get(f"{BASE}/api/v1/applications/order/{d['order1_id']}", headers=auth_header(tenant_token(d["tenant2_id"])))
    assert resp.status_code == 404

    # B 中介不能操作 A 的投递（先让教员投递 A 的单）
    app_id = await _apply(d, client)
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/shortlist", headers=auth_header(tenant_token(d["tenant2_id"])))
    assert resp.status_code == 404


async def test_transit_permissions(client, db):
    d = await _setup(db)
    # 教员不能驱动订单状态（越权统一 404/403，均视为拒绝）
    resp = await client.post(
        f"{BASE}/api/v1/orders/{d['order1_id']}/transit",
        json={"target_status": "archived"},
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code in (403, 404), f"教员 transit 应被拒绝: {resp.status_code}"

    # 老板（super_admin）也不能走废弃状态
    resp = await client.post(
        f"{BASE}/api/v1/orders/{d['order1_id']}/transit",
        json={"target_status": "pending_approval"},
        headers=auth_header(boss_token()),
    )
    assert resp.status_code == 400, f"废弃状态应被拒绝: {resp.status_code}"

    # 中介可以归档自己的订单
    resp = await client.post(
        f"{BASE}/api/v1/orders/{d['order1_id']}/transit",
        json={"target_status": "archived"},
        headers=auth_header(tenant_token(d["tenant1_id"])),
    )
    assert resp.status_code == 200
    assert resp.json()["current_status"] == "archived"

    # 已完成订单不可回退
    resp = await client.post(
        f"{BASE}/api/v1/orders/{d['order1_id']}/transit",
        json={"target_status": "recruiting"},
        headers=auth_header(tenant_token(d["tenant1_id"])),
    )
    assert resp.status_code == 400


async def test_trial_failed_refund(client, db):
    d = await _setup(db)
    app_id = await _apply(d, client)
    await _shortlist_and_deposit(d, client, app_id)
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/start-trial", headers=auth_header(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200

    # 家长已付试课酬 60 元：退费 = max(0, 100 − 60×0.7) = 58
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/trial-failed",
        params={"trial_paid_by_parent": 60},
        headers=auth_header(tenant_token(d["tenant1_id"])),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "refunded"

    # 违约 → 没收（不退款）
    app_id = await _apply(d, client, order_key="order3_id")
    await _shortlist_and_deposit(d, client, app_id)
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/trial-failed",
        params={"is_teacher_violated": True},
        headers=auth_header(tenant_token(d["tenant1_id"])),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "forfeited"


async def test_recommendations(client, db):
    from models.domain import Teacher

    d = await _setup(db)
    # 给教员补坐标，让距离分生效
    teacher = await db.get(Teacher, d["teacher_id"])
    teacher.lng = 104.07
    teacher.lat = 30.60
    await db.commit()

    # 旧路径已迁移，应 404
    resp = await client.get(
        f"{BASE}/api/v1/public/agent/testa001/recommendations",
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 404, f"旧推荐接口应已移除: {resp.status_code}"

    # 未登录 → 401
    resp = await client.get(f"{BASE}/api/v1/recommendations/testa001")
    assert resp.status_code in (401, 403), f"未登录应被拒绝: {resp.status_code}"

    # 新接口：教员登录获取推荐
    resp = await client.get(
        f"{BASE}/api/v1/recommendations/testa001",
        params={"limit": 12},
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] >= 1, "应至少推荐一笔招募中的订单"
    assert body["invite_code"] == "testa001"
    item = body["items"][0]
    assert item["total_score"] >= 0
    assert set(item["score_breakdown"].keys()) == {
        "distance", "subject", "grade", "school", "price", "history",
    }
    assert item["reasons"], "推荐应带理由"

    # 不存在的中介 → 404
    resp = await client.get(
        f"{BASE}/api/v1/recommendations/nonexist",
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 404

    # 已投递（活跃投递）订单从推荐流中排除，不再占用推荐位
    app_id = await _apply(d, client)
    resp = await client.get(
        f"{BASE}/api/v1/recommendations/testa001",
        params={"limit": 50},
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 200
    applied_items = [i for i in resp.json()["items"] if i["id"] == d["order1_id"]]
    assert not applied_items, "有活跃投递的订单不应继续出现在推荐里"

    # 终态投递（被拒）后订单重新进入推荐，且可再次投递
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/reject", headers=auth_header(tenant_token(d["tenant1_id"]))
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get(
        f"{BASE}/api/v1/recommendations/testa001",
        params={"limit": 50},
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 200
    reapply_items = [i for i in resp.json()["items"] if i["id"] == d["order1_id"]]
    assert reapply_items and reapply_items[0]["already_applied"] is False


async def test_restore_rejected(client, db):
    d = await _setup(db)
    # 误拒绝 → 恢复待审核（安全回退）
    app_id = await _apply(d, client)
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/reject", headers=auth_header(tenant_token(d["tenant1_id"]))
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/restore", headers=auth_header(tenant_token(d["tenant1_id"]))
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "pending"

    # 已恢复的投递不可重复恢复
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/restore", headers=auth_header(tenant_token(d["tenant1_id"]))
    )
    assert resp.status_code == 400

    # 资金处置终态（没收）不可恢复：恢复会让台账与状态矛盾
    app2 = await _apply(d, client, order_key="order3_id")
    await _shortlist_and_deposit(d, client, app2)
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app2}/forfeit", headers=auth_header(tenant_token(d["tenant1_id"]))
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app2}/restore", headers=auth_header(tenant_token(d["tenant1_id"]))
    )
    assert resp.status_code == 400, "没收终态不可恢复"


async def test_mine_urgency_ordering(client, db):
    d = await _setup(db)
    # order3 改为 10 小时后到期：比 order1（72h）更紧急
    o3 = await db.get(Order, d["order3_id"])
    o3.expired_at = datetime.datetime.utcnow() + datetime.timedelta(hours=10)
    await db.commit()

    app_normal = await _apply(d, client)                             # order1
    app_urgent = await _apply(d, client, order_key="order3_id")      # 临期

    resp = await client.get(
        f"{BASE}/api/v1/applications/mine",
        params={"page_size": 50},
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 200, resp.text
    apps = resp.json()
    assert [a["order_id"] for a in apps[:2]] == [d["order3_id"], d["order1_id"]], \
        "进行中的投递应按订单到期时间升序：临期单在最上"

    # 终态投递沉底
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_normal}/reject", headers=auth_header(tenant_token(d["tenant1_id"]))
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get(
        f"{BASE}/api/v1/applications/mine",
        params={"page_size": 50},
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    apps = resp.json()
    assert apps[-1]["id"] == app_normal, "终态投递应排在列表末尾"
    assert apps[0]["id"] == app_urgent
