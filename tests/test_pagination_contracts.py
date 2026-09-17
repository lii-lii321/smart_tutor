"""
分页契约回归（数据量增长防线）：

- /applications/mine 不再支持全量：缺省与 page_size<=0 都按默认页长截断；
  order_id 参数按单查询（订单详情页免拉全量列表）；
- /applications/order/{id} 分页返回，热门订单投递破百不再无上限；
- /applications/reviews/mine 分页 + X-Total-Count 精确总数；
- 推荐候选只扫最近 _RECOMMEND_SCAN_LIMIT 个活跃订单（正则评分有界）。

运行方式：
    pytest tests/test_pagination_contracts.py
"""
import datetime

from conftest import (
    BASE,
    auth_header,
    make_order,
    make_teacher,
    make_tenant,
    teacher_token,
    tenant_token,
)

from models.domain import Application, OrderReview, TeacherResume


async def _make_order_with_created_at(db, tenant_id: int, raw_id: str, created_at: datetime.datetime):
    order = await make_order(db, tenant_id, raw_id)
    order.created_at = created_at
    await db.flush()
    return order


async def test_mine_default_caps_and_zero_means_default(client, db):
    """25 条投递：缺省返回 20 条；page_size=0 不再是全量语义，同样按默认页长截断。"""
    tenant = await make_tenant(db, "pgcnt001")
    teacher = await make_teacher(db, "pg_teacher_1")
    for i in range(25):
        order = await make_order(db, tenant.id, f"PGC-{i:03d}")
        db.add(Application(order_id=order.id, teacher_id=teacher.id, tenant_id=tenant.id))
    await db.commit()

    headers = auth_header(teacher_token(teacher.id))

    r = await client.get(f"{BASE}/api/v1/applications/mine", headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 20, "缺省应按默认页长 20 截断，而非全量"

    r0 = await client.get(f"{BASE}/api/v1/applications/mine", params={"page_size": 0}, headers=headers)
    assert r0.status_code == 200
    assert len(r0.json()) == 20, "page_size=0 应按默认页长处理，不得回退全量"

    r2 = await client.get(
        f"{BASE}/api/v1/applications/mine", params={"page": 2, "page_size": 20}, headers=headers
    )
    assert r2.status_code == 200
    assert len(r2.json()) == 5


async def test_mine_order_id_filter(client, db):
    """order_id 过滤只返回自己在该订单的投递，且不受其他教员投递干扰。"""
    tenant = await make_tenant(db, "pgoid001")
    teacher_a = await make_teacher(db, "pg_teacher_a", name="教员A")
    teacher_b = await make_teacher(db, "pg_teacher_b", name="教员B")
    target = await make_order(db, tenant.id, "PGO-001")
    other = await make_order(db, tenant.id, "PGO-002")
    db.add_all([
        Application(order_id=target.id, teacher_id=teacher_a.id, tenant_id=tenant.id),
        Application(order_id=target.id, teacher_id=teacher_b.id, tenant_id=tenant.id),
        Application(order_id=other.id, teacher_id=teacher_a.id, tenant_id=tenant.id),
    ])
    await db.commit()

    r = await client.get(
        f"{BASE}/api/v1/applications/mine",
        params={"order_id": target.id},
        headers=auth_header(teacher_token(teacher_a.id)),
    )
    assert r.status_code == 200, r.text
    items = r.json()
    assert len(items) == 1, "应只返回自己在该订单的投递"
    assert items[0]["order_id"] == target.id
    assert items[0]["teacher"]["id"] == teacher_a.id


async def test_order_applications_pagination(client, db):
    """/applications/order/{id} 分页：按 applied_at desc, id desc 稳定排序。"""
    tenant = await make_tenant(db, "pgord001")
    order = await make_order(db, tenant.id, "PGO2-001")
    base = datetime.datetime.utcnow()
    for i in range(3):
        teacher = await make_teacher(db, f"pg_ord_t{i}")
        app = Application(order_id=order.id, teacher_id=teacher.id, tenant_id=tenant.id)
        app.applied_at = base - datetime.timedelta(minutes=i)
        db.add(app)
        await db.flush()
    await db.commit()

    headers = auth_header(tenant_token(tenant.id))
    r1 = await client.get(
        f"{BASE}/api/v1/applications/order/{order.id}",
        params={"page": 1, "page_size": 2},
        headers=headers,
    )
    assert r1.status_code == 200, r1.text
    assert len(r1.json()) == 2

    r2 = await client.get(
        f"{BASE}/api/v1/applications/order/{order.id}",
        params={"page": 2, "page_size": 2},
        headers=headers,
    )
    assert r2.status_code == 200
    assert len(r2.json()) == 1
    # 跨页不重不漏：合并后 id 唯一
    ids = [a["id"] for a in r1.json() + r2.json()]
    assert len(set(ids)) == 3


async def test_my_reviews_pagination_and_total_header(client, db):
    """reviews/mine：分页生效；X-Total-Count 返回不受分页影响的精确总数。"""
    tenant = await make_tenant(db, "pgrev001")
    teacher = await make_teacher(db, "pg_teacher_rev")
    for i in range(2):
        order = await make_order(db, tenant.id, f"PGR-{i:03d}")
        app = Application(order_id=order.id, teacher_id=teacher.id, tenant_id=tenant.id)
        db.add(app)
        await db.flush()
        db.add(OrderReview(
            order_id=order.id, application_id=app.id,
            tenant_id=tenant.id, teacher_id=teacher.id, rating=5,
        ))
    await db.commit()

    headers = auth_header(teacher_token(teacher.id))
    r = await client.get(
        f"{BASE}/api/v1/applications/reviews/mine",
        params={"page": 1, "page_size": 1},
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1
    assert r.headers["x-total-count"] == "2", "总数头不受分页影响"

    r_all = await client.get(f"{BASE}/api/v1/applications/reviews/mine", headers=headers)
    assert r_all.status_code == 200
    assert len(r_all.json()) == 2, "两条数据小于默认页长时应全部返回"


async def test_recommendation_scan_window(client, db):
    """活跃订单超过扫描窗口时，推荐只从最近 _RECOMMEND_SCAN_LIMIT 个订单中产出。"""
    from services.recommendation import _RECOMMEND_SCAN_LIMIT, build_teacher_recommendations

    tenant = await make_tenant(db, "pgrec001")
    teacher = await make_teacher(db, "pg_teacher_rec", name="推荐教员")
    db.add(TeacherResume(
        teacher_id=teacher.id, title="数学家教",
        teaching_subjects="数学", teaching_grades="初一-初三",
        experience="两年经验",
    ))
    await db.flush()

    extra = _RECOMMEND_SCAN_LIMIT + 5
    now = datetime.datetime.utcnow()
    oldest_ids: list[int] = []
    newest_ids: list[int] = []
    for i in range(extra):
        order = await _make_order_with_created_at(db, tenant.id, f"PGRX-{i:04d}", now - datetime.timedelta(minutes=i))
        if i >= _RECOMMEND_SCAN_LIMIT:
            oldest_ids.append(order.id)  # 窗口之外（最老的一批）
        else:
            newest_ids.append(order.id)
    await db.commit()

    items = await build_teacher_recommendations(db, teacher.id, tenant.id, limit=50)
    assert items, "科目匹配时推荐不应为空"
    returned_ids = {item.id for item in items}
    assert returned_ids.isdisjoint(set(oldest_ids)), "窗口外的老订单不应参与推荐"
    assert returned_ids.issubset(set(newest_ids)), "推荐必须来自窗口内的订单"
    assert len(items) <= 50


async def test_recommendation_scan_tenant_scoped_applications(client, db):
    """教员在别的租户的历史投递不参与当前租户推荐的已投递排除，但同租户投递仍生效。"""
    from services.recommendation import build_teacher_recommendations

    tenant_a = await make_tenant(db, "pgrecA01")
    tenant_b = await make_tenant(db, "pgrecB02")
    teacher = await make_teacher(db, "pg_teacher_multi")
    db.add(TeacherResume(
        teacher_id=teacher.id, title="数学家教",
        teaching_subjects="数学", teaching_grades="初一-初三",
        experience="两年经验",
    ))
    await db.flush()
    order_a = await make_order(db, tenant_a.id, "PGMA-001")
    order_b = await make_order(db, tenant_b.id, "PGMB-001")
    db.add(Application(order_id=order_b.id, teacher_id=teacher.id, tenant_id=tenant_b.id))
    await db.commit()

    items = await build_teacher_recommendations(db, teacher.id, tenant_a.id, limit=50)
    assert any(item.id == order_a.id for item in items), "租户 A 的未投递订单应出现在推荐中"

    items_b = await build_teacher_recommendations(db, teacher.id, tenant_b.id, limit=50)
    assert not any(item.id == order_b.id for item in items_b), "同租户已投递订单应被排除出推荐"


async def test_unread_count_endpoints(client, db):
    """角标轮询轻量端点：只回未读数不拉列表；C 端与 B 端未读互不串扰。"""
    from models.domain import Notification

    tenant = await make_tenant(db, "pgunr001")
    teacher = await make_teacher(db, "pg_teacher_unr")
    db.add_all([
        Notification(teacher_id=teacher.id, title="教员通知A"),
        Notification(teacher_id=teacher.id, title="教员通知B", read_at=datetime.datetime.utcnow()),
        Notification(tenant_id=tenant.id, title="租户通知A"),
        Notification(tenant_id=tenant.id, title="租户通知B"),
    ])
    await db.commit()

    r = await client.get(
        f"{BASE}/api/v1/notifications/mine/unread-count",
        headers=auth_header(teacher_token(teacher.id)),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"unread_count": 1}, "已读通知不计入未读数"

    r = await client.get(
        f"{BASE}/api/v1/notifications/tenant-unread-count",
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"unread_count": 2}


async def test_application_summary_with_data(client, db):
    """回归：/applications/summary 有数据时必须 200。
    order_counts 以订单 ID 为键，响应模型要求字符串键——数字键会触发
    ResponseValidationError 500，导致中介端统计/角标全挂（曾因前端 catch 静默掩盖）。"""
    tenant = await make_tenant(db, "pgsum001")
    teacher = await make_teacher(db, "pg_teacher_sum")
    teacher2 = await make_teacher(db, "pg_teacher_sum2")
    order_a = await make_order(db, tenant.id, "PGS-A")
    order_b = await make_order(db, tenant.id, "PGS-B")
    db.add_all([
        Application(order_id=order_a.id, teacher_id=teacher.id, tenant_id=tenant.id),
        Application(order_id=order_a.id, teacher_id=teacher2.id, tenant_id=tenant.id),
        Application(order_id=order_b.id, teacher_id=teacher.id, tenant_id=tenant.id),
    ])
    await db.commit()

    r = await client.get(
        f"{BASE}/api/v1/applications/summary",
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_applications"] == 3
    # JSON 序列化后键必为字符串
    assert body["order_counts"] == {str(order_a.id): 2, str(order_b.id): 1}


async def test_token_sliding_reissue(client, db):
    """滑动续期：签发超 24h 的有效 token 经 X-Reissued-Token 换发新 token；
    新 token 立即可用且不二次换发；新鲜 token 不换发。"""
    import time as _time

    import jwt as _jwt

    from config import settings

    teacher = await make_teacher(db, "pg_teacher_reissue")
    await db.commit()

    now = int(_time.time())
    old_token = _jwt.encode(
        {
            "sub": f"teacher_{teacher.id}",
            "role": "teacher",
            "tid": None,
            "iat": now - 25 * 3600,
            "exp": now + 3600,
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    r = await client.get(
        f"{BASE}/api/v1/applications/mine", headers=auth_header(old_token)
    )
    assert r.status_code == 200, r.text
    new_token = r.headers.get("x-reissued-token")
    assert new_token, "超 24h 的活跃 token 应被换发"

    r2 = await client.get(
        f"{BASE}/api/v1/applications/mine", headers=auth_header(new_token)
    )
    assert r2.status_code == 200, r2.text
    assert "x-reissued-token" not in r2.headers, "刚换发的新 token 不应再次换发"

    r3 = await client.get(
        f"{BASE}/api/v1/applications/mine", headers=auth_header(teacher_token(teacher.id))
    )
    assert r3.status_code == 200
    assert "x-reissued-token" not in r3.headers, "新鲜 token 不换发"


async def test_notification_delete_scoped_and_dedup_safe(client, db):
    """通知批量/全选删除（用户主动，无自动清理）：
    - 只能删自己的；跨用户 id 不生效；
    - 软删行从列表消失，但调度器临期提醒去重锚点保留——删掉的提醒不复活。"""
    from models.domain import Notification

    tenant = await make_tenant(db, "pgdel001")
    teacher_a = await make_teacher(db, "pg_del_a", name="删A")
    teacher_b = await make_teacher(db, "pg_del_b", name="删B")
    n_a1 = Notification(teacher_id=teacher_a.id, title="A的提醒1")
    n_a2 = Notification(teacher_id=teacher_a.id, title="A的提醒2")
    n_b = Notification(teacher_id=teacher_b.id, title="B的提醒")
    n_tenant = Notification(tenant_id=tenant.id, title="租户通知")
    db.add_all([n_a1, n_a2, n_b, n_tenant])
    await db.commit()

    headers_a = auth_header(teacher_token(teacher_a.id))
    headers_b = auth_header(teacher_token(teacher_b.id))
    headers_tenant = auth_header(tenant_token(tenant.id))

    # 教员 A 删除自己的一条
    r = await client.post(
        f"{BASE}/api/v1/notifications/delete",
        json={"ids": [n_a1.id]},
        headers=headers_a,
    )
    assert r.status_code == 200, r.text
    assert r.json()["marked"] == 1

    # 教员 A 试图删除 B 的通知：归属不符不生效
    r = await client.post(
        f"{BASE}/api/v1/notifications/delete",
        json={"ids": [n_b.id]},
        headers=headers_a,
    )
    assert r.status_code == 200
    assert r.json()["marked"] == 0
    r_b = await client.get(f"{BASE}/api/v1/notifications/mine", headers=headers_b)
    assert any(n["title"] == "B的提醒" for n in r_b.json()["items"]), "B 的通知不受他人删除影响"

    # A 的列表只剩一条
    r_a = await client.get(f"{BASE}/api/v1/notifications/mine", headers=headers_a)
    titles = [n["title"] for n in r_a.json()["items"]]
    assert titles == ["A的提醒2"]

    # B 端：删除租户通知 + 全清
    r = await client.post(
        f"{BASE}/api/v1/notifications/tenant-delete",
        json={"ids": [n_tenant.id]},
        headers=headers_tenant,
    )
    assert r.status_code == 200 and r.json()["marked"] == 1
    r = await client.post(f"{BASE}/api/v1/notifications/tenant-delete-all", headers=headers_tenant)
    assert r.status_code == 200

    # 超长列表拒绝
    r = await client.post(
        f"{BASE}/api/v1/notifications/delete",
        json={"ids": list(range(1, 202))},
        headers=headers_a,
    )
    assert r.status_code == 422


async def test_deleted_expiring_reminder_does_not_revive(client, db):
    """软删关键不变量：中介删掉"订单即将过期"通知后，调度再次运行不重建该提醒
    （去重按通知行存在性判断，硬删会让提醒每 5 分钟复活）。"""
    from services.order_maintenance import notify_expiring_orders

    tenant = await make_tenant(db, "pgrev002")
    order = await make_order(db, tenant.id, "PGREV-ORD")
    order.expired_at = datetime.datetime.utcnow() + datetime.timedelta(hours=12)
    await db.commit()

    assert await notify_expiring_orders(db) == 1, "首次调度应产生 1 条临期提醒"
    await db.commit()

    headers_tenant = auth_header(tenant_token(tenant.id))
    r = await client.get(f"{BASE}/api/v1/notifications/tenant-mine", headers=headers_tenant)
    reminders = [n for n in r.json()["items"] if n["title"] == "订单即将过期"]
    assert len(reminders) == 1
    reminder_id = reminders[0]["id"]

    r = await client.post(
        f"{BASE}/api/v1/notifications/tenant-delete",
        json={"ids": [reminder_id]},
        headers=headers_tenant,
    )
    assert r.status_code == 200 and r.json()["marked"] == 1

    db.expire_all()
    assert await notify_expiring_orders(db) == 0, "被删除的临期提醒不得复活"
    await db.commit()
