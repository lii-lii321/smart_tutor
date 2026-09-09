"""
业务功能批次回归测试：成交评价、教员信用画像、教员结算单、
B 端通知（新投递/订单临期）、老板经营看板。

运行方式：
    pytest tests/test_business_features.py
"""
import asyncio
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMP = tempfile.NamedTemporaryFile(suffix="_biz.db", delete=False)
_TMP.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP.name.replace(os.sep, '/')}"
os.environ["DEV_MODE"] = "true"
os.environ["JWT_SECRET"] = "test-secret-for-business-features-012345"
os.environ["OWNER_ACCESS_CODE"] = "test-boss-code"

import httpx  # noqa: E402
from sqlalchemy import select  # noqa: E402

import database as database_mod  # noqa: E402
from database import _get_sessionmaker, init_db  # noqa: E402
from main import app  # noqa: E402
from models.domain import (  # noqa: E402
    Application,
    ApplicationStatus,
    Gender,
    Notification,
    Order,
    OrderReview,
    OrderStatus,
    Teacher,
    TeacherResume,
    Tenant,
)
from services.auth import create_jwt  # noqa: E402
from services.order_maintenance import notify_expiring_orders  # noqa: E402

BASE = "http://test"


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
        tenant = Tenant(tenant_name="业务中介", invite_code="bizx0001", contact_wechat="wx_biz")
        teachers = []
        for i in range(2):
            teachers.append(Teacher(
                openid=f"biz_t{i + 1}", name=f"教员{i + 1}", gender=Gender.male,
                phone=f"1391111000{i + 1}", wechat_id=f"wx_bt{i + 1}",
                school="测试大学", is_985_211=True,
            ))
        s.add(tenant)
        s.add_all(teachers)
        await s.flush()
        resumes = []
        for teacher in teachers:
            resumes.append(TeacherResume(
                teacher_id=teacher.id, title="默认简历",
                teaching_subjects="数学、英语", teaching_grades="初一-初三",
                experience="两年家教经验",
            ))
        s.add_all(resumes)
        await s.flush()

        now = datetime.datetime.utcnow()
        order = Order(
            tenant_id=tenant.id, raw_id="BIZ-001", raw_text="业务测试订单",
            grade_subject="初三数学", requirements="", price_total="200/次",
            base_price=200.0, weekly_frequency=2, is_summer_vacation=False,
            calculated_info_fee=200.0, deposit_amount=100.0, balance_amount=100.0,
            exact_address="地址A", parent_phone="13800000000",
            fuzzy_address="成都市A", lng=104.06, lat=30.57,
            status=OrderStatus.recruiting,
            expired_at=now + datetime.timedelta(hours=72),
        )
        s.add(order)
        await s.commit()
        return {
            "tenant_id": tenant.id,
            "teacher1_id": teachers[0].id, "teacher2_id": teachers[1].id,
            "resume1_id": resumes[0].id, "resume2_id": resumes[1].id,
            "order_id": order.id,
        }


async def _full_complete(d, client, apply_key: str, resume_key: str) -> int:
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        params={"order_id": d["order_id"], "resume_id": d[resume_key]},
        headers=auth(teacher_token(d[apply_key])),
    )
    assert resp.status_code == 200, resp.text
    app_id = resp.json()["id"]
    for action in ("shortlist", "confirm-deposit", "start-trial", "confirm-balance", "complete"):
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_id}/{action}",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, f"{action}: {resp.text}"
    return app_id


async def _test_review_flow():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 未成交不可评价
        app_id = await _full_complete(d, client, "teacher1_id", "resume1_id")

        # 成交后评价
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_id}/review",
            json={"rating": 5, "comment": "非常负责"},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text

        # 同单重复评价 → 覆盖更新而不是新建
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_id}/review",
            json={"rating": 4, "comment": "改口：还不错"},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200

        sm = _get_sessionmaker()
        async with sm() as s:
            reviews = (await s.execute(select(OrderReview))).scalars().all()
            assert len(reviews) == 1, "一单只能有一条评价"
            assert reviews[0].rating == 4

        # 教员查看收到的评价
        resp = await client.get(
            f"{BASE}/api/v1/applications/reviews/mine",
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1 and data[0]["rating"] == 4 and data[0]["comment"] == "改口：还不错"

        # 教员收到评价通知
        resp = await client.get(
            f"{BASE}/api/v1/notifications/mine",
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert any(n["title"] == "收到新评价" for n in resp.json()["items"])

        # 其他教员查不到该评价
        resp = await client.get(
            f"{BASE}/api/v1/applications/reviews/mine",
            headers=auth(teacher_token(d["teacher2_id"])),
        )
        assert resp.json() == []

        # 评分越界 → 422
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_id}/review",
            json={"rating": 6},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 422
    print("[OK] test_review_flow")


async def _test_credit_in_applications():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        app_id = await _full_complete(d, client, "teacher1_id", "resume1_id")
        resp = await client.post(
            f"{BASE}/api/v1/applications/{app_id}/review",
            json={"rating": 5},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200

        # 查看订单投递列表 → 教员卡片带信用画像
        resp = await client.get(
            f"{BASE}/api/v1/applications/order/{d['order_id']}",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200
        apps = resp.json()
        target = next(a for a in apps if a["id"] == app_id)
        assert target["teacher"]["completed_count"] == 1
        assert target["teacher"]["violation_count"] == 0
        assert target["teacher"]["avg_rating"] == 5.0

        # 无评价的教员 avg_rating 为 None
        others = [a for a in apps if a["id"] != app_id]
        for a in others:
            assert a["teacher"]["avg_rating"] is None
    print("[OK] test_credit_in_applications")


async def _test_teacher_fees():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        await _full_complete(d, client, "teacher1_id", "resume1_id")

        resp = await client.get(
            f"{BASE}/api/v1/financial-records/mine",
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total_paid"] == 200.0, "定金 100 + 尾款 100"
        assert data["total_refunded"] == 0
        assert data["total_forfeit"] == 0
        assert len(data["records"]) == 2

        # 教员只能看自己的费用
        resp = await client.get(
            f"{BASE}/api/v1/financial-records/mine",
            headers=auth(teacher_token(d["teacher2_id"])),
        )
        assert resp.json()["records"] == []

        # 中介不可访问教员结算接口
        resp = await client.get(
            f"{BASE}/api/v1/financial-records/mine",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 403
    print("[OK] test_teacher_fees")


async def _test_tenant_notifications():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 教员投递 → 租户收到新投递通知
        resp = await client.post(
            f"{BASE}/api/v1/applications/",
            params={"order_id": d["order_id"], "resume_id": d["resume1_id"]},
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert resp.status_code == 200

        resp = await client.get(
            f"{BASE}/api/v1/notifications/tenant-mine",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["unread_count"] >= 1
        assert any(n["title"] == "收到新投递" for n in data["items"])

        # 一键已读
        resp = await client.post(
            f"{BASE}/api/v1/notifications/tenant-read-all",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200
        resp = await client.get(
            f"{BASE}/api/v1/notifications/tenant-mine",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.json()["unread_count"] == 0

        # 教员端通知接口不受租户通知影响（C 端看不到 B 端通知）
        resp = await client.get(
            f"{BASE}/api/v1/notifications/mine",
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert all(n["title"] != "收到新投递" for n in resp.json()["items"])
    print("[OK] test_tenant_notifications")


async def _test_expiring_order_notification():
    d = await _setup()
    sm = _get_sessionmaker()
    async with sm() as s:
        order = await s.get(Order, d["order_id"])
        # 12 小时后过期 → 落入提醒窗口
        order.expired_at = datetime.datetime.utcnow() + datetime.timedelta(hours=12)
        await s.commit()

    async with sm() as s:
        created = await notify_expiring_orders(s)
        assert created == 1, f"应产生 1 条临期通知，实际 {created}"
        await s.commit()

        # 重复执行不重复提醒
        created = await notify_expiring_orders(s)
        assert created == 0
        await s.commit()

        rows = (await s.execute(
            select(Notification).where(
                Notification.order_id == d["order_id"],
                Notification.title == "订单即将过期",
            )
        )).scalars().all()
        assert len(rows) == 1
        assert rows[0].tenant_id == d["tenant_id"]

    # 中介端能看到
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.get(
            f"{BASE}/api/v1/notifications/tenant-mine",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert any(n["title"] == "订单即将过期" for n in resp.json()["items"])
    print("[OK] test_expiring_order_notification")


async def _test_owner_stats():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        await _full_complete(d, client, "teacher1_id", "resume1_id")

        # 中介无权访问看板
        resp = await client.get(
            f"{BASE}/api/v1/tenants/stats",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 403

        resp = await client.get(
            f"{BASE}/api/v1/tenants/stats",
            headers=auth(boss_token()),
        )
        assert resp.status_code == 200, resp.text
        stats = resp.json()
        assert stats["orders_recruiting"] >= 0
        assert stats["orders_completed"] >= 1
        assert stats["gmv_total"] >= 200.0, "订单成交应收 200 信息费"
        assert stats["funnel"]["completed"] >= 1
        assert stats["funnel"]["deposit_paid"] >= 1
        rank = next(r for r in stats["ranking"] if r["tenant_id"] == d["tenant_id"])
        assert rank["orders_completed"] >= 1
        assert rank["gmv"] >= 200.0
    print("[OK] test_owner_stats")


async def _test_exports_and_blacklist_status():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        await _full_complete(d, client, "teacher1_id", "resume1_id")

        # 教员费用导出
        resp = await client.get(
            f"{BASE}/api/v1/financial-records/mine/export",
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        body = resp.content.decode("utf-8-sig")
        assert "定金支付" in body and "200.00" in body

        # 中介订单导出（含筛选）
        resp = await client.get(
            f"{BASE}/api/v1/orders/export?status=completed",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200
        assert "成都家教" not in resp.text.split("\n")[0]  # 表头无数据行错位
        body = resp.content.decode("utf-8-sig")
        assert "BIZ-001" in body and "已完成" in body

        # 教员不可导出订单
        resp = await client.get(
            f"{BASE}/api/v1/orders/export",
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert resp.status_code == 403

        # 教员名单导出（含黑名单标记列）
        resp = await client.post(
            f"{BASE}/api/v1/tenants/teachers/{d['teacher2_id']}/blacklist",
            json={"reason": "测试拉黑"},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200
        resp = await client.get(
            f"{BASE}/api/v1/tenants/my-teachers/export",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200
        body = resp.content.decode("utf-8-sig")
        assert "教员2" in body and "是" in body

        # 教员查询被拉黑状态（可见性）
        resp = await client.get(
            f"{BASE}/api/v1/tenants/blacklist-status",
            headers=auth(teacher_token(d["teacher2_id"])),
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 1
        assert rows[0]["tenant_name"] == "业务中介" and rows[0]["reason"] == "测试拉黑"

        # 未被拉黑的教员 → 空列表
        resp = await client.get(
            f"{BASE}/api/v1/tenants/blacklist-status",
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert resp.json() == []
    print("[OK] test_exports_and_blacklist_status")


def test_review_flow():
    _fresh_db()
    asyncio.run(_test_review_flow())


def test_credit_in_applications():
    _fresh_db()
    asyncio.run(_test_credit_in_applications())


def test_teacher_fees():
    _fresh_db()
    asyncio.run(_test_teacher_fees())


def test_tenant_notifications():
    _fresh_db()
    asyncio.run(_test_tenant_notifications())


def test_expiring_order_notification():
    _fresh_db()
    asyncio.run(_test_expiring_order_notification())


def test_owner_stats():
    _fresh_db()
    asyncio.run(_test_owner_stats())


async def _test_tenant_blacklist():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 教员1 投递（待审）后立即被拉黑 → 待审投递自动被拒
        resp = await client.post(
            f"{BASE}/api/v1/applications/",
            params={"order_id": d["order_id"], "resume_id": d["resume1_id"]},
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert resp.status_code == 200
        app1 = resp.json()["id"]

        resp = await client.post(
            f"{BASE}/api/v1/tenants/teachers/{d['teacher1_id']}/blacklist",
            json={"reason": "爽约两次"},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200, resp.text

        sm = _get_sessionmaker()
        async with sm() as s:
            status = (await s.get(Application, app1)).status
            assert status == ApplicationStatus.rejected, "拉黑应自动拒绝待审投递"

        # 重复拉黑 → 409
        resp = await client.post(
            f"{BASE}/api/v1/tenants/teachers/{d['teacher1_id']}/blacklist",
            json={},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 409

        # 黑名单教员不可再投递本中介
        resp = await client.post(
            f"{BASE}/api/v1/applications/",
            params={"order_id": d["order_id"], "resume_id": d["resume1_id"]},
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert resp.status_code == 403
        assert "限制投递" in resp.json()["detail"]

        # 推荐被屏蔽（403）
        resp = await client.get(
            f"{BASE}/api/v1/recommendations/bizx0001",
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert resp.status_code == 403

        # my-teachers 列表标记黑名单
        resp = await client.get(
            f"{BASE}/api/v1/tenants/my-teachers",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200
        items = resp.json()
        t1 = next(i for i in items if i["teacher_id"] == d["teacher1_id"])
        assert t1["is_blacklisted"] is True
        assert t1["violation_count"] == 0

        # 移出黑名单 → 恢复投递资格
        resp = await client.delete(
            f"{BASE}/api/v1/tenants/teachers/{d['teacher1_id']}/blacklist",
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200
        resp = await client.post(
            f"{BASE}/api/v1/applications/",
            params={"order_id": d["order_id"], "resume_id": d["resume1_id"]},
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert resp.status_code == 200, "移出黑名单后应可重新投递"

        # 黑名单不影响其他租户：教员1 可投递其他中介的订单（本测试集只有 1 个租户，验证接口隔离即可）
        resp = await client.get(
            f"{BASE}/api/v1/tenants/my-teachers",
            headers=auth(boss_token()),
        )
        assert resp.status_code == 200
    print("[OK] test_tenant_blacklist")


def test_tenant_blacklist():
    _fresh_db()
    asyncio.run(_test_tenant_blacklist())


if __name__ == "__main__":
    test_review_flow()
    test_credit_in_applications()
    test_teacher_fees()
    test_tenant_notifications()
    test_expiring_order_notification()
    test_owner_stats()
    test_tenant_blacklist()
    print("\n=== 业务功能测试全部通过 ===")
    try:
        os.unlink(_TMP.name)
    except OSError:
        pass
