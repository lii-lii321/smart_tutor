"""
教员公开成绩单：脱敏口径（姓氏展示/不露联系方式）、封禁 404、聚合数据正确性、
评价携带科目。无需登录（路由无鉴权依赖），跨租户可见属产品预期（转发给家长）。
"""
from conftest import make_order, make_teacher, make_tenant
from sqlalchemy import text, update

from models.domain import (
    Application,
    ApplicationStatus,
    FinancialRecord,
    FinancialType,
    OrderReview,
)
from utils.clock import utcnow

BASE = "http://test"


async def _completed_application(db, tenant, teacher, raw_id: str) -> Application:
    order = await make_order(db, tenant.id, raw_id)
    app = Application(
        order_id=order.id,
        teacher_id=teacher.id,
        tenant_id=tenant.id,
        status=ApplicationStatus.completed,
    )
    db.add(app)
    await db.flush()
    review = OrderReview(
        order_id=order.id,
        application_id=app.id,
        tenant_id=tenant.id,
        teacher_id=teacher.id,
        rating=5,
        comment="讲解清晰，孩子很喜欢",
    )
    db.add(review)
    return app


async def test_scorecard_masked_aggregates(client, db):
    tenant = await make_tenant(db, "sc001a")
    teacher = await make_teacher(db, "sc_teacher_a", name="王小明")
    await _completed_application(db, tenant, teacher, "SC-001")
    db.add(FinancialRecord(
        order_id=1, tenant_id=tenant.id, teacher_id=teacher.id,
        amount=100, type=FinancialType.forfeit,
    ))
    await db.commit()

    resp = await client.get(f"{BASE}/api/v1/public/teacher/{teacher.id}/scorecard")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 脱敏：只露姓氏，不露手机/微信
    assert body["display_name"] == "王老师"
    assert "王小明" not in resp.text
    assert "phone" not in body and "wechat_id" not in body
    # 聚合
    assert body["completed_count"] == 1
    assert body["violation_count"] == 1
    assert body["avg_rating"] == 5.0
    assert body["review_count"] == 1
    assert body["reviews"][0]["comment"] == "讲解清晰，孩子很喜欢"
    # 院校公开、标签来自院校标记（make_teacher 只勾联合位 → 985/211 兜底标签）
    assert body["school"] == "测试大学"
    assert "985/211" in body["tags"]


async def test_scorecard_single_char_name(client, db):
    tenant = await make_tenant(db, "sc002a")
    teacher = await make_teacher(db, "sc_teacher_b", name="李芳")
    await db.commit()
    resp = await client.get(f"{BASE}/api/v1/public/teacher/{teacher.id}/scorecard")
    assert resp.json()["display_name"] == "李老师"


async def test_scorecard_banned_and_missing_are_404(client, db):
    tenant = await make_tenant(db, "sc003a")
    teacher = await make_teacher(db, "sc_teacher_c")
    teacher.is_banned = True
    await db.commit()

    resp = await client.get(f"{BASE}/api/v1/public/teacher/{teacher.id}/scorecard")
    assert resp.status_code == 404

    resp = await client.get(f"{BASE}/api/v1/public/teacher/999999/scorecard")
    assert resp.status_code == 404


async def test_scorecard_reviews_carry_subject_and_order_desc(client, db):
    """评价列表携带订单科目，且新评价在前（家长先看最近的）。"""
    tenant = await make_tenant(db, "sc004a")
    teacher = await make_teacher(db, "sc_teacher_d")
    await _completed_application(db, tenant, teacher, "SC-002A")
    await _completed_application(db, tenant, teacher, "SC-002B")

    # 后写的一单评分时间戳更近：显式后移保证排序稳定
    import datetime


    await db.execute(
        update(OrderReview)
        .where(OrderReview.order_id == (
            await db.execute(
                text("SELECT id FROM orders WHERE raw_id='SC-002B'")
            )
        ).scalar_one())
        .values(created_at=utcnow() + datetime.timedelta(seconds=5))
    )
    await db.commit()

    resp = await client.get(f"{BASE}/api/v1/public/teacher/{teacher.id}/scorecard")
    body = resp.json()
    assert body["review_count"] == 2
    assert all(r["grade_subject"] for r in body["reviews"])
    assert body["reviews"][0]["created_at"] >= body["reviews"][1]["created_at"]
