"""
教员自助注销回归测试（合规：个人信息删除权，P2-7）。

口径锁定：
- 密码确认身份；错误密码 400；
- PII 匿名化：姓名呈"已注销用户"，手机号/openid/微信以 deleted-* 占位，
  可空字段（专业/年级/亮点/常驻地/坐标）清空，原手机号释放可重新注册；
- 简历删除；投递与财务流水保留（对账红线）；
- 账号封禁：旧 token 立即失效、不可再登录、不可再投递；
- 中介/超管角色不可调用。

运行方式：
    pytest tests/test_deactivate.py
"""

from conftest import (
    auth_header,
    make_order,
    make_teacher,
    make_tenant,
    teacher_token,
    tenant_token,
)
from sqlalchemy import select

from models.domain import (
    Application,
    ApplicationStatus,
    FinancialRecord,
    FinancialType,
    TeacherResume,
)

BASE = "http://test"


async def _setup_registered_teacher(db, invite: str, phone: str, openid: str):
    """走真实注册流程的教员（有密码哈希），带简历。"""
    from services.auth import hash_password_async

    tenant = await make_tenant(db, invite)
    teacher = await make_teacher(db, openid, phone=phone)
    teacher.password_hash = await hash_password_async("pass1234")
    teacher.home_area = "成都·武侯区"
    resume = TeacherResume(
        teacher_id=teacher.id, title="个人简历",
        teaching_subjects="数学", teaching_grades="初一-初三", experience="个人经历内容",
    )
    db.add(resume)
    await db.commit()
    return tenant, teacher, resume


async def test_deactivate_anonymizes_and_blocks(client, db):
    tenant, teacher, resume = await _setup_registered_teacher(db, "dea001a", "13855550001", "dea_openid_1")
    headers = auth_header(teacher_token(teacher.id))

    # 错误密码拒绝
    resp = await client.post(
        f"{BASE}/api/v1/auth/teacher/deactivate",
        json={"password": "wrong-pass"},
        headers=headers,
    )
    assert resp.status_code == 400

    # 正确密码注销
    resp = await client.post(
        f"{BASE}/api/v1/auth/teacher/deactivate",
        json={"password": "pass1234"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    # 端点会话已提交；本会话 identity map 缓存旧对象——直接查列绕过缓存
    row = (await db.execute(
        select(TeacherResume)
    )).scalar_one_or_none()
    from models.domain import Teacher
    t = (await db.execute(
        select(
            Teacher.name, Teacher.phone, Teacher.openid,
            Teacher.home_area, Teacher.highlights,
            Teacher.password_hash, Teacher.is_banned,
        ).where(Teacher.id == teacher.id)
    )).one()
    assert t.name == "已注销用户"
    assert t.phone.startswith("del-") and phone_freed(t.phone, "13855550001")
    assert t.openid.startswith("deleted-")
    assert t.home_area is None and t.highlights is None
    assert t.password_hash is None
    assert t.is_banned is True
    # 简历已删除
    assert row is None

    # 旧 token 立即失效
    resp = await client.get(f"{BASE}/api/v1/auth/me", headers=headers)
    assert resp.status_code == 401

    # 手机号+密码登录不可再进入（账号已无密码）
    resp = await client.post(
        f"{BASE}/api/v1/auth/teacher-phone-login",
        json={"phone": "13855550001", "invite_code": tenant.invite_code, "password": "pass1234"},
    )
    assert resp.status_code in (400, 404)

    # 原手机号可重新注册（唯一约束已释放）
    resp = await client.post(
        f"{BASE}/api/v1/auth/teacher-phone-register",
        json={"phone": "13855550001", "invite_code": tenant.invite_code, "password": "newpass1a",
              "name": "新教员", "gender": "female", "wechat_id": "wx_new", "school": "新大学"},
    )
    assert resp.status_code == 200, resp.text


def phone_freed(anonymized: str, original: str) -> bool:
    return original not in anonymized


async def test_deactivate_keeps_money_trail_and_blocks_apply(client, db):
    tenant = await make_tenant(db, "dea002a")
    teacher = await make_teacher(db, "dea_openid_2", phone="13855550002")
    from services.auth import hash_password_async
    teacher.password_hash = await hash_password_async("pass1234")
    resume = TeacherResume(
        teacher_id=teacher.id, title="默认简历",
        teaching_subjects="数学", teaching_grades="初一-初三", experience="经验",
    )
    db.add(resume)
    order = await make_order(db, tenant.id, "DEA-001")
    await db.flush()
    # 历史投递 + 财务流水（对账红线：注销后必须保留）
    application = Application(
        order_id=order.id, teacher_id=teacher.id, tenant_id=tenant.id,
        status=ApplicationStatus.completed, fee_total=200, fee_deposit=100, fee_balance=100,
    )
    db.add(application)
    db.add(FinancialRecord(
        order_id=order.id, tenant_id=tenant.id, teacher_id=teacher.id,
        amount=100, type=FinancialType.deposit_in, remark="历史定金",
    ))
    await db.commit()
    headers = auth_header(teacher_token(teacher.id))

    resp = await client.post(
        f"{BASE}/api/v1/auth/teacher/deactivate",
        json={"password": "pass1234"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    await db.commit()
    app_row = (await db.execute(select(Application))).scalar_one()
    assert app_row.status == ApplicationStatus.completed, "历史投递保留"
    fin_rows = (await db.execute(select(FinancialRecord))).scalars().all()
    assert len(fin_rows) == 1 and float(fin_rows[0].amount) == 100.0, "财务流水保留"

    # 注销后的账号不可再投递：旧 token 已吊销（401）；即使带新凭证，封禁也拦（403）
    order2 = await make_order(db, tenant.id, "DEA-002")
    await db.commit()
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        json={"order_id": order2.id, "resume_id": resume.id},
        headers=auth_header(teacher_token(teacher.id)),
    )
    assert resp.status_code in (401, 403)

    # 已失效 token 的历史投递详情仍可由中介侧正常读取（教员名呈"已注销用户"）
    resp = await client.get(
        f"{BASE}/api/v1/applications/order/{order.id}",
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()[0]["teacher"]["name"] == "已注销用户"


async def test_deactivate_rejects_non_teacher(client, db):
    from conftest import tenant_token as tt
    tenant = await make_tenant(db, "dea003a")
    await db.commit()

    resp = await client.post(
        f"{BASE}/api/v1/auth/teacher/deactivate",
        json={"password": "x"},
        headers=auth_header(tt(tenant.id)),
    )
    assert resp.status_code == 403

    # 未认证
    resp = await client.post(
        f"{BASE}/api/v1/auth/teacher/deactivate",
        json={"password": "x"},
    )
    assert resp.status_code in (401, 403)
