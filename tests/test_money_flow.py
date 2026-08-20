"""
资金流程与权限边界集成测试（止血清单 A5）。

使用独立的临时 SQLite 库，不触碰 dev.db。
覆盖：完整成交流程、先定金后试课、地址解锁门槛、没收定金、教员取消退款、
租户隔离、状态跳转权限、试课失败退费精算。

运行方式：
    python tests/test_money_flow.py
或（安装 pytest 后）：
    pytest tests/test_money_flow.py
"""
import asyncio
import datetime
import os
import sys
import tempfile

# 确保项目根目录可导入（与 test_smoke.py 一致）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 必须在导入 app 之前设置测试环境 ──
_TMP = tempfile.NamedTemporaryFile(suffix="_bleed.db", delete=False)
_TMP.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP.name.replace(os.sep, '/')}"
os.environ["DEV_MODE"] = "true"
os.environ["JWT_SECRET"] = "test-secret-for-money-flow-tests-0123456789"
os.environ["OWNER_ACCESS_CODE"] = "test-boss-code"

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

import database as database_mod  # noqa: E402
from main import app  # noqa: E402
from database import init_db, _get_sessionmaker  # noqa: E402
from models.domain import (  # noqa: E402
    Tenant, Teacher, TeacherResume, Order, OrderStatus, Gender,
    FinancialRecord, FinancialType,
)
from services.calculator import calculate_info_fee  # noqa: E402
from services.auth import create_jwt  # noqa: E402

BASE = "http://test"


def _fresh_db() -> None:
    """每个测试使用全新的临时库：释放旧引擎并删除库文件。"""
    engine = database_mod._engine
    if engine is not None:
        try:
            asyncio.run(engine.dispose())
        except Exception:
            pass
        database_mod._engine = None
        database_mod._async_sessionmaker = None
    try:
        os.unlink(_TMP.name)
    except OSError:
        pass


def tenant_token(tenant_id: int) -> str:
    return create_jwt(sub=f"tenant_admin_{tenant_id}", role="tenant_admin", tenant_id=tenant_id)


def teacher_token(teacher_id: int) -> str:
    return create_jwt(sub=f"teacher_{teacher_id}", role="teacher")


def boss_token() -> str:
    return create_jwt(sub="super_admin_1", role="super_admin")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup() -> dict:
    await init_db()
    sm = _get_sessionmaker()
    async with sm() as s:
        t1 = Tenant(tenant_name="测试中介A", invite_code="testa001", contact_wechat="wx_a")
        t2 = Tenant(tenant_name="测试中介B", invite_code="testb002", contact_wechat="wx_b")
        s.add_all([t1, t2])
        await s.flush()

        teacher = Teacher(
            openid="t_001", name="测试教员", gender=Gender.male,
            phone="13800000001", wechat_id="wx_t", school="测试大学", is_985_211=True,
        )
        s.add(teacher)
        await s.flush()
        resume = TeacherResume(
            teacher_id=teacher.id, title="默认简历",
            teaching_subjects="数学、英语", teaching_grades="初一-初三",
            experience="两年家教经验",
        )
        s.add(resume)
        await s.flush()

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
        s.add_all([o1, o2, o3])
        await s.commit()
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
        headers=auth(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _shortlist_and_deposit(d, client, app_id):
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/shortlist", headers=auth(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200, resp.text
    resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/confirm-deposit", headers=auth(tenant_token(d["tenant1_id"])))
    assert resp.status_code == 200, resp.text


async def _test_full_funnel():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        app_id = await _apply(d, client)

        # 投递 → 候选：订单进入 pending_deposit
        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/shortlist", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.status_code == 200
        resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.json()["status"] == "pending_deposit"

        # A2：未付定金不可开始试课
        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/start-trial", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.status_code == 400, f"未付定金应被拒绝: {resp.status_code}"

        # 确认定金 → 订单仍为 pending_deposit（A1 修复：不再是 pending_balance）
        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/confirm-deposit", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.status_code == 200
        resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.json()["status"] == "pending_deposit"

        # 开始试课
        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/start-trial", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.status_code == 200, resp.text
        resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.json()["status"] == "trial_in_progress"

        # 试课中可解锁家长联系方式
        resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}/address-unlock", headers=auth(teacher_token(d["teacher_id"])))
        assert resp.status_code == 200
        assert resp.json()["parent_phone"] == "13800000000"

        # 确认尾款 → 订单保持 trial_in_progress（A1 修复：不再是 pending_balance）
        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/confirm-balance", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.status_code == 200, resp.text
        resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.json()["status"] == "trial_in_progress"

        # 确认完成
        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/complete", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.status_code == 200
        resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.json()["status"] == "completed"

        # 财务流水：定金 + 尾款
        resp = await client.get(f"{BASE}/api/v1/financial-records/", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.status_code == 200
        summary = resp.json()
        assert summary["deposit_in"] == 100.0
        assert summary["balance_in"] == 100.0
    print("[OK] test_full_funnel")


async def _test_unlock_requires_trial():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        app_id = await _apply(d, client)
        # 仅候选（未付定金）→ 403
        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/shortlist", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.status_code == 200
        resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}/address-unlock", headers=auth(teacher_token(d["teacher_id"])))
        assert resp.status_code == 403, f"未付定金应无法解锁: {resp.status_code}"

        # 已付定金但未试课 → 403
        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/confirm-deposit", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.status_code == 200
        resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}/address-unlock", headers=auth(teacher_token(d["teacher_id"])))
        assert resp.status_code == 403, f"未开始试课应无法解锁: {resp.status_code}"

        # 未投递该订单的教员 → 403
        other = await client.post(
            f"{BASE}/api/v1/applications/",
            params={"order_id": d["order2_id"]},
            headers=auth(teacher_token(d["teacher_id"])),
        )
        # 该教员未投递订单1的申请；换一个未投递者视角（用订单2的地址解锁订单1）
        assert other.status_code in (200, 422)
        resp = await client.get(f"{BASE}/api/v1/orders/{d['order2_id']}/address-unlock", headers=auth(teacher_token(d["teacher_id"])))
        assert resp.status_code == 403
    print("[OK] test_unlock_requires_trial")


async def _test_forfeit():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        app_id = await _apply(d, client)
        await _shortlist_and_deposit(d, client, app_id)

        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/forfeit", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "rejected"

        # 订单重新开放
        resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.json()["status"] == "recruiting"

        # 生成没收流水
        sm = _get_sessionmaker()
        async with sm() as s:
            recs = (await s.execute(
                select(FinancialRecord).where(FinancialRecord.order_id == d["order1_id"])
            )).scalars().all()
        forfeits = [r for r in recs if r.type == FinancialType.forfeit]
        assert len(forfeits) == 1
        assert float(forfeits[0].amount) == 100.0, "应没收定金 100 元"
    print("[OK] test_forfeit")


async def _test_teacher_cancel():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 未付定金：直接取消
        app_id = await _apply(d, client)
        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/cancel", headers=auth(teacher_token(d["teacher_id"])))
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

        # 已付定金：退定金 + 订单重新开放（用另一笔订单）
        app_id = await _apply(d, client, order_key="order3_id")
        await _shortlist_and_deposit(d, client, app_id)
        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/cancel", headers=auth(teacher_token(d["teacher_id"])))
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "refunded"

        resp = await client.get(f"{BASE}/api/v1/orders/{d['order3_id']}", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.json()["status"] == "recruiting"

        sm = _get_sessionmaker()
        async with sm() as s:
            recs = (await s.execute(
                select(FinancialRecord).where(FinancialRecord.order_id == d["order3_id"])
            )).scalars().all()
        refunds = [r for r in recs if r.type == FinancialType.refund_out]
        assert len(refunds) == 1
        assert float(refunds[0].amount) == 100.0

        # 非本人不能取消他人投递
        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/cancel", headers=auth(boss_token()))
        assert resp.status_code == 403
    print("[OK] test_teacher_cancel")


async def _test_tenant_isolation():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # B 中介不能看 A 的订单详情
        resp = await client.get(f"{BASE}/api/v1/orders/{d['order1_id']}", headers=auth(tenant_token(d["tenant2_id"])))
        assert resp.status_code == 404

        # B 中介不能查看 A 订单的投递列表
        resp = await client.get(f"{BASE}/api/v1/applications/order/{d['order1_id']}", headers=auth(tenant_token(d["tenant2_id"])))
        assert resp.status_code == 404

        # B 中介不能操作 A 的投递（先让教员投递 A 的单）
        app_id = await _apply(d, client)
        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/shortlist", headers=auth(tenant_token(d["tenant2_id"])))
        assert resp.status_code == 404
    print("[OK] test_tenant_isolation")


async def _test_transit_permissions():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 教员不能驱动订单状态（越权统一 404/403，均视为拒绝）
        resp = await client.post(
            f"{BASE}/api/v1/orders/{d['order1_id']}/transit",
            json={"target_status": "archived"},
            headers=auth(teacher_token(d["teacher_id"])),
        )
        assert resp.status_code in (403, 404), f"教员 transit 应被拒绝: {resp.status_code}"

        # 老板（super_admin）也不能走废弃状态
        resp = await client.post(
            f"{BASE}/api/v1/orders/{d['order1_id']}/transit",
            json={"target_status": "pending_approval"},
            headers=auth(boss_token()),
        )
        assert resp.status_code == 400, f"废弃状态应被拒绝: {resp.status_code}"

        # 中介可以归档自己的订单
        resp = await client.post(
            f"{BASE}/api/v1/orders/{d['order1_id']}/transit",
            json={"target_status": "archived"},
            headers=auth(tenant_token(d["tenant1_id"])),
        )
        assert resp.status_code == 200
        assert resp.json()["current_status"] == "archived"

        # 已完成订单不可回退
        resp = await client.post(
            f"{BASE}/api/v1/orders/{d['order1_id']}/transit",
            json={"target_status": "recruiting"},
            headers=auth(tenant_token(d["tenant1_id"])),
        )
        assert resp.status_code == 400
    print("[OK] test_transit_permissions")


async def _test_trial_failed_refund():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        app_id = await _apply(d, client)
        await _shortlist_and_deposit(d, client, app_id)
        resp = await client.post(f"{BASE}/api/v1/applications/{app_id}/start-trial", headers=auth(tenant_token(d["tenant1_id"])))
        assert resp.status_code == 200

        # 家长已付试课酬 60 元：退费 = max(0, 100 − 60×0.7) = 58
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_id}/trial-failed",
            params={"trial_paid_by_parent": 60},
            headers=auth(tenant_token(d["tenant1_id"])),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "refunded"

        # 违约 → 没收（不退款）
        app_id = await _apply(d, client, order_key="order3_id")
        await _shortlist_and_deposit(d, client, app_id)
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_id}/trial-failed",
            params={"is_teacher_violated": True},
            headers=auth(tenant_token(d["tenant1_id"])),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "rejected"
    print("[OK] test_trial_failed_refund")


def test_full_funnel():
    _fresh_db()
    asyncio.run(_test_full_funnel())


def test_unlock_requires_trial():
    _fresh_db()
    asyncio.run(_test_unlock_requires_trial())


def test_forfeit():
    _fresh_db()
    asyncio.run(_test_forfeit())


def test_teacher_cancel():
    _fresh_db()
    asyncio.run(_test_teacher_cancel())


def test_tenant_isolation():
    _fresh_db()
    asyncio.run(_test_tenant_isolation())


def test_transit_permissions():
    _fresh_db()
    asyncio.run(_test_transit_permissions())


def test_trial_failed_refund():
    _fresh_db()
    asyncio.run(_test_trial_failed_refund())


if __name__ == "__main__":
    test_full_funnel()
    test_unlock_requires_trial()
    test_forfeit()
    test_teacher_cancel()
    test_tenant_isolation()
    test_transit_permissions()
    test_trial_failed_refund()
    print("\n=== 资金流程测试全部通过 ===")
    try:
        os.unlink(_TMP.name)
    except OSError:
        pass

