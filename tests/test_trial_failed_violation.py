"""
业务规则回归：正常试课失败不得记教员违约。

历史缺陷：is_teacher_violated=false 且零退款时，状态被置为 forfeited 并写入
forfeit 流水——违约次数按没收流水统计，导致正常失败被计成教员违约。

规则：
- 正常失败 + 零退款 → 状态 refunded，写 0 元 refund_out 留台账，不产生 forfeit；
- 教员违约 → 状态 forfeited，写 forfeit 流水，违约 +1。

运行方式：
    pytest tests/test_trial_failed_violation.py
"""
import datetime

from conftest import BASE, auth_header, make_order, make_teacher, make_tenant, tenant_token
from sqlalchemy import select

from models.domain import Application, FinancialRecord, FinancialType


async def _setup_app(db, status):
    tenant = await make_tenant(db, "tfx0001")
    teacher = await make_teacher(db, "tfx_teacher")
    order = await make_order(db, tenant.id, "TFX-001")
    app = Application(
        order_id=order.id, teacher_id=teacher.id, tenant_id=tenant.id,
        status=status, deposit_paid_at=datetime.datetime.utcnow(),
    )
    db.add(app)
    await db.commit()
    return tenant, teacher, app


async def test_normal_trial_failed_zero_refund_not_violation(client, db):
    """正常试课失败 + 零退款：状态 refunded、写 0 元退款流水、不产生没收流水。"""
    tenant, teacher, app = await _setup_app(db, "deposit_paid")

    r = await client.post(
        f"{BASE}/api/v1/applications/{app.id}/trial-failed",
        json={"refund_amount": 0, "trial_paid_by_parent": 0, "is_teacher_violated": False},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "refunded", "正常失败零退款不得置为已没收"

    records = (await db.execute(
        select(FinancialRecord).where(FinancialRecord.teacher_id == teacher.id)
    )).scalars().all()
    types = sorted(rec.type.value for rec in records)
    assert "forfeit" not in types, "正常失败不得产生没收流水（违约计数依据）"
    assert "refund_out" in types, "零退款也应留台账痕迹"

    # 教员违约计数口径：forfeit 流水数 → 应为 0
    from services.credit import teacher_credit_map
    credit = await teacher_credit_map(db, [teacher.id])
    assert credit.get(teacher.id, {}).get("violation_count", 0) == 0


async def test_teacher_violation_trial_failed_counts_violation(client, db):
    """教员违约的试课失败：没收流水 + 违约计数 +1（对照用例，保证口径没被改坏）。"""
    tenant, teacher, app = await _setup_app(db, "deposit_paid")

    r = await client.post(
        f"{BASE}/api/v1/applications/{app.id}/trial-failed",
        json={"refund_amount": 0, "trial_paid_by_parent": 0, "is_teacher_violated": True},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "forfeited"

    forfeits = (await db.execute(
        select(FinancialRecord).where(
            FinancialRecord.teacher_id == teacher.id,
            FinancialRecord.type == FinancialType.forfeit,
        )
    )).scalars().all()
    assert len(forfeits) == 1

    from services.credit import teacher_credit_map
    credit = await teacher_credit_map(db, [teacher.id])
    assert credit[teacher.id]["violation_count"] == 1
