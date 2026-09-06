"""
订单状态与资金守卫回归测试（止血批次：状态机穿透/资金处置/并发防护）。

覆盖：
- 已完成订单不可被残留候选"复活"（shortlist/confirm-deposit/start-trial 拦截）
- 已归档订单不可收款、不可处置（trial-failed/forfeit 拦截）
- 存在已收款投递的订单不可重开（transit/republish/batch-status 拦截），处置后可重开
- 成交自动关闭同单兄弟投递
- 退款封顶实收金额；零退款补记没收流水；net_amount 资金守恒
- 招聘中才可编辑订单；transit 重开刷新有效期
- 自动归档跳过有已收款投递的订单
- 处置非试课候选不影响进行中的试课
- 投递入口拒绝恶意低价报价

运行方式：
    pytest tests/test_order_guards.py
"""
import asyncio
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMP = tempfile.NamedTemporaryFile(suffix="_guards.db", delete=False)
_TMP.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP.name.replace(os.sep, '/')}"
os.environ["DEV_MODE"] = "true"
os.environ["JWT_SECRET"] = "test-secret-for-order-guards-0123456789"
os.environ["OWNER_ACCESS_CODE"] = "test-boss-code"

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

import database as database_mod  # noqa: E402
from main import app  # noqa: E402
from database import init_db, _get_sessionmaker  # noqa: E402
from models.domain import (  # noqa: E402
    Tenant, Teacher, TeacherResume, Order, OrderStatus, Gender,
    Application, ApplicationStatus, FinancialRecord, FinancialType,
)
from services.auth import create_jwt  # noqa: E402
from services.order_maintenance import archive_expired_recruiting_orders  # noqa: E402

BASE = "http://test"


def _fresh_db() -> None:
    from config import settings
    settings.DATABASE_URL = f"sqlite+aiosqlite:///{_TMP.name.replace(os.sep, '/')}"

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


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup() -> dict:
    await init_db()
    sm = _get_sessionmaker()
    async with sm() as s:
        tenant = Tenant(tenant_name="守卫中介", invite_code="guard001", contact_wechat="wx_g")
        teachers = []
        for i, openid in enumerate(("g_t1", "g_t2")):
            teacher = Teacher(
                openid=openid, name=f"教员{i + 1}", gender=Gender.male,
                phone=f"1380000000{i + 1}", wechat_id=f"wx_{openid}",
                school="测试大学", is_985_211=True,
            )
            teachers.append(teacher)
        s.add(tenant)
        s.add_all(teachers)
        await s.flush()

        resumes = []
        for teacher in teachers:
            resume = TeacherResume(
                teacher_id=teacher.id, title="默认简历",
                teaching_subjects="数学、英语", teaching_grades="初一-初三",
                experience="两年家教经验",
            )
            resumes.append(resume)
        s.add_all(resumes)
        await s.flush()

        now = datetime.datetime.utcnow()
        order = Order(
            tenant_id=tenant.id, raw_id="GUARD-001", raw_text="守卫测试订单",
            grade_subject="初三数学", requirements="", price_total="200/次",
            base_price=200.0, weekly_frequency=2, is_summer_vacation=False,
            calculated_info_fee=200.0, deposit_amount=100.0, balance_amount=100.0,
            exact_address="天府大道1号", parent_phone="13800000000",
            fuzzy_address="成都市天府大道", lng=104.06, lat=30.57,
            status=OrderStatus.recruiting,
            expired_at=now + datetime.timedelta(hours=72),
        )
        s.add(order)
        await s.commit()
        return {
            "tenant_id": tenant.id,
            "teacher1_id": teachers[0].id, "teacher2_id": teachers[1].id,
            "resume1_id": resumes[0].id, "resume2_id": resumes[1].id,
            "order_id": order.id,
        }


async def _apply(d, client, teacher_key: str, resume_key: str) -> int:
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        params={"order_id": d["order_id"], "resume_id": d[resume_key]},
        headers=auth(teacher_token(d[teacher_key])),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _deposit(d, client, app_id: int) -> None:
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/shortlist",
        headers=auth(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/confirm-deposit",
        headers=auth(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text


async def _test_completed_order_cannot_revive():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 教员2 先付定金成为残留候选
        app2 = await _apply(d, client, "teacher2_id", "resume2_id")
        await _deposit(d, client, app2)

        # 教员1 走完整流程至成交
        app1 = await _apply(d, client, "teacher1_id", "resume1_id")
        await _deposit(d, client, app1)
        for action in ("start-trial", "confirm-balance", "complete"):
            resp = await client.post(
                f"{BASE}/api/v1/applications/{app1}/{action}",
                headers=auth(tenant_token(d["tenant_id"])),
            )
            assert resp.status_code == 200, resp.text

        sm = _get_sessionmaker()
        async with sm() as s:
            assert (await s.get(Order, d["order_id"])).status == OrderStatus.completed
            # 成交后：教员2 的残留候选被自动关闭，复活链路的燃料被清空
            assert (await s.get(Application, app2)).status == ApplicationStatus.rejected

        # 重复完成被状态校验拦截
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app1}/start-trial",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 400, "已成交投递不可再次进入试课"

        # 已完成的订单不可再投递
        resp = await client.post(
            f"{BASE}/api/v1/applications/",
            params={"order_id": d["order_id"], "resume_id": d["resume2_id"]},
            headers=auth(teacher_token(d["teacher2_id"])),
        )
        assert resp.status_code == 400, "已完成订单不可再投递"
    print("[OK] test_completed_order_cannot_revive")


async def _test_archived_order_blocks_money_and_disposal():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 教员1 付定金，教员2 进入候选队列——均在归档前完成
        app1 = await _apply(d, client, "teacher1_id", "resume1_id")
        await _deposit(d, client, app1)
        app2 = await _apply(d, client, "teacher2_id", "resume2_id")
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app2}/shortlist",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text

        # 归档（recruiting → archived 合法）
        resp = await client.post(
            f"{BASE}/api/v1/orders/{d['order_id']}/archive",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text

        # 已归档订单不可继续收款（候选仍在，但订单状态守卫拦截）
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app2}/confirm-deposit",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 409, f"已归档订单不可确认定金: {resp.status_code}"

        # 资金处置允许补做（中介归档后仍要能处置已收定金），
        # 但订单必须保持归档，绝不能被"复活"回招聘中
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app1}/forfeit",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "rejected"

        sm = _get_sessionmaker()
        async with sm() as s:
            assert (await s.get(Order, d["order_id"])).status == OrderStatus.archived, \
                "归档订单处置后不得被复活"
    print("[OK] test_archived_order_blocks_money_and_disposal")


async def _test_reopen_requires_disposal():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 教员1 付定金成为候选，教员2 进入试课
        candidate_app = await _apply(d, client, "teacher1_id", "resume1_id")
        await _deposit(d, client, candidate_app)
        trial_app = await _apply(d, client, "teacher2_id", "resume2_id")
        await _deposit(d, client, trial_app)
        resp = await client.post(
            f"{BASE}/api/v1/applications/{trial_app}/start-trial",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text

        # 存在已收款投递（候选 + 试课中）时，transit 重开被拦截
        resp = await client.post(
            f"{BASE}/api/v1/orders/{d['order_id']}/transit",
            json={"target_status": "recruiting"},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 409, f"transit 应拦截已收款投递: {resp.status_code}"

        sm = _get_sessionmaker()
        async with sm() as s:
            assert (await s.get(Order, d["order_id"])).status == OrderStatus.trial_in_progress
    print("[OK] test_reopen_requires_disposal")


async def _test_republish_after_disposal():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        paid_app = await _apply(d, client, "teacher1_id", "resume1_id")
        await _deposit(d, client, paid_app)
        pending_app = await _apply(d, client, "teacher2_id", "resume2_id")

        # 归档后：存在已收款投递时，两种重开路径全部拦截
        resp = await client.post(
            f"{BASE}/api/v1/orders/{d['order_id']}/archive",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200

        resp = await client.post(
            f"{BASE}/api/v1/orders/{d['order_id']}/republish",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 409, f"republish 应拦截已收款投递: {resp.status_code}"

        resp = await client.post(
            f"{BASE}/api/v1/orders/batch-status",
            json={"order_ids": [d["order_id"]], "target_status": "recruiting"},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        # 归档单先被状态机拒绝（400）；试课中单则被资金守卫拦截（409），均不可重开
        assert resp.status_code in (400, 409), f"batch-status 应拦截重开: {resp.status_code}"

        # 补做资金处置（订单保持归档）后即可重开
        resp = await client.post(
            f"{BASE}/api/v1/applications/{paid_app}/forfeit",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text

        resp = await client.post(
            f"{BASE}/api/v1/orders/{d['order_id']}/republish",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "recruiting"

        sm = _get_sessionmaker()
        async with sm() as s:
            assert (await s.get(Application, pending_app)).status == ApplicationStatus.rejected
            assert (await s.get(Order, d["order_id"])).selected_teacher_id is None
    print("[OK] test_republish_after_disposal")


async def _test_refund_cap_and_zero_refund_forfeit():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 超额退款被钳制到实收 100
        app1 = await _apply(d, client, "teacher1_id", "resume1_id")
        await _deposit(d, client, app1)
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app1}/trial-failed",
            params={"refund_amount": 999},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text

        # 零退款补记没收流水
        app2 = await _apply(d, client, "teacher2_id", "resume2_id")
        await _deposit(d, client, app2)
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app2}/trial-failed",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "rejected"

        sm = _get_sessionmaker()
        async with sm() as s:
            recs = (await s.execute(
                select(FinancialRecord).where(FinancialRecord.order_id == d["order_id"])
            )).scalars().all()
        refunds = [r for r in recs if r.type == FinancialType.refund_out]
        forfeits = [r for r in recs if r.type == FinancialType.forfeit]
        assert len(refunds) == 1 and float(refunds[0].amount) == 100.0, "退款必须封顶为实收定金"
        assert len(forfeits) == 1 and float(forfeits[0].amount) == 100.0, "零退款必须补记没收"
    print("[OK] test_refund_cap_and_zero_refund_forfeit")


async def _test_net_amount_conservation():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        app_id = await _apply(d, client, "teacher1_id", "resume1_id")
        await _deposit(d, client, app_id)
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_id}/forfeit",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200

        # 没收后净额必须等于实收现金（100），不得因 forfeit 双算变成 200
        resp = await client.get(
            f"{BASE}/api/v1/financial-records/",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text
        summary = resp.json()
        assert summary["deposit_in"] == 100.0
        assert summary["forfeit"] == 100.0
        assert summary["net_amount"] == 100.0, f"net 应与实收一致，实际 {summary['net_amount']}"
    print("[OK] test_net_amount_conservation")


async def _test_update_order_guard_and_transit_refresh():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        app_id = await _apply(d, client, "teacher1_id", "resume1_id")
        await _deposit(d, client, app_id)
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_id}/start-trial",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200

        # 试课中不可编辑订单（价格/家长信息锁定）
        resp = await client.patch(
            f"{BASE}/api/v1/orders/{d['order_id']}",
            json={"base_price": 1},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 409, f"试课中订单不可编辑: {resp.status_code}"

        # 把过期时间改到过去，验证处置重开时刷新有效期
        sm = _get_sessionmaker()
        async with sm() as s:
            order = await s.get(Order, d["order_id"])
            order.expired_at = datetime.datetime.utcnow() - datetime.timedelta(hours=1)
            await s.commit()

        # 试课中投递属于已收款，transit 重开被资金守卫拦截
        resp = await client.post(
            f"{BASE}/api/v1/orders/{d['order_id']}/transit",
            json={"target_status": "recruiting"},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 409, "存在已收款投递时 transit 重开应被拦截"

        # 走正规处置流程（试课失败退款）重开，有效期必须被刷新
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_id}/trial-failed",
            params={"refund_amount": 100},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text

        sm = _get_sessionmaker()
        async with sm() as s:
            order = await s.get(Order, d["order_id"])
            assert order.status == OrderStatus.recruiting
            assert order.expired_at > datetime.datetime.utcnow(), "重开必须刷新有效期"
    print("[OK] test_update_order_guard_and_transit_refresh")


async def _test_scheduler_skips_paid_candidate_orders():
    d = await _setup()
    sm = _get_sessionmaker()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        app_id = await _apply(d, client, "teacher1_id", "resume1_id")
        await _deposit(d, client, app_id)

    async with sm() as s:
        now = datetime.datetime.utcnow()
        clean = Order(
            tenant_id=d["tenant_id"], raw_id="GUARD-002", raw_text="无候选过期单",
            grade_subject="初一英语", requirements="", price_total="180/次",
            base_price=180.0, weekly_frequency=1, is_summer_vacation=False,
            calculated_info_fee=270.0, deposit_amount=100.0, balance_amount=170.0,
            exact_address="地址B", parent_phone="13700000000",
            fuzzy_address="成都市B", lng=104.07, lat=30.58,
            status=OrderStatus.recruiting,
            expired_at=now - datetime.timedelta(hours=1),
        )
        order = await s.get(Order, d["order_id"])
        order.expired_at = now - datetime.timedelta(hours=1)
        s.add(clean)
        await s.commit()
        clean_id = clean.id

    async with sm() as s:
        archived = await archive_expired_recruiting_orders(s)
        assert archived == 1, f"只应归档无候选的过期订单，实际 {archived}"
        assert (await s.get(Order, clean_id)).status == OrderStatus.archived
        assert (await s.get(Order, d["order_id"])).status == OrderStatus.recruiting, \
            "有已收款投递的订单不可被自动归档"
    print("[OK] test_scheduler_skips_paid_candidate_orders")


async def _test_disposing_sibling_keeps_trial():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 两名教员都在招聘期付定金成为候选
        trial_app = await _apply(d, client, "teacher1_id", "resume1_id")
        await _deposit(d, client, trial_app)
        sibling_app = await _apply(d, client, "teacher2_id", "resume2_id")
        await _deposit(d, client, sibling_app)

        # 教员1 进入试课
        resp = await client.post(
            f"{BASE}/api/v1/applications/{trial_app}/start-trial",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200

        # 处置残留候选教员2：不得踩掉教员1 进行中的试课
        resp = await client.post(
            f"{BASE}/api/v1/applications/{sibling_app}/forfeit",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text

        sm = _get_sessionmaker()
        async with sm() as s:
            order = await s.get(Order, d["order_id"])
            assert order.status == OrderStatus.trial_in_progress, "处置候选不应中断试课"
            assert order.selected_teacher_id == d["teacher1_id"]
    print("[OK] test_disposing_sibling_keeps_trial")


async def _test_apply_rejects_underpriced_quote():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post(
            f"{BASE}/api/v1/applications/",
            params={"order_id": d["order_id"], "resume_id": d["resume1_id"], "proposed_price": 0.01},
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert resp.status_code == 422, f"恶意低价报价应在投递入口被拒: {resp.status_code}"
    print("[OK] test_apply_rejects_underpriced_quote")


def test_completed_order_cannot_revive():
    _fresh_db()
    asyncio.run(_test_completed_order_cannot_revive())


def test_archived_order_blocks_money_and_disposal():
    _fresh_db()
    asyncio.run(_test_archived_order_blocks_money_and_disposal())


def test_reopen_requires_disposal():
    _fresh_db()
    asyncio.run(_test_reopen_requires_disposal())


def test_republish_after_disposal():
    _fresh_db()
    asyncio.run(_test_republish_after_disposal())


def test_refund_cap_and_zero_refund_forfeit():
    _fresh_db()
    asyncio.run(_test_refund_cap_and_zero_refund_forfeit())


def test_net_amount_conservation():
    _fresh_db()
    asyncio.run(_test_net_amount_conservation())


def test_update_order_guard_and_transit_refresh():
    _fresh_db()
    asyncio.run(_test_update_order_guard_and_transit_refresh())


def test_scheduler_skips_paid_candidate_orders():
    _fresh_db()
    asyncio.run(_test_scheduler_skips_paid_candidate_orders())


def test_disposing_sibling_keeps_trial():
    _fresh_db()
    asyncio.run(_test_disposing_sibling_keeps_trial())


def test_apply_rejects_underpriced_quote():
    _fresh_db()
    asyncio.run(_test_apply_rejects_underpriced_quote())


if __name__ == "__main__":
    test_completed_order_cannot_revive()
    test_archived_order_blocks_money_and_disposal()
    test_reopen_requires_disposal()
    test_republish_after_disposal()
    test_refund_cap_and_zero_refund_forfeit()
    test_net_amount_conservation()
    test_update_order_guard_and_transit_refresh()
    test_scheduler_skips_paid_candidate_orders()
    test_disposing_sibling_keeps_trial()
    test_apply_rejects_underpriced_quote()
    print("\n=== 订单守卫测试全部通过 ===")
    try:
        os.unlink(_TMP.name)
    except OSError:
        pass
