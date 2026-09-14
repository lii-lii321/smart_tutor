"""
API 一致性与查询优化回归测试（第 3 阶段）。

覆盖：
- batch-status 批量重开与 transit/republish 同口径：清理未产生资金往来的活跃投递；
- 状态机放开 archived→recruiting 后，归档单重开统一被资金守卫拦截（409，不再 400）；
- 超管移出黑名单需显式 tenant_id（修复恒 404），缺参 422；
- 订单改价为 0（转自带价）时清空订单级费率；
- LIKE 关键字通配符按字面匹配（% 不再当通配符）。

运行方式：
    pytest tests/test_phase3_consistency.py
"""

from conftest import (
    auth_header,
    make_order,
    make_teacher,
    make_tenant,
    teacher_token,
    tenant_token,
)
from sqlalchemy import select

from models.domain import Application, ApplicationStatus, TenantTeacherBlacklist

BASE = "http://test"


async def _setup(db) -> dict:
    tenant = await make_tenant(db, "p3t00001")
    teacher_a = await make_teacher(db, "p3_teacher_a", name="教员A")
    teacher_b = await make_teacher(db, "p3_teacher_b", name="教员B")
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
    order = await make_order(db, tenant.id, "P3-001")
    await db.commit()
    return {
        "tenant_id": tenant.id,
        "order_id": order.id,
        "teacher_a": teacher_a.id, "resume_a": resume_a.id,
        "teacher_b": teacher_b.id, "resume_b": resume_b.id,
    }


def _tenant_headers(d: dict) -> dict:
    return auth_header(tenant_token(d["tenant_id"]))


async def _apply(client, d: dict, key: str) -> int:
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        json={"order_id": d["order_id"], "resume_id": d[f"resume_{key}"]},
        headers=auth_header(teacher_token(d[f"teacher_{key}"])),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def boss_token() -> str:
    from services.auth import create_jwt
    return create_jwt(sub="super_admin_1", role="super_admin")


async def test_batch_reopen_rejects_active_applications(client, db):
    d = await _setup(db)
    app_a = await _apply(client, d, "a")
    resp = await client.post(
        f"{BASE}/api/v1/orders/{d['order_id']}/archive", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text

    # 无资金往来时批量重开放行（状态机已放开 archived→recruiting），
    # 且与 transit/republish 同口径：pending 投递被清理
    resp = await client.post(
        f"{BASE}/api/v1/orders/batch-status",
        json={"order_ids": [d["order_id"]], "target_status": "recruiting"},
        headers=_tenant_headers(d),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["updated"] == 1

    app_row = (await db.execute(
        select(Application).where(Application.id == app_a)
    )).scalar_one()
    assert app_row.status == ApplicationStatus.rejected


async def test_batch_reopen_still_blocked_by_money_guard(client, db):
    d = await _setup(db)
    app_a = await _apply(client, d, "a")
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/shortlist", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/confirm-deposit", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/orders/{d['order_id']}/archive", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text

    # 有已收款投递：状态机放行后由资金守卫统一拦截（409），三路径口径一致
    resp = await client.post(
        f"{BASE}/api/v1/orders/batch-status",
        json={"order_ids": [d["order_id"]], "target_status": "recruiting"},
        headers=_tenant_headers(d),
    )
    assert resp.status_code == 409, f"应被资金守卫拦截: {resp.status_code}"


async def test_super_admin_unblacklist_with_tenant_id(client, db):
    d = await _setup(db)
    app_a = await _apply(client, d, "a")
    resp = await client.post(
        f"{BASE}/api/v1/tenants/teachers/{d['teacher_a']}/blacklist",
        json={"reason": "测试拉黑"},
        headers=_tenant_headers(d),
    )
    assert resp.status_code == 200, resp.text

    # 缺 tenant_id：422 明确提示，而不是恒 404
    resp = await client.delete(
        f"{BASE}/api/v1/tenants/teachers/{d['teacher_a']}/blacklist",
        headers=auth_header(boss_token()),
    )
    assert resp.status_code == 422, f"缺 tenant_id 应 422: {resp.status_code}"

    # 显式 tenant_id：超管可移出
    resp = await client.delete(
        f"{BASE}/api/v1/tenants/teachers/{d['teacher_a']}/blacklist",
        params={"tenant_id": d["tenant_id"]},
        headers=auth_header(boss_token()),
    )
    assert resp.status_code == 200, resp.text
    record = (await db.execute(
        select(TenantTeacherBlacklist).where(
            TenantTeacherBlacklist.tenant_id == d["tenant_id"],
            TenantTeacherBlacklist.teacher_id == d["teacher_a"],
        )
    )).scalar_one_or_none()
    assert record is None

    # 移出后教员可重新投递
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        json={"order_id": d["order_id"], "resume_id": d["resume_a"]},
        headers=auth_header(teacher_token(d["teacher_a"])),
    )
    assert resp.status_code == 200, resp.text


async def test_update_order_zero_price_resets_fees(client, db):
    d = await _setup(db)
    resp = await client.patch(
        f"{BASE}/api/v1/orders/{d['order_id']}",
        json={"base_price": 0},
        headers=_tenant_headers(d),
    )
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert float(detail["calculated_info_fee"]) == 0.0
    assert float(detail["deposit_amount"]) == 0.0
    assert float(detail["balance_amount"]) == 0.0
    assert detail["needs_manual_price"] is True


async def test_like_wildcard_escaped(client, db):
    d = await _setup(db)
    headers = _tenant_headers(d)

    # 正常关键字命中
    resp = await client.get(
        f"{BASE}/api/v1/orders/", params={"q": "P3-001"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 1

    # 通配符按字面匹配：% 不再匹配任意串（此前 "%%%" 等价全表扫描）
    resp = await client.get(
        f"{BASE}/api/v1/orders/", params={"q": "%%"}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 0


async def test_completed_order_cannot_transit(client, db):
    d = await _setup(db)
    app_a = await _apply(client, d, "a")
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/shortlist", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_a}/confirm-deposit", headers=_tenant_headers(d)
    )
    assert resp.status_code == 200, resp.text
    for action in ("start-trial", "confirm-balance", "complete"):
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_a}/{action}", headers=_tenant_headers(d)
        )
        assert resp.status_code == 200, resp.text

    # completed 仍是终态：transit 重开被状态机拒绝（400），成交单只读
    resp = await client.post(
        f"{BASE}/api/v1/orders/{d['order_id']}/transit",
        json={"target_status": "recruiting"},
        headers=_tenant_headers(d),
    )
    assert resp.status_code == 400, f"completed 订单不可回退: {resp.status_code}"
