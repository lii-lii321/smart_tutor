"""
夜间批次防退化回归（对应 2026-09-09/09-10 修复集）：
- 停用中介邀请码不得放行教员登录/注册；
- /financial-records/mine 分页生效且汇总不受分页影响；
- /applications/reviews/mine 分页；
- trial-failed 退款金额 Decimal 舍入到分；
- 审查加固批次：限流真实 IP、过期提醒按周期去重、PATCH 忽略非空列 null、
  super_admin 拉黑 403、AUTO_CREATE_SCHEMA 生产护栏。

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


# ── 审查加固批次（2026-09-10 晚） ──


def test_client_ip_prefers_x_real_ip():
    """限流键必须取 nginx 覆写的 X-Real-IP，否则全体客户端共享一个 web 容器 IP。"""
    from starlette.requests import Request as StarletteRequest

    from routers.v1.auth import _client_ip

    scope = {
        "type": "http",
        "client": ("10.0.0.1", 12345),
        "headers": [(b"x-real-ip", b"203.0.113.7")],
    }
    assert _client_ip(StarletteRequest(scope)) == "203.0.113.7"

    scope_no_header = {"type": "http", "client": ("10.0.0.1", 12345), "headers": []}
    assert _client_ip(StarletteRequest(scope_no_header)) == "10.0.0.1"

    scope_no_client = {"type": "http", "headers": []}
    assert _client_ip(StarletteRequest(scope_no_client)) == "unknown"


def test_auto_create_schema_forbidden_in_production():
    """生产（非 DEV_MODE）误开 AUTO_CREATE_SCHEMA 必须在配置加载时硬失败。"""
    from config import Settings

    def make_settings(**kwargs):
        # _env_file=None 隔离本地 .env，显式提供其余生产必填项
        return Settings(
            _env_file=None,
            DEV_MODE=False,
            JWT_SECRET="hardening-test-secret-0123456789abcdef",
            OWNER_ACCESS_CODE="hardening-boss-code",
            **kwargs,
        )

    make_settings(AUTO_CREATE_SCHEMA=False)  # 合法组合不抛
    try:
        make_settings(AUTO_CREATE_SCHEMA=True)
    except RuntimeError as e:
        assert "AUTO_CREATE_SCHEMA" in str(e)
    else:
        raise AssertionError("生产开启 AUTO_CREATE_SCHEMA 应被拒绝")


async def test_order_patch_ignores_null_for_non_nullable_columns(client, db):
    """PATCH 显式 null 打到非空列应按未提供处理（修复前 500），可空字段仍可置空。"""
    tenant = await make_tenant(db, "patch001")
    order = await make_order(db, tenant.id, "PATCH-001")
    await db.commit()

    r = await client.patch(
        f"{BASE}/api/v1/orders/{order.id}",
        json={"grade_subject": None, "lng": None, "subway_remark": None},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["grade_subject"] == "初三数学", "非空列的 null 应被忽略"
    assert body["subway_remark"] is None, "可空字段显式 null 仍应置空"

    await db.refresh(order)
    assert order.lng is not None


async def test_super_admin_blacklist_rejected(client, db):
    """超管无租户，拉黑（租户级黑名单）应 403 而非 500。"""
    from services.auth import create_jwt

    teacher = await make_teacher(db, "bl_teacher")
    await db.commit()
    boss = create_jwt(sub="super_admin_1", role="super_admin")

    r = await client.post(
        f"{BASE}/api/v1/tenants/teachers/{teacher.id}/blacklist",
        json={"reason": "测试"},
        headers=auth_header(boss),
    )
    assert r.status_code == 403, f"超管拉黑应 403: {r.status_code} {r.text}"


async def test_expiry_reminder_dedupes_per_cycle(client, db, monkeypatch):
    """订单重开刷新有效期后，旧周期的临期提醒不得压制新一轮提醒。"""
    from sqlalchemy import select

    from models.domain import Notification
    from services.order_maintenance import notify_expiring_orders

    tenant = await make_tenant(db, "expir001")
    order = await make_order(db, tenant.id, "EXPR-001")
    order.expired_at = datetime.datetime.utcnow() + datetime.timedelta(hours=2)
    await db.commit()

    assert await notify_expiring_orders(db) == 1, "首周期应产生一条提醒"
    assert await notify_expiring_orders(db) == 0, "同周期内不得重复提醒"

    # 模拟跨周期：把旧提醒回写到 80 小时前，再按 republish 语义刷新有效期（now+72h 起算，
    # 本周期起点 = expired_at − 72h = now−70h，晚于旧提醒时间）
    rows = (await db.execute(
        select(Notification).where(Notification.order_id == order.id)
    )).scalars().all()
    for row in rows:
        row.created_at = datetime.datetime.utcnow() - datetime.timedelta(hours=80)
    order.expired_at = datetime.datetime.utcnow() + datetime.timedelta(hours=2)
    await db.commit()

    assert await notify_expiring_orders(db) == 1, "重开后的新周期应能再次提醒"
