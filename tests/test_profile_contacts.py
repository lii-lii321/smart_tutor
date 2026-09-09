"""
资料编辑与联系方式触达回归测试：
- 教员自助编辑基础资料/常驻地（无高德 Key 时优雅降级）；
- 橱窗下发中介微信；投递列表下发教员联系方式；
- 教员取消投递产生 B 端通知；新设密码复杂度校验。

使用独立的临时 SQLite 库，不触碰 dev.db。
运行方式：
    python tests/test_profile_contacts.py
或：
    pytest tests/test_profile_contacts.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 必须在导入 app 之前设置测试环境 ──
_TMP = tempfile.NamedTemporaryFile(suffix="_profile.db", delete=False)
_TMP.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP.name.replace(os.sep, '/')}"
os.environ["DEV_MODE"] = "true"
os.environ["JWT_SECRET"] = "test-secret-for-profile-contacts-0123456"
os.environ["OWNER_ACCESS_CODE"] = "test-boss-code"
os.environ["AMAP_API_KEY"] = ""

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

import database as database_mod  # noqa: E402
from config import settings as app_settings  # noqa: E402
from database import _get_sessionmaker, init_db  # noqa: E402
from main import app  # noqa: E402
from models.domain import Gender, Notification, Teacher, Tenant  # noqa: E402
from services.auth import create_jwt  # noqa: E402

# pytest 会先导入其他测试模块并创建 settings 单例（可能读到本机 .env 的高德 Key），
# 这里显式关闭，保证地理编码分支在 CI/本机行为一致：跳过网络调用、坐标保持为空
app_settings.AMAP_API_KEY = ""

BASE = "http://test"


def _fresh_db() -> None:
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


def boss_token() -> str:
    return create_jwt(sub="super_admin_1", role="super_admin")


def tenant_token(tenant_id: int) -> str:
    return create_jwt(sub=f"tenant_admin_{tenant_id}", role="tenant_admin", tenant_id=tenant_id)


def teacher_token(teacher_id: int) -> str:
    return create_jwt(sub=f"teacher_{teacher_id}", role="teacher")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_world(prefix: str, phone: str):
    """直接落库一套租户+教员，返回 (tenant_id, teacher_id)。"""
    sm = _get_sessionmaker()
    async with sm() as s:
        tenant = Tenant(
            tenant_name=f"{prefix}中介", invite_code=f"{prefix.lower()}01",
            contact_wechat=f"wx_{prefix.lower()}",
        )
        teacher = Teacher(
            openid=f"{prefix.lower()}_t", name=f"{prefix}教员", gender=Gender.male,
            phone=phone, wechat_id=f"wxid_{prefix.lower()}", school="测试大学",
            is_985_211=True,
        )
        s.add_all([tenant, teacher])
        await s.flush()
        ids = (tenant.id, teacher.id)
        await s.commit()
        return ids


async def _test_teacher_profile_update():
    await init_db()
    tenant_id, teacher_id = await _create_world("Profile", "13700000001")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 非教员角色禁止编辑
        resp = await client.patch(
            f"{BASE}/api/v1/auth/teacher/profile",
            json={"name": "改名"},
            headers=auth(tenant_token(tenant_id)),
        )
        assert resp.status_code == 403, f"中介不应能改教员资料: {resp.status_code}"

        # 正常编辑：基础字段 + 常驻地文本（测试环境无高德 Key，坐标保持为空但保存成功）
        resp = await client.patch(
            f"{BASE}/api/v1/auth/teacher/profile",
            json={
                "name": "改名教员",
                "major": "软件工程",
                "grade": "研三",
                "wechat_id": "new_wxid",
                "home_area": "成都·武侯区",
            },
            headers=auth(teacher_token(teacher_id)),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["name"] == "改名教员"
        assert body["wechat_id"] == "new_wxid"
        assert body["home_area"] == "成都·武侯区"
        assert body["lng"] is None and body["lat"] is None

        # 教员可见自己的联系方式（用于资料回填）
        assert body["phone"] == "13700000001"

        # 部分更新：未传字段保持不变
        resp = await client.patch(
            f"{BASE}/api/v1/auth/teacher/profile",
            json={"grade": "博一"},
            headers=auth(teacher_token(teacher_id)),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "改名教员"
        assert resp.json()["grade"] == "博一"

        # 教员带坐标更新常驻地（H5 定位场景）
        resp = await client.patch(
            f"{BASE}/api/v1/auth/teacher/profile",
            json={"home_area": "成都·锦江区", "lng": 104.1172, "lat": 30.5985},
            headers=auth(teacher_token(teacher_id)),
        )
        assert resp.status_code == 200, resp.text
        assert abs(resp.json()["lng"] - 104.1172) < 0.001
    print("[OK] teacher_profile_update")


async def _test_board_exposes_contact_wechat():
    await init_db()
    tenant_id, _teacher_id = await _create_world("BoardWx", "13700000002")
    sm = _get_sessionmaker()
    async with sm() as s:
        tenant = await s.get(Tenant, tenant_id)
        invite_code = tenant.invite_code
        contact = tenant.contact_wechat

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.get(f"{BASE}/api/v1/public/agent/{invite_code}/board")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["contact_wechat"] == contact, "橱窗必须下发中介微信供教员联系"

    # 教员登录响应也携带中介微信
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.get(
            f"{BASE}/api/v1/auth/me/profile", headers=auth(teacher_token(_teacher_id))
        )
        assert resp.status_code == 200
    print("[OK] board_exposes_contact_wechat")


async def _test_application_exposes_teacher_contact():
    await init_db()
    tenant_id, teacher_id = await _create_world("Contact", "13700000003")
    sm = _get_sessionmaker()
    async with sm() as s:
        from datetime import datetime, timedelta

        from models.domain import Application, Order, OrderStatus
        order = Order(
            tenant_id=tenant_id, raw_id="CT-001", raw_text="联系方式测试订单",
            grade_subject="初三数学", requirements="", price_total="200/次",
            base_price=200.0, weekly_frequency=2, is_summer_vacation=False,
            calculated_info_fee=200.0, deposit_amount=100.0, balance_amount=100.0,
            fuzzy_address="成都市某小区", lng=104.06, lat=30.57,
            status=OrderStatus.recruiting,
            expired_at=datetime.utcnow() + timedelta(days=3),
        )
        s.add(order)
        await s.flush()
        app_row = Application(
            order_id=order.id, teacher_id=teacher_id, tenant_id=tenant_id,
        )
        s.add(app_row)
        await s.commit()
        app_id, order_id = app_row.id, order.id

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # B 端投递列表能看到教员手机号/微信
        resp = await client.get(
            f"{BASE}/api/v1/applications/order/{order_id}",
            headers=auth(tenant_token(tenant_id)),
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert items[0]["teacher"]["phone"] == "13700000003"
        assert items[0]["teacher"]["wechat_id"] == "wxid_contact"

        # 其他租户看不到该订单投递（隔离不回退：越权 404 / 租户不存在 403）
        resp = await client.get(
            f"{BASE}/api/v1/applications/order/{order_id}",
            headers=auth(tenant_token(tenant_id + 100)),
        )
        assert resp.status_code in (403, 404), resp.status_code
    print("[OK] application_exposes_teacher_contact")


async def _test_cancel_notifies_tenant():
    await init_db()
    tenant_id, teacher_id = await _create_world("Cancel", "13700000005")
    sm = _get_sessionmaker()
    async with sm() as s:
        from datetime import datetime, timedelta

        from models.domain import Application, Order, OrderStatus
        order = Order(
            tenant_id=tenant_id, raw_id="CX-001", raw_text="取消通知测试订单",
            grade_subject="初一英语", requirements="", price_total="150/次",
            base_price=150.0, weekly_frequency=1, is_summer_vacation=False,
            calculated_info_fee=225.0, deposit_amount=100.0, balance_amount=125.0,
            fuzzy_address="成都市某小区", lng=104.06, lat=30.57,
            status=OrderStatus.recruiting,
            expired_at=datetime.utcnow() + timedelta(days=3),
        )
        s.add(order)
        await s.flush()
        app_row = Application(
            order_id=order.id, teacher_id=teacher_id, tenant_id=tenant_id,
        )
        s.add(app_row)
        await s.commit()
        app_id = app_row.id

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_id}/cancel",
            headers=auth(teacher_token(teacher_id)),
        )
        assert resp.status_code == 200, resp.text

    sm = _get_sessionmaker()
    async with sm() as s:
        rows = (await s.execute(
            select(Notification).where(
                Notification.tenant_id == tenant_id,
                Notification.title == "教员取消投递",
            )
        )).scalars().all()
        assert rows, "教员取消投递必须给中介写站内通知"
        assert "初一英语" in rows[0].content
    print("[OK] cancel_notifies_tenant")


async def _test_password_complexity_gate():
    await init_db()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 老板创建中介（自动密码），拿到邀请码
        resp = await client.post(
            f"{BASE}/api/v1/tenants/",
            json={"tenant_name": "复杂度中介", "contact_wechat": "wx_cx"},
            headers=auth(boss_token()),
        )
        assert resp.status_code == 200, resp.text
        invite_code = resp.json()["invite_code"]

        # 教员注册：纯数字密码 → 422
        resp = await client.post(
            f"{BASE}/api/v1/auth/teacher-phone-register",
            json={
                "phone": "13700000006", "invite_code": invite_code, "password": "123456",
                "name": "弱密码", "gender": "male", "wechat_id": "wx_weak", "school": "川大",
            },
        )
        assert resp.status_code == 422, f"纯数字密码应被拒绝: {resp.status_code}"

        # 老板显式指定纯字母密码 → 422
        resp = await client.post(
            f"{BASE}/api/v1/tenants/",
            json={"tenant_name": "弱密码中介", "contact_wechat": "wx_cx", "password": "abcdef"},
            headers=auth(boss_token()),
        )
        assert resp.status_code == 422, f"纯字母密码应被拒绝: {resp.status_code}"

        # 字母+数字 → 通过
        resp = await client.post(
            f"{BASE}/api/v1/auth/teacher-phone-register",
            json={
                "phone": "13700000006", "invite_code": invite_code, "password": "abc123",
                "name": "强密码", "gender": "male", "wechat_id": "wx_strong", "school": "川大",
            },
        )
        assert resp.status_code == 200, resp.text
    print("[OK] password_complexity_gate")


async def _test_mine_pagination():
    await init_db()
    tenant_id, teacher_id = await _create_world("Page", "13700000007")
    sm = _get_sessionmaker()
    async with sm() as s:
        from datetime import datetime, timedelta

        from models.domain import Application, Order, OrderStatus
        ids = []
        for i in range(3):
            order = Order(
                tenant_id=tenant_id, raw_id=f"PG-{i:03d}", raw_text=f"分页订单{i}",
                grade_subject="初三数学", requirements="", price_total="200/次",
                base_price=200.0, weekly_frequency=2, is_summer_vacation=False,
                calculated_info_fee=200.0, deposit_amount=100.0, balance_amount=100.0,
                fuzzy_address="成都市某小区", lng=104.06, lat=30.57,
                status=OrderStatus.recruiting,
                expired_at=datetime.utcnow() + timedelta(days=3),
            )
            s.add(order)
            await s.flush()
            s.add(Application(order_id=order.id, teacher_id=teacher_id, tenant_id=tenant_id))
            ids.append(order.id)
        await s.commit()

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 不带分页参数 → 全量（兼容旧调用）
        resp = await client.get(
            f"{BASE}/api/v1/applications/mine", headers=auth(teacher_token(teacher_id))
        )
        assert resp.status_code == 200 and len(resp.json()) == 3

        # 分页：每页 2 条
        resp = await client.get(
            f"{BASE}/api/v1/applications/mine",
            params={"page": 1, "page_size": 2},
            headers=auth(teacher_token(teacher_id)),
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2
        resp = await client.get(
            f"{BASE}/api/v1/applications/mine",
            params={"page": 2, "page_size": 2},
            headers=auth(teacher_token(teacher_id)),
        )
        assert len(resp.json()) == 1
    print("[OK] mine_pagination")


def test_teacher_profile_update():
    _fresh_db()
    asyncio.run(_test_teacher_profile_update())


def test_board_exposes_contact_wechat():
    _fresh_db()
    asyncio.run(_test_board_exposes_contact_wechat())


def test_application_exposes_teacher_contact():
    _fresh_db()
    asyncio.run(_test_application_exposes_teacher_contact())


def test_cancel_notifies_tenant():
    _fresh_db()
    asyncio.run(_test_cancel_notifies_tenant())


def test_password_complexity_gate():
    _fresh_db()
    asyncio.run(_test_password_complexity_gate())


def test_mine_pagination():
    _fresh_db()
    asyncio.run(_test_mine_pagination())


if __name__ == "__main__":
    test_teacher_profile_update()
    test_board_exposes_contact_wechat()
    test_application_exposes_teacher_contact()
    test_cancel_notifies_tenant()
    test_password_complexity_gate()
    test_mine_pagination()
    print("\n=== 资料编辑与联系方式测试全部通过 ===")
    try:
        os.unlink(_TMP.name)
    except OSError:
        pass
