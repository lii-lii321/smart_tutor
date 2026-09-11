"""
内部运营统计回归（PLAN P2-5 降级方案）：
- 超管可查询六大维度聚合（租户/教员/订单/投递/资金/审计）；
- 中介 403；数值与造数一致。

运行方式：pytest tests/test_internal_stats.py
"""
from decimal import Decimal

from conftest import (
    auth_header,
    make_order,
    make_teacher,
    make_tenant,
    teacher_token,
    tenant_token,
)

from models.domain import FinancialRecord, FinancialType, OrderStatus
from services.auth import create_jwt

BASE = "http://test"


async def test_internal_stats_shape_and_auth(client, db):
    from models.domain import Application, ApplicationStatus

    tenant = await make_tenant(db, "stats001")
    teacher = await make_teacher(db, "stats_teacher")
    order = await make_order(db, tenant.id, "STATS-001")
    db.add(Application(
        order_id=order.id, teacher_id=teacher.id, tenant_id=tenant.id,
        status=ApplicationStatus.pending,
    ))
    db.add(FinancialRecord(
        order_id=order.id, tenant_id=tenant.id, teacher_id=teacher.id,
        amount=Decimal("100.00"), type=FinancialType.deposit_in, remark="定金",
    ))
    await db.commit()

    boss = create_jwt(sub="super_admin_1", role="super_admin")
    resp = await client.get(f"{BASE}/api/v1/internal/stats", headers=auth_header(boss))
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["tenants"] == {"total": 1, "active": 1}
    assert body["teachers"] == {"total": 1, "banned": 0}
    assert body["orders"]["recruiting"] == 1
    assert body["applications"]["pending"] == 1
    assert body["finance"]["deposit_in"] == 100.0
    assert body["finance"]["net_amount"] == 100.0
    assert set(body["orders"].keys()) == {s.value for s in OrderStatus}
    assert body["audit"]["total"] == 0  # 本用例未触发资金写路径

    # 静默订单（无投递、无流水）不参与也不影响其他维度
    await make_order(db, tenant.id, "STATS-002")
    await db.commit()
    resp = await client.get(f"{BASE}/api/v1/internal/stats", headers=auth_header(boss))
    assert resp.status_code == 200
    assert resp.json()["orders"]["recruiting"] == 2
    assert resp.json()["finance"]["deposit_in"] == 100.0


async def test_internal_stats_forbidden_for_tenant_and_teacher(client, db):
    tenant = await make_tenant(db, "stats002")
    teacher = await make_teacher(db, "stats_teacher2")
    await db.commit()

    resp = await client.get(
        f"{BASE}/api/v1/internal/stats", headers=auth_header(tenant_token(tenant.id))
    )
    assert resp.status_code == 403

    resp = await client.get(
        f"{BASE}/api/v1/internal/stats", headers=auth_header(teacher_token(teacher.id))
    )
    assert resp.status_code == 403
