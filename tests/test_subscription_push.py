"""
教员订阅推送测试：偏好匹配规则、硬门槛排除、幂等与路由契约。
无 LLM/Embedding 依赖，纯 DB 行为。运行：pytest tests/test_subscription_push.py
"""

from conftest import (
    BASE,
    auth_header,
    make_order,
    make_teacher,
    make_tenant,
    teacher_token,
    tenant_token,
)
from sqlalchemy import select

from models.domain import (
    Application,
    Notification,
    TeacherSubscription,
    TenantTeacherBlacklist,
)
from services.subscription_push import deliver_for_order


async def _set_subscription(db, teacher_id: int, **fields) -> None:
    sub = await db.get(TeacherSubscription, teacher_id)
    if sub is None:
        sub = TeacherSubscription(teacher_id=teacher_id)
        db.add(sub)
    defaults = {"enabled": True, "subjects": None, "grades": None, "min_base_price": None}
    defaults.update(fields)
    for key, value in defaults.items():
        setattr(sub, key, value)
    await db.flush()


async def _notify_teacher_ids(db, order_id: int) -> set[int]:
    rows = (
        await db.scalars(
            select(Notification.teacher_id).where(
                Notification.order_id == order_id,
                Notification.title == "订阅新单",
            )
        )
    ).all()
    return set(rows)


# ── 匹配规则 ──


async def test_match_subject_grade_price(db):
    tenant = await make_tenant(db, "sub_match")
    teacher = await make_teacher(db, "sub_t1")
    order = await make_order(db, tenant.id, "M1")  # 初三数学 200/次 周频2

    async def _clear_notifications() -> None:
        # 匹配测试与幂等无关：清掉上一场景的站内信，避免查重拦截本场景断言
        for n in (
            await db.scalars(
                select(Notification).where(
                    Notification.teacher_id == teacher.id, Notification.order_id == order.id
                )
            )
        ).all():
            await db.delete(n)
        await db.flush()

    await _set_subscription(db, teacher.id, subjects="数学", grades="初中", min_base_price=150)
    assert await deliver_for_order(db, order) == 1

    # 科目不匹配
    await _set_subscription(db, teacher.id, subjects="英语")
    await _clear_notifications()
    assert await deliver_for_order(db, order) == 0
    # 学段不匹配（订单初三 vs 订阅高中）
    await _set_subscription(db, teacher.id, subjects="数学", grades="高中")
    await _clear_notifications()
    assert await deliver_for_order(db, order) == 0
    # 课酬低于下限（订单 200 < 下限 300）
    await _set_subscription(db, teacher.id, subjects="数学", min_base_price=300)
    await _clear_notifications()
    assert await deliver_for_order(db, order) == 0
    # 留空 = 不限
    await _set_subscription(db, teacher.id)
    await _clear_notifications()
    assert await deliver_for_order(db, order) == 1


async def test_push_excludes_banned_blacklisted_and_applied(db):
    tenant = await make_tenant(db, "sub_gate")
    banned = await make_teacher(db, "sub_ban")
    banned.is_banned = True
    black = await make_teacher(db, "sub_black")
    applied = await make_teacher(db, "sub_applied")
    normal = await make_teacher(db, "sub_ok")
    order = await make_order(db, tenant.id, "G1")
    db.add(Application(order_id=order.id, teacher_id=applied.id, tenant_id=tenant.id))
    db.add(TeacherSubscription(teacher_id=banned.id, enabled=True))
    db.add(TeacherSubscription(teacher_id=black.id, enabled=True))
    db.add(TeacherSubscription(teacher_id=applied.id, enabled=True))
    db.add(TeacherSubscription(teacher_id=normal.id, enabled=True))
    db.add(TenantTeacherBlacklist(tenant_id=tenant.id, teacher_id=black.id, reason="测试"))
    await db.flush()

    notified = await deliver_for_order(db, order)
    ids = await _notify_teacher_ids(db, order.id)
    assert ids == {normal.id}
    assert notified == 1


async def test_push_disabled_subscription_excluded(db):
    tenant = await make_tenant(db, "sub_off")
    teacher = await make_teacher(db, "sub_off1")
    order = await make_order(db, tenant.id, "OFF1")
    db.add(TeacherSubscription(teacher_id=teacher.id, enabled=False))
    await db.flush()

    assert await deliver_for_order(db, order) == 0


async def test_push_non_recruiting_order_skipped(db):
    from models.domain import OrderStatus

    tenant = await make_tenant(db, "sub_arch")
    teacher = await make_teacher(db, "sub_arch1")
    order = await make_order(db, tenant.id, "ARCH")
    order.status = OrderStatus.archived
    db.add(TeacherSubscription(teacher_id=teacher.id, enabled=True))
    await db.flush()

    assert await deliver_for_order(db, order) == 0


async def test_push_is_idempotent_per_order(db):
    tenant = await make_tenant(db, "sub_idem")
    teacher = await make_teacher(db, "sub_i1")
    order = await make_order(db, tenant.id, "I1")
    db.add(TeacherSubscription(teacher_id=teacher.id, enabled=True))
    await db.flush()

    assert await deliver_for_order(db, order) == 1
    assert await deliver_for_order(db, order) == 0  # 同单同教员不重复推
    assert len(await _notify_teacher_ids(db, order.id)) == 1


async def test_push_cap_limits_notifications(db, monkeypatch):
    from services import subscription_push

    monkeypatch.setattr(subscription_push, "_MAX_NOTIFY_PER_ORDER", 3)
    tenant = await make_tenant(db, "sub_cap")
    order = await make_order(db, tenant.id, "CAP")
    for i in range(6):
        teacher = await make_teacher(db, f"sub_cap{i}")
        db.add(TeacherSubscription(teacher_id=teacher.id, enabled=True))
    await db.flush()

    assert await deliver_for_order(db, order) == 3


# ── 路由契约 ──


async def test_subscription_route_roundtrip_and_teacher_only(client, db):
    from models.schemas import TeacherSubscriptionRequest

    tenant = await make_tenant(db, "sub_rt")
    await db.commit()

    # 仅教员可访问：中介 403
    resp = await client.get(
        f"{BASE}/api/v1/subscriptions/mine", headers=auth_header(tenant_token(tenant.id))
    )
    assert resp.status_code == 403

    # 教员 PUT 保存（含可归一科目名）→ GET 回读
    teacher = await make_teacher(db, "sub_rt1")
    await db.commit()
    headers = auth_header(teacher_token(teacher.id))
    resp = await client.put(
        f"{BASE}/api/v1/subscriptions/mine",
        json=TeacherSubscriptionRequest(
            enabled=True, subjects=["奥数", "英语"], grades=["初中"], min_base_price=150
        ).model_dump(),
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["subjects"] == ["数学", "英语"]  # 奥数 → 规范名数学
    assert body["grades"] == ["初中"]
    assert body["min_base_price"] == 150

    resp = await client.get(f"{BASE}/api/v1/subscriptions/mine", headers=headers)
    assert resp.json()["enabled"] is True
