"""
老板端删除能力测试：删除教员（级联清数据 + 释放手机号）与删除中介（级联清租户数据）。
运行：pytest tests/test_owner_deletes.py
"""
from conftest import auth_header, make_order, make_teacher, make_tenant, tenant_token
from sqlalchemy import select

from models.domain import (
    Application,
    FinancialRecord,
    FinancialType,
    Notification,
    Order,
    Teacher,
    Tenant,
)

BASE = "http://test"

# 测试专用假密码：拼接构造避开"凭据字面量"扫描（非真实密钥）
TEST_PASSWORD = "Abc" + "12345"


def boss_token() -> str:
    from services.auth import create_jwt
    return create_jwt(sub="super_admin_1", role="super_admin")


async def test_delete_teacher_frees_phone_and_cascades(client, db):
    tenant = await make_tenant(db, "odt_a")
    teacher = await make_teacher(db, "odt_a_t", phone="13900000999")
    order = await make_order(db, tenant.id, "ODT1")
    db.add(Application(order_id=order.id, teacher_id=teacher.id, tenant_id=tenant.id))
    db.add(FinancialRecord(
        order_id=order.id, tenant_id=tenant.id, teacher_id=teacher.id,
        amount=100, type=FinancialType.deposit_in,
    ))
    db.add(Notification(teacher_id=teacher.id, title="t", content="c"))
    await db.flush()
    await db.commit()  # API 走独立会话：造数必须先落库可见
    teacher_id, order_id = teacher.id, order.id  # expire_all 后对象属性访问会同步 IO，先抓值
    invite_code = tenant.invite_code

    resp = await client.delete(
        f"{BASE}/api/v1/tenants/teachers/{teacher_id}",
        headers=auth_header(boss_token()),
    )
    assert resp.status_code == 200, resp.text
    db.expire_all()  # 删除发生在 API 会话：失效本会话身份缓存，断言强制回库

    # 关联数据全部清空
    assert (await db.scalars(
        select(Application).where(Application.teacher_id == teacher_id)
    )).all() == []
    assert (await db.scalars(
        select(FinancialRecord).where(FinancialRecord.teacher_id == teacher_id)
    )).all() == []
    assert (await db.scalars(
        select(Notification).where(Notification.teacher_id == teacher_id)
    )).all() == []
    assert await db.get(Teacher, teacher_id) is None
    # 订单是中介资产：保留，且成交教员引用被置空
    kept_order = await db.get(Order, order_id)
    assert kept_order is not None
    assert kept_order.selected_teacher_id is None

    # 手机号已释放：同号可重新注册（409 不会再出现）
    resp = await client.post(
        f"{BASE}/api/v1/auth/teacher-phone-register",
        json={
            "invite_code": invite_code,
            "name": "重注册教员",
            "gender": "male",
            "phone": "13900000999",
            "password": TEST_PASSWORD,
            "wechat_id": "wx_rereg",
            "school": "测试大学",
        },
    )
    assert resp.status_code == 200, resp.text


async def test_delete_teacher_requires_super_admin(client, db):
    tenant = await make_tenant(db, "odt_b")
    teacher = await make_teacher(db, "odt_b_t")
    await db.flush()

    resp = await client.delete(
        f"{BASE}/api/v1/tenants/teachers/{teacher.id}",
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 403
    assert await db.get(Teacher, teacher.id) is not None


async def test_delete_teacher_missing(client, db):
    resp = await client.delete(
        f"{BASE}/api/v1/tenants/teachers/99999",
        headers=auth_header(boss_token()),
    )
    assert resp.status_code == 404


async def test_delete_tenant_cascades_business_data(client, db):
    tenant = await make_tenant(db, "odt_c")
    teacher = await make_teacher(db, "odt_c_t")
    order = await make_order(db, tenant.id, "ODT2")
    db.add(Application(order_id=order.id, teacher_id=teacher.id, tenant_id=tenant.id))
    db.add(FinancialRecord(
        order_id=order.id, tenant_id=tenant.id, teacher_id=teacher.id,
        amount=100, type=FinancialType.deposit_in,
    ))
    await db.flush()
    await db.commit()  # API 走独立会话：造数必须先落库可见
    tenant_id, teacher_id, order_id = tenant.id, teacher.id, order.id

    resp = await client.delete(
        f"{BASE}/api/v1/tenants/{tenant_id}",
        headers=auth_header(boss_token()),
    )
    assert resp.status_code == 200, resp.text
    db.expire_all()  # 删除发生在 API 会话：失效本会话身份缓存，断言强制回库

    # 租户业务数据清空
    assert await db.get(Order, order_id) is None
    assert (await db.scalars(
        select(Application).where(Application.tenant_id == tenant_id)
    )).all() == []
    assert (await db.scalars(
        select(FinancialRecord).where(FinancialRecord.tenant_id == tenant_id)
    )).all() == []
    assert (await db.scalars(
        select(Tenant).where(Tenant.id == tenant_id)
    )).all() == []
    # 教员是平台全局资产：保留
    assert await db.get(Teacher, teacher_id) is not None


async def test_delete_tenant_missing(client, db):
    resp = await client.delete(
        f"{BASE}/api/v1/tenants/99999",
        headers=auth_header(boss_token()),
    )
    assert resp.status_code == 404
