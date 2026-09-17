"""
认证与超管边缘回归测试（批次 C 覆盖率补强）。

此前全量套件下 routers/v1/auth.py 仅 67%、tenants.py 81%，本文件精准补齐缺口：
- dev 三件套的 DEV_MODE=true 快乐路径（登录/注册教员/建租户）；
- 微信登录与注册（mock code2session）：未注册 404 → 注册 → 登录；
- 资料编辑（无高德 Key 时坐标降级）与 /auth/me/profile 双角色分支；
- 租户自助改密后旧 token 失效；
- 手机号登录对"无密码遗留账号"的 400 口径、停用中介登录 403；
- 超管：租户列表、封禁/解封全流程、my-teachers 分页与导出、教员侧黑名单状态。

运行方式：
    pytest tests/test_admin_edges.py
"""

import pytest
from conftest import (
    auth_header,
    make_order,
    make_teacher,
    make_tenant,
    teacher_token,
    tenant_token,
)

from config import settings
from routers.v1 import auth as auth_router

BASE = "http://test"


def boss_token() -> str:
    from services.auth import create_jwt
    return create_jwt(sub="super_admin_1", role="super_admin")


# ── dev 三件套快乐路径（DEV_MODE=true） ──


async def test_dev_endpoints_happy_path(client, db):
    resp = await client.post(f"{BASE}/api/v1/auth/dev-tenant")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role"] == "tenant_admin"
    assert body["tenant"]["invite_code"] == "tx886"

    resp = await client.post(f"{BASE}/api/v1/auth/dev-register")
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "teacher"

    # 重复注册 → 409；注册后 dev-login 可登录
    resp = await client.post(f"{BASE}/api/v1/auth/dev-register")
    assert resp.status_code == 409

    resp = await client.post(f"{BASE}/api/v1/auth/dev-login")
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "teacher"


# ── 微信登录 / 注册（mock code2session） ──


@pytest.fixture()
def fake_wx(monkeypatch):
    """固定返回同一个 openid，绕过微信外呼。"""
    async def _fake(code: str) -> dict:
        return {"openid": "wx_probe_openid", "session_key": "x"}
    monkeypatch.setattr(auth_router, "wx_code2session", _fake)


async def test_wx_login_unregistered_then_register_then_login(client, db, fake_wx):
    # 未注册 → 404 引导注册
    resp = await client.post(f"{BASE}/api/v1/auth/teacher-login", json={"code": "c1"})
    assert resp.status_code == 404

    resp = await client.post(
        f"{BASE}/api/v1/auth/teacher-register",
        params={"code": "c1"},
        json={"name": "微信教员", "gender": "male", "phone": "13877770001",
              "wechat_id": "wx_probe", "school": "测试大学"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "teacher"

    # 重复注册 → 409；随后微信登录成功
    resp = await client.post(
        f"{BASE}/api/v1/auth/teacher-register",
        params={"code": "c1"},
        json={"name": "微信教员", "gender": "male", "phone": "13877770001",
              "wechat_id": "wx_probe", "school": "测试大学"},
    )
    assert resp.status_code == 409

    resp = await client.post(f"{BASE}/api/v1/auth/teacher-login", json={"code": "c1"})
    assert resp.status_code == 200, resp.text


# ── 资料编辑与 /me/profile ──


async def test_teacher_profile_patch_and_me_profile(client, db, monkeypatch):
    monkeypatch.setattr(settings, "AMAP_API_KEY", "")  # 无 Key：地理编码跳过，保存不受阻
    teacher = await make_teacher(db, "edge_teacher_a")
    await db.commit()
    headers = auth_header(teacher_token(teacher.id))

    resp = await client.patch(
        f"{BASE}/api/v1/auth/teacher/profile",
        json={"name": "改名教员", "home_area": "成都·武侯区"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "改名教员"
    assert body["home_area"] == "成都·武侯区"

    # /me/profile：教员分支返回 teacher 明细
    resp = await client.get(f"{BASE}/api/v1/auth/me/profile", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["teacher"]["name"] == "改名教员"

    # /me/profile：租户分支返回 tenant 信息
    tenant = await make_tenant(db, "edge001a")
    await db.commit()
    resp = await client.get(
        f"{BASE}/api/v1/auth/me/profile", headers=auth_header(tenant_token(tenant.id))
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["tenant"]["invite_code"] == "edge001a"


# ── 密码与会话口径 ──


async def _tenant_with_password(db, invite_code: str, *, is_active: bool = True, password: str = "dev123456"):
    """造一个带真实可登录密码的租户（conftest 工厂的哈希是占位串）。"""
    from services.auth import hash_password_async

    tenant = await make_tenant(db, invite_code, is_active=is_active)
    tenant.password_hash = await hash_password_async(password)
    await db.flush()
    return tenant


async def test_tenant_self_change_password_revokes_tokens(client, db):
    await _tenant_with_password(db, "edge002a")
    await db.commit()

    resp = await client.post(
        f"{BASE}/api/v1/auth/tenant-login",
        json={"invite_code": "edge002a", "password": "dev123456"},
    )
    assert resp.status_code == 200, resp.text
    old_token = resp.json()["token"]

    resp = await client.post(
        f"{BASE}/api/v1/auth/tenant-change-password",
        json={"old_password": "dev123456", "new_password": "newpass123"},
        headers=auth_header(old_token),
    )
    assert resp.status_code == 200, resp.text

    # 旧 token 立即失效；新密码可登录
    resp = await client.get(
        f"{BASE}/api/v1/auth/me", headers=auth_header(old_token)
    )
    assert resp.status_code == 401

    resp = await client.post(
        f"{BASE}/api/v1/auth/tenant-login",
        json={"invite_code": "edge002a", "password": "newpass123"},
    )
    assert resp.status_code == 200, resp.text


async def test_phone_login_legacy_account_without_password(client, db):
    tenant = await make_tenant(db, "edge003a")
    teacher = await make_teacher(db, "edge_teacher_b")
    await db.commit()

    resp = await client.post(
        f"{BASE}/api/v1/auth/teacher-phone-login",
        json={"phone": teacher.phone, "invite_code": tenant.invite_code, "password": "whatever1"},
    )
    assert resp.status_code == 400
    assert "未设置密码" in resp.json()["detail"]


async def test_tenant_login_inactive_403_after_correct_password(client, db):
    tenant = await _tenant_with_password(db, "edge004a", is_active=False)
    await db.commit()

    resp = await client.post(
        f"{BASE}/api/v1/auth/tenant-login",
        json={"invite_code": tenant.invite_code, "password": "dev123456"},
    )
    assert resp.status_code == 403
    assert "停用" in resp.json()["detail"]


# ── 超管：租户列表 / 封禁 / my-teachers 分页导出 / 黑名单状态 ──


async def _apply(client, d: dict) -> int:
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        json={"order_id": d["order_id"], "resume_id": d["resume_id"]},
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def test_boss_tenant_list_shape(client, db):
    await make_tenant(db, "edge005a")
    await make_tenant(db, "edge005b")
    await db.commit()

    resp = await client.get(f"{BASE}/api/v1/tenants/", headers=auth_header(boss_token()))
    assert resp.status_code == 200, resp.text
    items = resp.json()
    codes = {t["invite_code"] for t in items}
    assert {"edge005a", "edge005b"} <= codes
    assert "tenant_name" in items[0]

    # 非超管不可访问
    resp = await client.get(f"{BASE}/api/v1/tenants/", headers=auth_header(tenant_token(1)))
    assert resp.status_code in (401, 403)


async def test_ban_unban_flow_blocks_apply(client, db):
    d_tenant = await make_tenant(db, "edge006a")
    d_teacher = await make_teacher(db, "edge_teacher_c")
    from models.domain import TeacherResume
    resume = TeacherResume(
        teacher_id=d_teacher.id, title="默认简历",
        teaching_subjects="数学", teaching_grades="初一-初三", experience="两年经验",
    )
    db.add(resume)
    order = await make_order(db, d_tenant.id, "EDGE-001")
    await db.commit()

    # 封禁
    resp = await client.patch(
        f"{BASE}/api/v1/tenants/teachers/{d_teacher.id}/ban",
        json={"is_banned": True},
        headers=auth_header(boss_token()),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_banned"] is True

    # 封禁后投递被拒：403 = is_banned 拦截；401 = 封禁同秒内签发的 token 被
    # token_valid_after 一并吊销（宁可多踢一次登录的既有口径），两者都算封禁生效
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        json={"order_id": order.id, "resume_id": resume.id},
        headers=auth_header(teacher_token(d_teacher.id)),
    )
    assert resp.status_code in (401, 403)

    # 解封后恢复。等待跨过封禁写入 token_valid_after 的那一秒：
    # 真实场景是"解封后重新登录"，iat 必然晚于 token_valid_after
    import asyncio
    await asyncio.sleep(1.1)
    resp = await client.patch(
        f"{BASE}/api/v1/tenants/teachers/{d_teacher.id}/ban",
        json={"is_banned": False},
        headers=auth_header(boss_token()),
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        json={"order_id": order.id, "resume_id": resume.id},
        headers=auth_header(teacher_token(d_teacher.id)),
    )
    assert resp.status_code == 200, resp.text


async def test_my_teachers_pagination_and_export(client, db):
    tenant = await make_tenant(db, "edge007a")
    t1 = await make_teacher(db, "edge_teacher_d", name="教员D")
    from models.domain import TeacherResume
    resume = TeacherResume(
        teacher_id=t1.id, title="默认简历",
        teaching_subjects="数学", teaching_grades="初一-初三", experience="经验",
    )
    db.add(resume)
    order = await make_order(db, tenant.id, "EDGE-002")
    await db.commit()
    await client.post(
        f"{BASE}/api/v1/applications/",
        json={"order_id": order.id, "resume_id": resume.id},
        headers=auth_header(teacher_token(t1.id)),
    )
    headers = auth_header(tenant_token(tenant.id))

    # 全量与分页
    resp = await client.get(f"{BASE}/api/v1/tenants/my-teachers", headers=headers)
    assert resp.status_code == 200, resp.text
    total = len(resp.json())
    assert total >= 1

    resp = await client.get(
        f"{BASE}/api/v1/tenants/my-teachers",
        params={"page": 1, "page_size": 1},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 1

    # CSV 导出
    resp = await client.get(f"{BASE}/api/v1/tenants/my-teachers/export", headers=headers)
    assert resp.status_code == 200, resp.text
    assert "text/csv" in resp.headers["content-type"]


async def test_teacher_blacklist_status_view(client, db):
    tenant = await make_tenant(db, "edge008a")
    t1 = await make_teacher(db, "edge_teacher_e")
    await db.commit()

    # 无拉黑记录 → 空列表
    resp = await client.get(
        f"{BASE}/api/v1/tenants/blacklist-status",
        headers=auth_header(teacher_token(t1.id)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []

    resp = await client.post(
        f"{BASE}/api/v1/tenants/teachers/{t1.id}/blacklist",
        json={"reason": "违规"},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 200, resp.text

    resp = await client.get(
        f"{BASE}/api/v1/tenants/blacklist-status",
        headers=auth_header(teacher_token(t1.id)),
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) == 1
    assert items[0]["tenant_id"] == tenant.id
    assert items[0]["reason"] == "违规"
