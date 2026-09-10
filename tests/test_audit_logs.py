"""
资金操作审计日志回归（PLAN P2-6）：
- confirm_deposit / cancel 写路径落审计行（谁、角色、对象、IP）；
- 超管分页查询 + action 过滤；中介无权访问；非法 action 422。

运行方式：pytest tests/test_audit_logs.py
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
from sqlalchemy import select

BASE = "http://test"

# 注意：本文件按字母序最先被收集，禁止在模块级 import config 触碰链
# （models.domain / services.auth），否则 settings 单例会固化为 conftest 的
# OWNER_ACCESS_CODE，破坏存量测试各自声明的环境。相关 import 一律放函数内。


async def _setup(db) -> dict:
    from models.domain import TeacherResume

    tenant = await make_tenant(db, "audit001")
    teacher = await make_teacher(db, "audit_teacher")
    resume = TeacherResume(
        teacher_id=teacher.id, title="默认简历",
        teaching_subjects="数学", teaching_grades="初一-初三",
        experience="两年家教经验",
    )
    db.add(resume)
    order1 = await make_order(db, tenant.id, "AUDIT-001")
    order2 = await make_order(db, tenant.id, "AUDIT-002")
    await db.commit()
    return {
        "tenant_id": tenant.id, "teacher_id": teacher.id,
        "resume_id": resume.id, "order1_id": order1.id, "order2_id": order2.id,
    }


async def _apply(d, client, order_key: str = "order1_id") -> int:
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        params={"order_id": d[order_key], "resume_id": d["resume_id"]},
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def test_confirm_deposit_and_cancel_write_audit(client, db):
    d = await _setup(db)
    app_id = await _apply(d, client)

    # 中介确认定金 → confirm_deposit 审计
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/shortlist",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/confirm-deposit",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text

    from models.domain import AuditLog

    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "confirm_deposit")
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].actor_role == "tenant_admin"
    assert rows[0].actor_id == d["tenant_id"]
    assert rows[0].tenant_id == d["tenant_id"]
    assert rows[0].object_type == "application"
    assert rows[0].object_id == app_id

    # 教员取消（另一笔订单的投递，未付定金）→ cancel 审计
    app_id2 = await _apply(d, client, "order2_id")
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id2}/cancel",
        headers=auth_header(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 200, resp.text

    from models.domain import AuditLog

    rows = (await db.execute(
        select(AuditLog).where(AuditLog.action == "cancel")
    )).scalars().all()
    assert len(rows) == 1
    assert rows[0].actor_role == "teacher"
    assert rows[0].actor_id == d["teacher_id"]
    assert rows[0].tenant_id == d["tenant_id"]


async def test_super_admin_query_endpoint(client, db):
    d = await _setup(db)
    app_id = await _apply(d, client)
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/shortlist",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/confirm-deposit",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text

    from services.auth import create_jwt

    boss = create_jwt(sub="super_admin_1", role="super_admin")

    # 分页 + 总数
    resp = await client.get(
        f"{BASE}/api/v1/audit-logs",
        params={"page": 1, "page_size": 1},
        headers=auth_header(boss),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["action"] == "confirm_deposit"
    assert body["items"][0]["ip"], "ASGI 客户端应能取到请求地址"

    # action 过滤：无匹配时为空
    resp = await client.get(
        f"{BASE}/api/v1/audit-logs",
        params={"action": "forfeit"},
        headers=auth_header(boss),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0

    # 中介无权访问
    resp = await client.get(
        f"{BASE}/api/v1/audit-logs",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 403, f"中介查询审计应 403: {resp.status_code}"

    # 非法 action 422
    resp = await client.get(
        f"{BASE}/api/v1/audit-logs",
        params={"action": "not-a-action"},
        headers=auth_header(boss),
    )
    assert resp.status_code == 422


async def test_audit_created_at_utc_window(client, db):
    """日期过滤口径：今天写入的记录应落在 [today, tomorrow) 窗口内。"""
    d = await _setup(db)
    app_id = await _apply(d, client)
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/shortlist",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/confirm-deposit",
        headers=auth_header(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text

    from models.domain import AuditLog

    rows = (await db.execute(select(AuditLog))).scalars().all()
    assert len(rows) == 1
    now = datetime.datetime.utcnow()
    assert rows[0].created_at is not None
    assert abs((now - rows[0].created_at).total_seconds()) < 300, "created_at 应为库端当前 UTC 时间"


async def test_audit_failure_does_not_poison_session(db, monkeypatch):
    """审计写入失败必须被 SAVEPOINT 隔离：只回滚审计，业务会话保持可用。

    （直接 flush 失败会把 AsyncSession 置为 pending-rollback，调用方的下一次
    flush 连带 500 + 全量回滚——这正是 SAVEPOINT 要挡住的事故。）
    """
    from models.domain import AuditLog
    from services import audit as audit_mod

    real_audit = AuditLog

    class BrokenAuditFactory:
        # 返回 actor_role=None 的实体：savepoint flush 时触发 NOT NULL 约束
        def __call__(self, **kwargs):
            kwargs["actor_role"] = None
            return real_audit(**kwargs)

    monkeypatch.setattr(audit_mod, "AuditLog", BrokenAuditFactory())
    await audit_mod.record_audit(
        db, actor_role="tenant_admin", actor_id=1, action="confirm_deposit",
        object_id=999, tenant_id=1, request=None,
    )
    monkeypatch.undo()

    # 会话必须仍然可用：正常建数并提交
    tenant = await make_tenant(db, "savept01")
    await db.commit()
    assert tenant.id is not None

    rows = (await db.execute(select(AuditLog))).scalars().all()
    assert rows == [], "失败的审计行不得落库"

