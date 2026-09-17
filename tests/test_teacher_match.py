"""
订单找教员（一期）回归：

- 推荐排序：科目匹配的教员排前；封禁/拉黑/已投递的教员被排除；不含联系方式；
- 邀约：写教员通知；72h 内重复邀约 409；已投递 409；拉黑 400；非招聘中 400；
- 非本租户订单不可见（租户隔离）。

运行方式：
    pytest tests/test_teacher_match.py
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

from models.domain import Notification, TeacherResume


async def _setup(db, invite_code: str):
    tenant = await make_tenant(db, invite_code)
    order = await make_order(db, tenant.id, "TM-001")
    # 三名教员:数学匹配 / 英语不匹配 / 已投递
    t_math = await make_teacher(db, "tm_math", name="数学王")
    t_eng = await make_teacher(db, "tm_eng", name="英语李")
    t_applied = await make_teacher(db, "tm_applied", name="已投赵")
    for t in (t_math, t_eng, t_applied):
        db.add(TeacherResume(
            teacher_id=t.id,
            title=f"{t.name}简历",
            teaching_subjects="数学" if t is t_math else "英语",
            teaching_grades="初一-高三",
            experience="三年家教经验",
            is_default=True,
        ))
    await db.flush()
    from models.domain import Application
    db.add(Application(order_id=order.id, teacher_id=t_applied.id, tenant_id=tenant.id))
    await db.commit()
    return tenant, order, t_math, t_eng, t_applied


async def test_recommended_teachers_rank_and_exclusions(client, db):
    tenant, order, t_math, t_eng, t_applied = await _setup(db, "tmrk001")

    r = await client.get(
        f"{BASE}/api/v1/orders/{order.id}/recommended-teachers",
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert r.status_code == 200, r.text
    items = r.json()
    ids = [item["teacher_id"] for item in items]

    assert t_applied.id not in ids, "已投递教员不参与推荐"
    assert ids and ids[0] == t_math.id, "科目匹配的教员应排第一"
    top = items[0]
    assert top["subject_matched"] is True
    assert not any(k in top for k in ("phone", "wechat_id")), "推荐列表不得暴露联系方式"


async def test_recommended_excludes_blacklisted(client, db):
    tenant, order, t_math, t_eng, t_applied = await _setup(db, "tmrk002")
    from models.domain import TenantTeacherBlacklist
    db.add(TenantTeacherBlacklist(tenant_id=tenant.id, teacher_id=t_math.id, reason="拉黑"))
    await db.commit()

    r = await client.get(
        f"{BASE}/api/v1/orders/{order.id}/recommended-teachers",
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert r.status_code == 200, r.text
    ids = [item["teacher_id"] for item in r.json()]
    assert t_math.id not in ids, "被拉黑教员不参与推荐"


async def test_invite_creates_notification_once(client, db):
    tenant, order, t_math, t_eng, t_applied = await _setup(db, "tmin001")
    headers = auth_header(tenant_token(tenant.id))

    r = await client.post(
        f"{BASE}/api/v1/orders/{order.id}/invite-teacher",
        json={"teacher_id": t_math.id},
        headers=headers,
    )
    assert r.status_code == 200, r.text

    notif = (await db.execute(
        select(Notification).where(
            Notification.teacher_id == t_math.id,
            Notification.order_id == order.id,
            Notification.title == "订单邀约",
        )
    )).scalars().all()
    assert len(notif) == 1
    assert notif[0].deleted_at is None

    # 72h 内重复邀约 → 409
    r2 = await client.post(
        f"{BASE}/api/v1/orders/{order.id}/invite-teacher",
        json={"teacher_id": t_math.id},
        headers=headers,
    )
    assert r2.status_code == 409, r2.text
    assert "邀约" in r2.json()["detail"]

    # 教员侧能看到邀约通知
    r3 = await client.get(
        f"{BASE}/api/v1/notifications/mine",
        headers=auth_header(teacher_token(t_math.id)),
    )
    assert any(n["title"] == "订单邀约" for n in r3.json()["items"])


async def test_invite_rejects_applied_and_blacklisted(client, db):
    tenant, order, t_math, t_eng, t_applied = await _setup(db, "tmin002")
    headers = auth_header(tenant_token(tenant.id))

    r = await client.post(
        f"{BASE}/api/v1/orders/{order.id}/invite-teacher",
        json={"teacher_id": t_applied.id},
        headers=headers,
    )
    assert r.status_code == 409, "已投递教员邀约应 409"

    from models.domain import TenantTeacherBlacklist
    db.add(TenantTeacherBlacklist(tenant_id=tenant.id, teacher_id=t_eng.id, reason="x"))
    await db.commit()
    r = await client.post(
        f"{BASE}/api/v1/orders/{order.id}/invite-teacher",
        json={"teacher_id": t_eng.id},
        headers=headers,
    )
    assert r.status_code == 400, "拉黑教员邀约应 400"


async def test_invite_requires_recruiting_order(client, db):
    tenant = await make_tenant(db, "tmin003")
    teacher = await make_teacher(db, "tmin_t")
    order = await make_order(db, tenant.id, "TMIN-001")
    from models.domain import OrderStatus
    order.status = OrderStatus.archived
    await db.commit()

    r = await client.post(
        f"{BASE}/api/v1/orders/{order.id}/invite-teacher",
        json={"teacher_id": teacher.id},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert r.status_code == 400, r.text


async def test_match_is_tenant_scoped(client, db):
    tenant = await make_tenant(db, "tmin004")
    order = await make_order(db, tenant.id, "TMIN-002")
    other = await make_tenant(db, "tmin005")
    await db.commit()

    r = await client.get(
        f"{BASE}/api/v1/orders/{order.id}/recommended-teachers",
        headers=auth_header(tenant_token(other.id)),
    )
    assert r.status_code == 404, "他租户订单按不存在处理"
