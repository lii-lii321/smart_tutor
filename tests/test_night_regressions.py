"""
夜间批次防退化回归（对应 2026-09-09 修复集）：
- 停用中介邀请码不得放行教员登录/注册；
- /financial-records/mine 分页生效且汇总不受分页影响；
- /applications/reviews/mine 分页；
- trial-failed 退款金额 Decimal 舍入到分。

运行方式：pytest tests/test_night_regressions.py
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

BASE = "http://test"


def _allow_login_rate(monkeypatch) -> None:
    """本组用例与存量测试共享进程内限流桶，这里局部放宽避免跨文件误伤 429。"""
    from config import settings
    monkeypatch.setattr(settings, "MAX_LOGIN_PER_MINUTE", 1000)


async def test_inactive_tenant_invite_code_blocks_login(client, db, monkeypatch):
    _allow_login_rate(monkeypatch)
    tenant = await make_tenant(db, "dead0001", is_active=False)
    teacher = await make_teacher(db, "dead_teacher", phone="13900000001")
    await db.commit()

    r = await client.post(f"{BASE}/api/v1/auth/teacher-phone-login", json={
        "phone": teacher.phone,
        "invite_code": tenant.invite_code,
        "password": "whatever6",
    })
    assert r.status_code == 403, r.text
    assert "停用" in r.json()["detail"]


async def test_inactive_tenant_invite_code_blocks_register(client, db, monkeypatch):
    _allow_login_rate(monkeypatch)
    tenant = await make_tenant(db, "dead0002", is_active=False)
    await db.commit()

    r = await client.post(f"{BASE}/api/v1/auth/teacher-phone-register", json={
        "phone": "13900000002",
        "invite_code": tenant.invite_code,
        "password": "abc12345",
        "name": "注册教员",
        "gender": "male",
        "wechat_id": "wx_reg1",
        "school": "测试大学",
    })
    assert r.status_code == 403, r.text

    # 对照组：启用中介可正常注册
    ok_tenant = await make_tenant(db, "alive001", is_active=True)
    await db.commit()
    r2 = await client.post(f"{BASE}/api/v1/auth/teacher-phone-register", json={
        "phone": "13900000003",
        "invite_code": ok_tenant.invite_code,
        "password": "abc12345",
        "name": "正常教员",
        "gender": "male",
        "wechat_id": "wx_reg2",
        "school": "测试大学",
    })
    assert r2.status_code == 200, r2.text


async def test_my_fees_pagination_keeps_totals(client, db):
    from decimal import Decimal

    from models.domain import FinancialRecord, FinancialType

    tenant = await make_tenant(db, "fee00001")
    teacher = await make_teacher(db, "fee_teacher")
    order = await make_order(db, tenant.id, "FEE-001")
    db.add_all([
        FinancialRecord(order_id=order.id, tenant_id=tenant.id, teacher_id=teacher.id,
                        amount=Decimal("100.00"), type=FinancialType.deposit_in, remark="定金1"),
        FinancialRecord(order_id=order.id, tenant_id=tenant.id, teacher_id=teacher.id,
                        amount=Decimal("100.00"), type=FinancialType.deposit_in, remark="定金2"),
        FinancialRecord(order_id=order.id, tenant_id=tenant.id, teacher_id=teacher.id,
                        amount=Decimal("50.00"), type=FinancialType.refund_out, remark="退款"),
    ])
    await db.commit()

    headers = auth_header(teacher_token(teacher.id))
    r = await client.get(f"{BASE}/api/v1/financial-records/mine", params={
        "page": 1, "page_size": 1,
    }, headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["records"]) == 1, "分页应只返回 1 条"
    assert body["total_paid"] == 200.0, "汇总不随分页收窄"
    assert body["total_refunded"] == 50.0

    # 不带分页时全量返回（兼容旧调用）
    r2 = await client.get(f"{BASE}/api/v1/financial-records/mine", headers=headers)
    assert len(r2.json()["records"]) == 3


async def test_my_reviews_pagination(client, db):
    from models.domain import OrderReview

    tenant = await make_tenant(db, "rev00001")
    teacher = await make_teacher(db, "rev_teacher")
    order1 = await make_order(db, tenant.id, "REV-001")
    order2 = await make_order(db, tenant.id, "REV-002")
    db.add_all([
        OrderReview(order_id=order1.id, application_id=0, tenant_id=tenant.id,
                    teacher_id=teacher.id, rating=5, comment="很好"),
        OrderReview(order_id=order2.id, application_id=0, tenant_id=tenant.id,
                    teacher_id=teacher.id, rating=4, comment="不错"),
    ])
    await db.commit()

    headers = auth_header(teacher_token(teacher.id))
    r = await client.get(f"{BASE}/api/v1/applications/reviews/mine", params={
        "page": 1, "page_size": 1,
    }, headers=headers)
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1, "分页应只返回 1 条"

    r2 = await client.get(f"{BASE}/api/v1/applications/reviews/mine", headers=headers)
    assert len(r2.json()) == 2


async def test_trial_failed_refund_decimal_rounding(client, db):
    from decimal import Decimal

    from sqlalchemy import select

    from models.domain import (
        Application,
        ApplicationStatus,
        FinancialRecord,
        FinancialType,
    )

    tenant = await make_tenant(db, "dec00001")
    teacher = await make_teacher(db, "dec_teacher")
    order = await make_order(db, tenant.id, "DEC-001")
    application = Application(
        order_id=order.id, teacher_id=teacher.id, tenant_id=tenant.id,
        status=ApplicationStatus.deposit_paid,
        deposit_paid_at=datetime.datetime.utcnow(),
    )
    db.add(application)
    await db.commit()

    r = await client.post(
        f"{BASE}/api/v1/applications/{application.id}/trial-failed",
        params={"refund_amount": "10.005"},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "refunded"

    rows = (await db.execute(
        select(FinancialRecord).where(
            FinancialRecord.order_id == order.id,
            FinancialRecord.type == FinancialType.refund_out,
        )
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].amount == Decimal("10.01"), f"HALF_UP 舍入应为 10.01，实际 {rows[0].amount}"
