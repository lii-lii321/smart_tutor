"""
安全守卫回归测试（第 2 阶段）。

覆盖：
- DEV_MODE 关闭时 dev-login / dev-register / dev-tenant 一律 403（生产开关回归保护）；
- DEV_MODE 关闭时 seed-demo 为无操作（不注入演示数据）；
- 投递报价超上限返回 422 而非 DECIMAL 溢出 500；
- 自带价订单导入时客户端金额被服务端置零（不信任客户端金额）；
- 微信注册入口限流（未鉴权流量不可无限触发微信外呼）。

运行方式：
    pytest tests/test_security_guards.py
"""
import datetime

from conftest import (
    auth_header,
    make_teacher,
    make_tenant,
    teacher_token,
    tenant_token,
)
from sqlalchemy import select

from config import settings
from models.domain import Order, Tenant
from utils.clock import utcnow

BASE = "http://test"


def boss_token() -> str:
    from services.auth import create_jwt
    return create_jwt(sub="super_admin_1", role="super_admin")


async def test_dev_endpoints_rejected_without_dev_mode(client, db, monkeypatch):
    monkeypatch.setattr(settings, "DEV_MODE", False)

    resp = await client.post(f"{BASE}/api/v1/auth/dev-login")
    assert resp.status_code == 403
    resp = await client.post(f"{BASE}/api/v1/auth/dev-register")
    assert resp.status_code == 403
    resp = await client.post(f"{BASE}/api/v1/auth/dev-tenant")
    assert resp.status_code == 403


async def test_seed_demo_noop_without_dev_mode(client, db, monkeypatch):
    await make_tenant(db, "guard001")
    await db.commit()

    monkeypatch.setattr(settings, "DEV_MODE", False)
    resp = await client.post(
        f"{BASE}/api/v1/tenants/seed-demo",
        headers=auth_header(boss_token()),
    )
    assert resp.status_code == 200, resp.text

    tenants = (await db.execute(select(Tenant))).scalars().all()
    assert len(tenants) == 1, "DEV_MODE 关闭时 seed-demo 不得注入演示数据"


async def test_apply_proposed_price_upper_bound_422(client, db):
    tenant = await make_tenant(db, "guard002")
    teacher = await make_teacher(db, "guard_teacher")
    from models.domain import OrderStatus, TeacherResume
    resume = TeacherResume(
        teacher_id=teacher.id, title="默认简历",
        teaching_subjects="数学", teaching_grades="初一-初三", experience="两年经验",
    )
    db.add(resume)
    # 自带价订单：base_price=0，必须报价投递
    order = Order(
        tenant_id=tenant.id, raw_id="GUARD-SELF", raw_text="【GUARD-SELF】自带价订单",
        grade_subject="初三数学", requirements="", price_total="自带价",
        base_price=0.0, weekly_frequency=2, is_summer_vacation=False,
        calculated_info_fee=0.0, deposit_amount=0.0, balance_amount=0.0,
        fuzzy_address="成都市天府大道", lng=104.065735, lat=30.659462,
        status=OrderStatus.recruiting,
        expired_at=utcnow() + datetime.timedelta(hours=72),
    )
    db.add(order)
    await db.commit()
    headers = auth_header(teacher_token(teacher.id))

    # 合法报价正常通过
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        json={"order_id": order.id, "resume_id": resume.id, "proposed_price": 250},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    # 超上限报价：在参数层被 422 拒绝，而不是 DECIMAL(8,2) 溢出 500
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        json={"order_id": order.id, "resume_id": resume.id, "proposed_price": 12345678.0},
        headers=headers,
    )
    assert resp.status_code == 422, f"报价超上限应 422: {resp.status_code}"


async def test_batch_import_zeroes_client_amounts_for_self_priced(client, db):
    tenant = await make_tenant(db, "guard003")
    await db.commit()
    headers = auth_header(tenant_token(tenant.id))

    payload = {
        "items": [{
            "raw_id": "GUARD-IMP-001", "raw_text": "自带价单",
            "grade_subject": "高一英语", "requirements": "",
            "price_total": "自带价", "base_price": 0,
            "weekly_frequency": 1, "is_summer_vacation": False,
            "fuzzy_address": "成都市武侯区", "lng": 104.04, "lat": 30.64,
            # 客户端伪造的金额：导入后必须被服务端置零
            "calculated_info_fee": 88.88, "deposit_amount": 88.88, "balance_amount": 88.88,
        }]
    }
    resp = await client.post(f"{BASE}/api/v1/orders/batch-import", json=payload, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 1

    order = (await db.execute(
        select(Order).where(Order.raw_id == "GUARD-IMP-001")
    )).scalar_one()
    assert float(order.calculated_info_fee) == 0.0
    assert float(order.deposit_amount) == 0.0
    assert float(order.balance_amount) == 0.0

    resp = await client.get(f"{BASE}/api/v1/orders/{order.id}", headers=headers)
    assert resp.status_code == 200, resp.text
    detail = resp.json()
    assert detail["needs_manual_price"] is True


async def test_teacher_register_rate_limited(client, db):
    # 限流在微信外呼之前：无 WX 配置时前 10 次为 502，第 11 次应被 429 拦截
    statuses = []
    for _ in range(11):
        resp = await client.post(
            f"{BASE}/api/v1/auth/teacher-register",
            params={"code": "any-code"},
            json={"name": "限流测试", "phone": "13899990000", "wechat_id": "wx_rl",
                  "school": "测试大学", "gender": "male"},
        )
        statuses.append(resp.status_code)
    assert 429 in statuses, f"微信注册入口应触发限流: {statuses}"
