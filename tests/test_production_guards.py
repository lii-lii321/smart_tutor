"""
生产化批次回归测试：封禁/停用拦截、被拒重投、坐标降精度、脱敏强化、
站内通知、停用租户 token 实时失效、解析长度上限。

运行方式：
    pytest tests/test_production_guards.py
"""
import asyncio
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMP = tempfile.NamedTemporaryFile(suffix="_prod.db", delete=False)
_TMP.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP.name.replace(os.sep, '/')}"
os.environ["DEV_MODE"] = "true"
os.environ["JWT_SECRET"] = "test-secret-for-production-guards-0123456"
os.environ["OWNER_ACCESS_CODE"] = "test-boss-code"

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

import database as database_mod  # noqa: E402
from main import app  # noqa: E402
from database import init_db, _get_sessionmaker  # noqa: E402
from models.domain import (  # noqa: E402
    Tenant, Teacher, TeacherResume, Order, OrderStatus, Gender,
    Application, ApplicationStatus, Notification,
)
from services.auth import create_jwt  # noqa: E402

BASE = "http://test"
PARENT_PHONE = "13812345678"
RAW_TEXT = (
    "【测试单 91940393】家长 张女士，电话 138 1234 5678，"
    "微信号：zhangsan123，QQ：987654321，地址天府大道1号"
)


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


def boss_token() -> str:
    return create_jwt(sub="super_admin_1", role="super_admin")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup() -> dict:
    await init_db()
    sm = _get_sessionmaker()
    async with sm() as s:
        tenant = Tenant(tenant_name="生产中介", invite_code="prod0001", contact_wechat="wx_p")
        teacher = Teacher(
            openid="p_t1", name="生产教员", gender=Gender.male,
            phone="13800000001", wechat_id="wx_pt", school="测试大学", is_985_211=True,
        )
        s.add_all([tenant, teacher])
        await s.flush()
        resume = TeacherResume(
            teacher_id=teacher.id, title="默认简历",
            teaching_subjects="数学、英语", teaching_grades="初一-初三",
            experience="两年家教经验",
        )
        s.add(resume)
        await s.flush()

        order = Order(
            tenant_id=tenant.id, raw_id="PROD-001", raw_text=RAW_TEXT,
            grade_subject="初三数学", requirements="", price_total="200/次",
            base_price=200.0, weekly_frequency=2, is_summer_vacation=False,
            calculated_info_fee=200.0, deposit_amount=100.0, balance_amount=100.0,
            exact_address="天府大道1号101室", parent_phone=PARENT_PHONE,
            fuzzy_address="成都市天府大道", lng=104.065735, lat=30.659462,
            status=OrderStatus.recruiting,
            expired_at=datetime.datetime.utcnow() + datetime.timedelta(hours=72),
        )
        s.add(order)
        await s.commit()
        return {
            "tenant_id": tenant.id, "teacher_id": teacher.id, "resume_id": resume.id,
            "order_id": order.id,
        }


async def _apply(d, client) -> int:
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        params={"order_id": d["order_id"], "resume_id": d["resume_id"]},
        headers=auth(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _test_banned_teacher_blocked():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.patch(
            f"{BASE}/api/v1/tenants/teachers/{d['teacher_id']}/ban",
            json={"is_banned": True},
            headers=auth(boss_token()),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_banned"] is True

        resp = await client.post(
            f"{BASE}/api/v1/applications/",
            params={"order_id": d["order_id"], "resume_id": d["resume_id"]},
            headers=auth(teacher_token(d["teacher_id"])),
        )
        assert resp.status_code == 403, f"封禁教员不可投递: {resp.status_code}"

        resp = await client.get(
            f"{BASE}/api/v1/recommendations/prod0001",
            headers=auth(teacher_token(d["teacher_id"])),
        )
        assert resp.status_code == 403, f"封禁教员不可获取推荐: {resp.status_code}"

        # 非老板不可封禁
        resp = await client.patch(
            f"{BASE}/api/v1/tenants/teachers/{d['teacher_id']}/ban",
            json={"is_banned": True},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 403

        # 解封后恢复
        resp = await client.patch(
            f"{BASE}/api/v1/tenants/teachers/{d['teacher_id']}/ban",
            json={"is_banned": False},
            headers=auth(boss_token()),
        )
        assert resp.status_code == 200
    print("[OK] test_banned_teacher_blocked")


async def _test_inactive_tenant_blocked():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.patch(
            f"{BASE}/api/v1/tenants/{d['tenant_id']}/status",
            json={"is_active": False},
            headers=auth(boss_token()),
        )
        assert resp.status_code == 200

        resp = await client.post(
            f"{BASE}/api/v1/applications/",
            params={"order_id": d["order_id"], "resume_id": d["resume_id"]},
            headers=auth(teacher_token(d["teacher_id"])),
        )
        assert resp.status_code == 403, f"停用中介不可被投递: {resp.status_code}"

        resp = await client.get(
            f"{BASE}/api/v1/recommendations/prod0001",
            headers=auth(teacher_token(d["teacher_id"])),
        )
        assert resp.status_code == 404, "停用中介推荐应与不存在同样 404"

        # 公开橱窗对停用中介关闭
        resp = await client.get(f"{BASE}/api/v1/public/agent/prod0001/board")
        assert resp.status_code == 404
    print("[OK] test_inactive_tenant_blocked")


async def _test_tenant_token_invalidated_after_deactivate():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        token = tenant_token(d["tenant_id"])
        resp = await client.get(f"{BASE}/api/v1/orders/", headers=auth(token))
        assert resp.status_code == 200

        await client.patch(
            f"{BASE}/api/v1/tenants/{d['tenant_id']}/status",
            json={"is_active": False},
            headers=auth(boss_token()),
        )

        # 已签发的 72h token 在停用后立即失效
        resp = await client.get(f"{BASE}/api/v1/orders/", headers=auth(token))
        assert resp.status_code == 403, f"停用后旧 token 应立即失效: {resp.status_code}"
    print("[OK] test_tenant_token_invalidated_after_deactivate")


async def _test_reapply_after_rejection():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        app_id = await _apply(d, client)

        # 未终结的投递不可重复投递
        resp = await client.post(
            f"{BASE}/api/v1/applications/",
            params={"order_id": d["order_id"], "resume_id": d["resume_id"]},
            headers=auth(teacher_token(d["teacher_id"])),
        )
        assert resp.status_code == 409

        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_id}/reject",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200

        # 被拒后可重新投递，复用同一投递行并重置为待审核
        resp = await client.post(
            f"{BASE}/api/v1/applications/",
            params={"order_id": d["order_id"], "resume_id": d["resume_id"]},
            headers=auth(teacher_token(d["teacher_id"])),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == app_id
        assert body["status"] == "pending"

        # 复用历史行：rejected_at 已清空
        sm = _get_sessionmaker()
        async with sm() as s:
            revived = await s.get(Application, app_id)
            assert revived.rejected_at is None
            assert revived.applied_at is not None

        # 拒绝动作产生了站内通知
        resp = await client.get(
            f"{BASE}/api/v1/notifications/mine",
            headers=auth(teacher_token(d["teacher_id"])),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["unread_count"] >= 1
        assert any(n["title"] == "投递未通过" for n in data["items"])

        # 一键已读
        resp = await client.post(
            f"{BASE}/api/v1/notifications/read-all",
            headers=auth(teacher_token(d["teacher_id"])),
        )
        assert resp.status_code == 200
        resp = await client.get(
            f"{BASE}/api/v1/notifications/mine",
            headers=auth(teacher_token(d["teacher_id"])),
        )
        assert resp.json()["unread_count"] == 0
    print("[OK] test_reapply_after_rejection")


async def _test_teacher_view_coarse_and_masked():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.get(
            f"{BASE}/api/v1/orders/{d['order_id']}",
            headers=auth(teacher_token(d["teacher_id"])),
        )
        assert resp.status_code == 200
        body = resp.json()
        # 坐标截断到 3 位小数
        assert body["lng"] == 104.066, f"教员视角经度应降精度: {body['lng']}"
        assert body["lat"] == 30.659, f"教员视角纬度应降精度: {body['lat']}"
        # 家长信息不出现
        assert body["parent_phone"] is None
        assert body["exact_address"] is None
        assert PARENT_PHONE not in body["raw_text"]
        assert "138****5678" in body["raw_text"], "带空格手机号应被掩码"
        assert "zh****23" in body["raw_text"], "微信号应被掩码"
        assert "98****21" in body["raw_text"], "QQ 号应被掩码"

        # B 端视角保持精确坐标与完整信息
        resp = await client.get(
            f"{BASE}/api/v1/orders/{d['order_id']}",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        body = resp.json()
        assert body["lng"] == 104.065735
        assert body["parent_phone"] == PARENT_PHONE
    print("[OK] test_teacher_view_coarse_and_masked")


async def _test_notifications_on_complete_flow():
    d = await _setup()
    sm = _get_sessionmaker()
    async with sm() as s:
        teacher2 = Teacher(
            openid="p_t2", name="第二教员", gender=Gender.female,
            phone="13800000002", wechat_id="wx_pt2", school="测试大学", is_985_211=True,
        )
        s.add(teacher2)
        await s.flush()
        resume2 = TeacherResume(
            teacher_id=teacher2.id, title="默认简历",
            teaching_subjects="数学", teaching_grades="初一-初三",
            experience="三年家教经验",
        )
        s.add(resume2)
        await s.commit()
        d["teacher2_id"] = teacher2.id
        d["resume2_id"] = resume2.id

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        winner = await _apply(d, client)
        async with sm() as s:
            pass

        # 教员2 也投递（复用 _apply 逻辑，但用 teacher2 身份）
        resp = await client.post(
            f"{BASE}/api/v1/applications/",
            params={"order_id": d["order_id"], "resume_id": d["resume2_id"]},
            headers=auth(teacher_token(d["teacher2_id"])),
        )
        assert resp.status_code == 200, resp.text
        loser = resp.json()["id"]

        for app_id, tkey in ((winner, "tenant_id"),):
            pass

        # 教员1 走完整流程
        await client.post(f"{BASE}/api/v1/applications/{winner}/shortlist", headers=auth(tenant_token(d["tenant_id"])))
        await client.post(f"{BASE}/api/v1/applications/{winner}/confirm-deposit", headers=auth(tenant_token(d["tenant_id"])))
        await client.post(f"{BASE}/api/v1/applications/{winner}/start-trial", headers=auth(tenant_token(d["tenant_id"])))
        await client.post(f"{BASE}/api/v1/applications/{winner}/confirm-balance", headers=auth(tenant_token(d["tenant_id"])))
        resp = await client.post(
            f"{BASE}/api/v1/applications/{winner}/complete",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text

        # 教员2 收到落选通知
        resp = await client.get(
            f"{BASE}/api/v1/notifications/mine",
            headers=auth(teacher_token(d["teacher2_id"])),
        )
        data = resp.json()
        assert any(n["title"] == "未被选中" for n in data["items"]), f"应收到落选通知: {data}"

        # 教员1 收到成交通知
        resp = await client.get(
            f"{BASE}/api/v1/notifications/mine",
            headers=auth(teacher_token(d["teacher_id"])),
        )
        titles = [n["title"] for n in resp.json()["items"]]
        assert "恭喜成交" in titles
        assert "试课开始" in titles
    print("[OK] test_notifications_on_complete_flow")


async def _test_batch_parse_length_limit():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post(
            f"{BASE}/api/v1/orders/batch-parse",
            json={"raw_text": "订单" * 20000},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 422, f"超长文本应被 422 拒绝: {resp.status_code}"
    print("[OK] test_batch_parse_length_limit")


def test_banned_teacher_blocked():
    _fresh_db()
    asyncio.run(_test_banned_teacher_blocked())


def test_inactive_tenant_blocked():
    _fresh_db()
    asyncio.run(_test_inactive_tenant_blocked())


def test_tenant_token_invalidated_after_deactivate():
    _fresh_db()
    asyncio.run(_test_tenant_token_invalidated_after_deactivate())


def test_reapply_after_rejection():
    _fresh_db()
    asyncio.run(_test_reapply_after_rejection())


def test_teacher_view_coarse_and_masked():
    _fresh_db()
    asyncio.run(_test_teacher_view_coarse_and_masked())


def test_notifications_on_complete_flow():
    _fresh_db()
    asyncio.run(_test_notifications_on_complete_flow())


def test_batch_parse_length_limit():
    _fresh_db()
    asyncio.run(_test_batch_parse_length_limit())


if __name__ == "__main__":
    test_banned_teacher_blocked()
    test_inactive_tenant_blocked()
    test_tenant_token_invalidated_after_deactivate()
    test_reapply_after_rejection()
    test_teacher_view_coarse_and_masked()
    test_notifications_on_complete_flow()
    test_batch_parse_length_limit()
    print("\n=== 生产化守卫测试全部通过 ===")
    try:
        os.unlink(_TMP.name)
    except OSError:
        pass
