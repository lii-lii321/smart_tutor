"""
路由形状回归测试（覆盖率补强）：notifications / resumes / public 橱窗。

此前这三个路由组基本无测试覆盖（覆盖率 40%~58%），本文件锁定：
- 通知：教员/租户两侧的列表形状、未读数、一键已读、租户隔离；
- 简历：首份自动默认、默认互斥切换、删除默认后顺位继承；
- 公开橱窗：脱敏字段面、停用中介 404、30s 缓存命中与失效（fakeredis）。

运行方式：
    pytest tests/test_router_shapes.py
"""
import datetime

from conftest import (
    auth_header,
    make_order,
    make_teacher,
    make_tenant,
    teacher_token,
    tenant_token,
)
from sqlalchemy import select

from models.domain import Notification, Order, OrderStatus

BASE = "http://test"


async def _seed_teacher_notification(db, teacher_id: int, title: str, *, read: bool = False, order_id: int | None = None) -> Notification:
    note = Notification(
        teacher_id=teacher_id,
        title=title,
        content=f"{title}的内容",
        order_id=order_id,
        read_at=datetime.datetime.utcnow() if read else None,
    )
    db.add(note)
    await db.flush()
    return note


async def _seed_tenant_notification(db, tenant_id: int, title: str, *, read: bool = False) -> Notification:
    note = Notification(
        tenant_id=tenant_id,
        title=title,
        content=f"{title}的内容",
        read_at=datetime.datetime.utcnow() if read else None,
    )
    db.add(note)
    await db.flush()
    return note


# ── 教员通知 ──


async def test_teacher_notifications_shape_and_unread(client, db):
    tenant = await make_tenant(db, "rsh001a")
    teacher = await make_teacher(db, "rsh_teacher_a")
    order = await make_order(db, tenant.id, "RSH-A01")
    await _seed_teacher_notification(db, teacher.id, "进入候选名单", order_id=order.id)
    await _seed_teacher_notification(db, teacher.id, "定金已确认", read=True)
    await db.commit()
    headers = auth_header(teacher_token(teacher.id))

    resp = await client.get(f"{BASE}/api/v1/notifications/mine", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["unread_count"] == 1
    assert len(body["items"]) == 2
    item = body["items"][0]
    for key in ("id", "title", "content", "is_read", "created_at"):
        assert key in item
    # 未读的排前面（created_at 同刻时按 id 降序，种子顺序后者在前）
    assert body["items"][0]["title"] == "定金已确认"

    resp = await client.post(f"{BASE}/api/v1/notifications/read-all", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["marked"] == 1

    resp = await client.get(f"{BASE}/api/v1/notifications/mine", headers=headers)
    assert resp.json()["unread_count"] == 0


async def test_teacher_notification_limit_clamped(client, db):
    teacher = await make_teacher(db, "rsh_teacher_b")
    for i in range(3):
        await _seed_teacher_notification(db, teacher.id, f"通知{i}")
    await db.commit()

    resp = await client.get(
        f"{BASE}/api/v1/notifications/mine",
        params={"limit": 2},
        headers=auth_header(teacher_token(teacher.id)),
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["items"]) == 2


# ── 租户通知 ──


async def test_tenant_notifications_scoped_and_read_all(client, db):
    tenant_a = await make_tenant(db, "rsh002a")
    tenant_b = await make_tenant(db, "rsh002b")
    await _seed_tenant_notification(db, tenant_a.id, "收到新投递")
    await _seed_tenant_notification(db, tenant_b.id, "别家的通知")
    await db.commit()
    headers = auth_header(tenant_token(tenant_a.id))

    resp = await client.get(f"{BASE}/api/v1/notifications/tenant-mine", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["unread_count"] == 1
    assert [i["title"] for i in body["items"]] == ["收到新投递"]

    resp = await client.post(f"{BASE}/api/v1/notifications/tenant-read-all", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["marked"] == 1

    # 中介 B 的通知不受中介 A 一键已读影响
    resp = await client.get(
        f"{BASE}/api/v1/notifications/tenant-mine",
        headers=auth_header(tenant_token(tenant_b.id)),
    )
    assert resp.json()["unread_count"] == 1


# ── 简历 ──


def _resume_payload(title: str, **overrides) -> dict:
    payload = {
        "title": title,
        "teaching_subjects": "数学",
        "teaching_grades": "初一-初三",
        "experience": "两年经验",
    }
    payload.update(overrides)
    return payload


async def test_resume_first_auto_default_and_switch(client, db):
    teacher = await make_teacher(db, "rsh_teacher_c")
    await db.commit()
    headers = auth_header(teacher_token(teacher.id))

    # 首份简历自动成为默认
    resp = await client.post(f"{BASE}/api/v1/teacher/resumes/", json=_resume_payload("简历一"), headers=headers)
    assert resp.status_code == 200, resp.text
    first = resp.json()
    assert first["is_default"] is True

    # 第二份不指定默认：互斥保持
    resp = await client.post(f"{BASE}/api/v1/teacher/resumes/", json=_resume_payload("简历二"), headers=headers)
    second = resp.json()
    assert second["is_default"] is False

    # 设第二份为默认：第一份被互斥取消
    resp = await client.post(f"{BASE}/api/v1/teacher/resumes/{second['id']}/default", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_default"] is True

    listing = (await client.get(f"{BASE}/api/v1/teacher/resumes/", headers=headers)).json()
    defaults = [r for r in listing if r["is_default"]]
    assert len(defaults) == 1 and defaults[0]["id"] == second["id"]


async def test_resume_patch_and_delete_default_inherits(client, db):
    teacher = await make_teacher(db, "rsh_teacher_d")
    await db.commit()
    headers = auth_header(teacher_token(teacher.id))

    resp = await client.post(f"{BASE}/api/v1/teacher/resumes/", json=_resume_payload("主简历"), headers=headers)
    first = resp.json()
    resp = await client.post(
        f"{BASE}/api/v1/teacher/resumes/",
        json=_resume_payload("备简历", expected_rate="200/次"),
        headers=headers,
    )
    second = resp.json()

    # PATCH 更新字段
    resp = await client.patch(
        f"{BASE}/api/v1/teacher/resumes/{second['id']}",
        json={"strengths": "擅长错题复盘"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["strengths"] == "擅长错题复盘"

    # 删除默认简历：最新剩余简历自动继承默认
    resp = await client.delete(f"{BASE}/api/v1/teacher/resumes/{first['id']}", headers=headers)
    assert resp.status_code == 200, resp.text

    listing = (await client.get(f"{BASE}/api/v1/teacher/resumes/", headers=headers)).json()
    assert len(listing) == 1
    assert listing[0]["id"] == second["id"]
    assert listing[0]["is_default"] is True


# ── 公开橱窗 ──


async def test_public_board_masked_and_404(client, db, fake_redis):
    tenant = await make_tenant(db, "rsh003z")
    order = await make_order(db, tenant.id, "RSH-B01")
    await db.commit()

    # 不存在的邀请码 / 停用中介 → 404 同文案
    resp = await client.get(f"{BASE}/api/v1/public/agent/nope/board")
    assert resp.status_code == 404

    resp = await client.get(f"{BASE}/api/v1/public/agent/{tenant.invite_code}/board")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["invite_code"] == tenant.invite_code
    assert len(body["orders"]) == 1
    brief = body["orders"][0]
    # 公开视图不带内部字段（raw_id/status/家长信息不在响应面）
    assert "raw_id" not in brief
    assert "status" not in brief
    assert brief["grade_subject"] == order.grade_subject

    # 归档订单立即从橱窗消失（写路径已失效缓存）
    order.status = OrderStatus.archived
    await db.commit()
    from services.order_maintenance import invalidate_board_cache
    await invalidate_board_cache(tenant.id)

    resp = await client.get(f"{BASE}/api/v1/public/agent/{tenant.invite_code}/board")
    assert resp.status_code == 200, resp.text
    assert resp.json()["orders"] == []


async def test_public_board_cache_hit(client, db, fake_redis):
    """第一次请求写缓存；随后 DB 直改不失效缓存时，30s 内仍返回旧集合。"""
    from services.order_maintenance import board_cache_key

    tenant = await make_tenant(db, "rsh004z")
    await make_order(db, tenant.id, "RSH-C01")
    await db.commit()
    url = f"{BASE}/api/v1/public/agent/{tenant.invite_code}/board"

    resp = await client.get(url)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["orders"]) == 1
    assert await fake_redis.exists(board_cache_key(tenant.id))

    # 绕过写路径直接改库：缓存未失效，橱窗仍显示 1 单
    order = (await db.execute(
        select(Order).where(Order.raw_id == "RSH-C01")
    )).scalar_one()
    order.status = OrderStatus.archived
    await db.commit()

    resp = await client.get(url)
    assert len(resp.json()["orders"]) == 1, "30s 缓存窗口内应返回旧数据"

    # 缓存清空后回落真实集合
    await fake_redis.delete(board_cache_key(tenant.id))
    resp = await client.get(url)
    assert resp.json()["orders"] == []
