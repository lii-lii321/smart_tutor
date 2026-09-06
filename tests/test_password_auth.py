"""
密码认证回归测试：教员/中介密码登录、错误统一化、限流、改密与重置。

使用独立的临时 SQLite 库，不触碰 dev.db。
运行方式：
    python tests/test_password_auth.py
或：
    pytest tests/test_password_auth.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 必须在导入 app 之前设置测试环境 ──
_TMP = tempfile.NamedTemporaryFile(suffix="_pwauth.db", delete=False)
_TMP.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP.name.replace(os.sep, '/')}"
os.environ["DEV_MODE"] = "true"
os.environ["JWT_SECRET"] = "test-secret-for-password-auth-0123456789"
os.environ["OWNER_ACCESS_CODE"] = "test-boss-code"

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

import database as database_mod  # noqa: E402
from main import app  # noqa: E402
from database import init_db, _get_sessionmaker  # noqa: E402
from models.domain import Tenant, Teacher, Gender  # noqa: E402
from services.auth import create_jwt  # noqa: E402

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


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_legacy_tenant_and_teacher(invite_code: str, phone: str):
    """直接落库：模拟未设置密码的历史账号。返回 (tenant_id, teacher_id)。"""
    sm = _get_sessionmaker()
    async with sm() as s:
        tenant = Tenant(
            tenant_name="历史中介", invite_code=invite_code,
            contact_wechat="wx_legacy",
        )
        teacher = Teacher(
            openid=f"legacy_{phone}", name="历史教员", gender=Gender.male,
            phone=phone, wechat_id="wx_legacy_t", school="测试大学", is_985_211=True,
        )
        s.add_all([tenant, teacher])
        await s.flush()
        ids = (tenant.id, teacher.id)
        await s.commit()
        return ids


async def _test_teacher_register_and_login():
    await init_db()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 老板创建中介（带密码）
        resp = await client.post(
            f"{BASE}/api/v1/tenants/",
            json={"tenant_name": "密码测试中介", "contact_wechat": "wx_pw"},
            headers=auth(boss_token()),
        )
        assert resp.status_code == 200, resp.text
        created = resp.json()
        assert created["initial_password"], "创建中介必须返回一次性初始密码"

        invite_code = created["invite_code"]

        # 注册缺少密码 → 422
        resp = await client.post(
            f"{BASE}/api/v1/auth/teacher-phone-register",
            json={
                "phone": "13811110001", "invite_code": invite_code,
                "name": "张三", "gender": "male", "wechat_id": "wx_z", "school": "川大",
            },
        )
        assert resp.status_code == 422, f"缺密码应 422: {resp.status_code}"

        # 正常注册（带密码）
        resp = await client.post(
            f"{BASE}/api/v1/auth/teacher-phone-register",
            json={
                "phone": "13811110001", "invite_code": invite_code, "password": "secret123",
                "name": "张三", "gender": "male", "wechat_id": "wx_z", "school": "川大",
            },
        )
        assert resp.status_code == 200, resp.text

        # 密码错误 → 400 统一提示
        resp = await client.post(
            f"{BASE}/api/v1/auth/teacher-phone-login",
            json={"phone": "13811110001", "invite_code": invite_code, "password": "wrong-pw"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "手机号或密码错误"

        # 密码正确 → 200
        resp = await client.post(
            f"{BASE}/api/v1/auth/teacher-phone-login",
            json={"phone": "13811110001", "invite_code": invite_code, "password": "secret123"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["role"] == "teacher"
        assert body["teacher"]["name"] == "张三"
    print("[OK] teacher_register_and_login")


async def _test_legacy_teacher_without_password():
    await init_db()
    _, teacher_id = await _create_legacy_tenant_and_teacher("lgcy0001", "13822220002")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post(
            f"{BASE}/api/v1/auth/teacher-phone-login",
            json={"phone": "13822220002", "invite_code": "lgcy0001", "password": "whatever1"},
        )
        assert resp.status_code == 400
        assert "未设置密码" in resp.json()["detail"]
    print("[OK] legacy_teacher_without_password")


async def _test_tenant_login_with_password():
    await init_db()
    await _create_legacy_tenant_and_teacher("lgcy0002", "13822220003")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 老板创建中介
        resp = await client.post(
            f"{BASE}/api/v1/tenants/",
            json={"tenant_name": "中介B", "contact_wechat": "wx_b", "password": "boss-given-pw"},
            headers=auth(boss_token()),
        )
        assert resp.status_code == 200, resp.text
        invite_code = resp.json()["invite_code"]
        assert resp.json()["initial_password"] == "boss-given-pw"

        # 密码错误 → 401 统一提示（不区分邀请码无效）
        resp = await client.post(
            f"{BASE}/api/v1/auth/tenant-login",
            json={"invite_code": invite_code, "password": "wrong-wrong"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "邀请码或密码错误"

        # 无效邀请码 + 任意密码 → 同样 401 同样文案
        resp = await client.post(
            f"{BASE}/api/v1/auth/tenant-login",
            json={"invite_code": "no-such-code", "password": "whatever1"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "邀请码或密码错误"

        # 历史中介（无密码）→ 401，不可凭邀请码直接进入
        resp = await client.post(
            f"{BASE}/api/v1/auth/tenant-login",
            json={"invite_code": "lgcy0002", "password": "whatever1"},
        )
        assert resp.status_code == 401, f"无密码中介不应被邀请码单独放行: {resp.status_code}"

        # 密码正确 → 200
        resp = await client.post(
            f"{BASE}/api/v1/auth/tenant-login",
            json={"invite_code": invite_code, "password": "boss-given-pw"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == "tenant_admin"
    print("[OK] tenant_login_with_password")


async def _test_tenant_reset_password():
    await init_db()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post(
            f"{BASE}/api/v1/tenants/",
            json={"tenant_name": "中介C", "contact_wechat": "wx_c", "password": "first-pw-1"},
            headers=auth(boss_token()),
        )
        assert resp.status_code == 200, resp.text
        tenant_id = resp.json()["id"]
        invite_code = resp.json()["invite_code"]

        # 中介先用初始密码登录，拿到旧 token
        resp = await client.post(
            f"{BASE}/api/v1/auth/tenant-login",
            json={"invite_code": invite_code, "password": "first-pw-1"},
        )
        assert resp.status_code == 200, resp.text
        old_tenant_token = resp.json()["token"]

        # token 失效判定按秒粒度（iat 严格早于 token_valid_after 才拒绝），
        # 等待跨秒以模拟真实时序：改密必然晚于登录
        await asyncio.sleep(1.1)

        # 非老板不可重置
        resp = await client.post(
            f"{BASE}/api/v1/tenants/{tenant_id}/reset-password",
            json={},
        )
        assert resp.status_code in (401, 403)

        # 老板重置 → 返回新明文密码
        resp = await client.post(
            f"{BASE}/api/v1/tenants/{tenant_id}/reset-password",
            headers=auth(boss_token()),
        )
        assert resp.status_code == 200, resp.text
        new_password = resp.json()["initial_password"]
        assert new_password and new_password != "first-pw-1"

        # 重置后旧 token 立即失效
        resp = await client.get(
            f"{BASE}/api/v1/auth/me/profile", headers=auth(old_tenant_token)
        )
        assert resp.status_code == 401, f"重置后旧 token 应失效: {resp.status_code}"

        # 旧密码失效，新密码可登录
        resp = await client.post(
            f"{BASE}/api/v1/auth/tenant-login",
            json={"invite_code": invite_code, "password": "first-pw-1"},
        )
        assert resp.status_code == 401
        resp = await client.post(
            f"{BASE}/api/v1/auth/tenant-login",
            json={"invite_code": invite_code, "password": new_password},
        )
        assert resp.status_code == 200, resp.text
    print("[OK] tenant_reset_password")


async def _test_change_password():
    await init_db()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post(
            f"{BASE}/api/v1/tenants/",
            json={"tenant_name": "中介D", "contact_wechat": "wx_d"},
            headers=auth(boss_token()),
        )
        invite_code = resp.json()["invite_code"]

        resp = await client.post(
            f"{BASE}/api/v1/auth/teacher-phone-register",
            json={
                "phone": "13833330004", "invite_code": invite_code, "password": "old-pass-1",
                "name": "李四", "gender": "female", "wechat_id": "wx_l", "school": "川大",
            },
        )
        assert resp.status_code == 200, resp.text
        teacher_token = resp.json()["token"]

        # 跨秒等待：token 失效按秒粒度判定（见 _test_tenant_reset_password 注释）
        await asyncio.sleep(1.1)

        # 原密码错误 → 400
        resp = await client.post(
            f"{BASE}/api/v1/auth/teacher-change-password",
            json={"old_password": "bad-old-1", "new_password": "new-pass-1"},
            headers=auth(teacher_token),
        )
        assert resp.status_code == 400

        # 原密码正确 → 更新成功
        resp = await client.post(
            f"{BASE}/api/v1/auth/teacher-change-password",
            json={"old_password": "old-pass-1", "new_password": "new-pass-1"},
            headers=auth(teacher_token),
        )
        assert resp.status_code == 200, resp.text

        # 新密码登录、旧密码失效
        resp = await client.post(
            f"{BASE}/api/v1/auth/teacher-phone-login",
            json={"phone": "13833330004", "invite_code": invite_code, "password": "old-pass-1"},
        )
        assert resp.status_code == 400
        resp = await client.post(
            f"{BASE}/api/v1/auth/teacher-phone-login",
            json={"phone": "13833330004", "invite_code": invite_code, "password": "new-pass-1"},
        )
        assert resp.status_code == 200, resp.text

        # 改密后旧 token 立即失效（token_valid_after 兜底）
        resp = await client.get(
            f"{BASE}/api/v1/auth/me/profile", headers=auth(teacher_token)
        )
        assert resp.status_code == 401, f"改密后旧 token 应失效: {resp.status_code}"
    print("[OK] change_password")


async def _test_owner_login_constant_compare():
    await init_db()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post(
            f"{BASE}/api/v1/auth/owner-login", json={"access_code": "bad-code"}
        )
        assert resp.status_code == 403
        resp = await client.post(
            f"{BASE}/api/v1/auth/owner-login", json={"access_code": "test-boss-code"}
        )
        assert resp.status_code == 200
        assert resp.json()["role"] == "super_admin"
    print("[OK] owner_login_constant_compare")


async def _test_login_rate_limit():
    await init_db()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 同一手机号连续失败 10 次后触发限流
        statuses = []
        for _ in range(11):
            resp = await client.post(
                f"{BASE}/api/v1/auth/teacher-phone-login",
                json={"phone": "13844440005", "invite_code": "anycode1", "password": "whatever1"},
            )
            statuses.append(resp.status_code)
        assert 429 in statuses, f"应触发登录限流: {statuses}"
        assert statuses[-1] == 429
        assert statuses[0] in (400, 404)
    print("[OK] login_rate_limit")


def test_teacher_register_and_login():
    _fresh_db()
    asyncio.run(_test_teacher_register_and_login())


def test_legacy_teacher_without_password():
    _fresh_db()
    asyncio.run(_test_legacy_teacher_without_password())


def test_tenant_login_with_password():
    _fresh_db()
    asyncio.run(_test_tenant_login_with_password())


def test_tenant_reset_password():
    _fresh_db()
    asyncio.run(_test_tenant_reset_password())


def test_change_password():
    _fresh_db()
    asyncio.run(_test_change_password())


def test_owner_login_constant_compare():
    _fresh_db()
    asyncio.run(_test_owner_login_constant_compare())


def test_login_rate_limit():
    _fresh_db()
    asyncio.run(_test_login_rate_limit())


if __name__ == "__main__":
    test_teacher_register_and_login()
    test_legacy_teacher_without_password()
    test_tenant_login_with_password()
    test_tenant_reset_password()
    test_change_password()
    test_owner_login_constant_compare()
    test_login_rate_limit()
    print("\n=== 密码认证测试全部通过 ===")
    try:
        os.unlink(_TMP.name)
    except OSError:
        pass
