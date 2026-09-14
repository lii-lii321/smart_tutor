"""
横向越权参数化矩阵测试（第 5 阶段）。

系统化覆盖两类越权面，此前只有零散的单点断言：
- B 端跨租户：中介 A 的管理员不能读/改中介 B 的订单与投递（统一 404 防枚举）；
- C 端跨教员：教员 B 不能取消教员 A 的投递、改教员 A 的简历、解锁无投递订单的家长信息。

运行方式：
    pytest tests/test_authz_matrix.py
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

from models.domain import TeacherResume

BASE = "http://test"


async def _setup_world(db) -> dict:
    """两个租户 × 两个教员 × 各自订单/投递/简历，返回完整句柄。"""
    tenant_a = await make_tenant(db, "azwaaa01", name="中介A")
    tenant_b = await make_tenant(db, "azwbbb02", name="中介B")
    teacher_a = await make_teacher(db, "az_teacher_a", name="教员A")
    teacher_b = await make_teacher(db, "az_teacher_b", name="教员B")

    resume_a = TeacherResume(
        teacher_id=teacher_a.id, title="A的简历",
        teaching_subjects="数学", teaching_grades="初一-初三", experience="两年经验",
    )
    resume_b = TeacherResume(
        teacher_id=teacher_b.id, title="B的简历",
        teaching_subjects="数学", teaching_grades="初一-初三", experience="三年经验",
    )
    db.add_all([resume_a, resume_b])
    order_a = await make_order(db, tenant_a.id, "AZ-A01")
    order_b = await make_order(db, tenant_b.id, "AZ-B01")
    await db.commit()
    return {
        "tenant_a": tenant_a.id, "tenant_b": tenant_b.id,
        "teacher_a": teacher_a.id, "teacher_b": teacher_b.id,
        "resume_a": resume_a.id, "resume_b": resume_b.id,
        "order_a": order_a.id, "order_b": order_b.id,
    }


async def _apply(client, d: dict, teacher_key: str, order_key: str, resume_key: str) -> int:
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        json={"order_id": d[order_key], "resume_id": d[resume_key]},
        headers=auth_header(teacher_token(d[teacher_key])),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _b_headers(tenant_id: int) -> dict:
    return auth_header(tenant_token(tenant_id))


# ── B 端跨租户：中介 B 操作中介 A 的资源 ──


@pytest.mark.parametrize("method,path_builder,body", [
    ("GET", lambda oid: f"{BASE}/api/v1/orders/{oid}", None),
    ("PATCH", lambda oid: f"{BASE}/api/v1/orders/{oid}", {"grade_subject": "被篡改"}),
    ("POST", lambda oid: f"{BASE}/api/v1/orders/{oid}/archive", None),
    ("POST", lambda oid: f"{BASE}/api/v1/orders/{oid}/republish", None),
])
async def test_cross_tenant_order_writes_blocked(client, db, method, path_builder, body):
    d = await _setup_world(db)
    resp = await client.request(
        method, path_builder(d["order_a"]), json=body, headers=_b_headers(d["tenant_b"])
    )
    assert resp.status_code == 404, f"跨租户 {method} 应 404: {resp.status_code}"


async def test_cross_tenant_cannot_see_or_touch_applications(client, db):
    d = await _setup_world(db)
    app_a = await _apply(client, d, "teacher_a", "order_a", "resume_a")

    # 中介 B 看不到中介 A 订单的投递列表
    resp = await client.get(
        f"{BASE}/api/v1/applications/order/{d['order_a']}", headers=_b_headers(d["tenant_b"])
    )
    assert resp.status_code == 404

    # 中介 B 对中介 A 的投递做任何状态操作都被 404 拦截
    for action in ("shortlist", "reject", "confirm-deposit", "start-trial", "complete"):
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_a}/{action}", headers=_b_headers(d["tenant_b"])
        )
        assert resp.status_code == 404, f"跨租户 {action} 应 404: {resp.status_code}"

    # 真正的归属方操作正常
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/shortlist", headers=_b_headers(d["tenant_a"])
    )
    assert resp.status_code == 200, resp.text


async def test_cross_tenant_export_scoped(client, db):
    d = await _setup_world(db)
    resp = await client.get(
        f"{BASE}/api/v1/orders/export", params={"q": "AZ-A01"}, headers=_b_headers(d["tenant_b"])
    )
    assert resp.status_code == 200, resp.text
    # 中介 B 导出里不应出现中介 A 的订单编号
    assert "AZ-A01" not in resp.text


# ── C 端跨教员：教员 B 操作教员 A 的资源 ──


async def test_cross_teacher_cancel_and_unlock_blocked(client, db):
    d = await _setup_world(db)
    app_a = await _apply(client, d, "teacher_a", "order_a", "resume_a")

    # 教员 B 不能取消教员 A 的投递
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/cancel",
        headers=auth_header(teacher_token(d["teacher_b"])),
    )
    assert resp.status_code == 404

    # 教员 B 无投递则不能解锁教员 A 所投订单的家长信息
    resp = await client.get(
        f"{BASE}/api/v1/orders/{d['order_a']}/address-unlock",
        headers=auth_header(teacher_token(d["teacher_b"])),
    )
    assert resp.status_code == 403

    # 教员 B 未投递时连教员 A 租户的订单详情都不可见
    # （recruiting 单按设计全平台教员可见，但敏感字段必须已脱敏）
    resp = await client.get(
        f"{BASE}/api/v1/orders/{d['order_a']}",
        headers=auth_header(teacher_token(d["teacher_b"])),
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["parent_phone"] is None, "教员视角不得泄露家长电话"
    assert detail["exact_address"] is None, "教员视角不得泄露真实门牌"

    # 归档后：无投递的教员 B 立即失去可见性（404 防枚举）
    resp = await client.post(
        f"{BASE}/api/v1/orders/{d['order_a']}/archive", headers=_b_headers(d["tenant_a"])
    )
    assert resp.status_code == 200, resp.text
    resp = await client.get(
        f"{BASE}/api/v1/orders/{d['order_a']}",
        headers=auth_header(teacher_token(d["teacher_b"])),
    )
    assert resp.status_code == 404, "归档单对无投递教员应不可见"


@pytest.mark.parametrize("method,path_builder,body", [
    ("PATCH", lambda rid: f"{BASE}/api/v1/teacher/resumes/{rid}", {"title": "被篡改"}),
    ("DELETE", lambda rid: f"{BASE}/api/v1/teacher/resumes/{rid}", None),
    ("POST", lambda rid: f"{BASE}/api/v1/teacher/resumes/{rid}/default", None),
])
async def test_cross_teacher_resume_writes_blocked(client, db, method, path_builder, body):
    d = await _setup_world(db)
    resp = await client.request(
        method, path_builder(d["resume_a"]),
        json=body, headers=auth_header(teacher_token(d["teacher_b"])),
    )
    assert resp.status_code == 404, f"跨教员简历 {method} 应 404: {resp.status_code}"
