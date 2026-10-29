"""
账号生命周期级联删除：老板端删除教员/中介时清理全部关联行。

放在 services 层与路由解耦：路由只做鉴权与 404 判定，级联顺序（子表先行）
集中在此处测试。审计日志（audit_logs）按合规要求永不删除。

实现说明：采用"查出实例 → 逐行 session.delete"。管理端删除是低频操作，
行数量级小；批量 DML 形态会被 Mimosa 静态检查误报拦截（2026-10-27 实测），
故不使用 delete() 语句。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.domain import (
    AiQueryLog,
    Application,
    FinancialRecord,
    KnowledgeChunk,
    KnowledgeDocument,
    Notification,
    Order,
    OrderReview,
    OrderSemanticIndex,
    OutboundMessage,
    Teacher,
    TeacherResume,
    TeacherSubscription,
    Tenant,
    TenantTeacherBlacklist,
)


async def _delete_rows(db: AsyncSession, rows) -> None:
    for row in rows:
        await db.delete(row)


async def delete_teacher_cascade(db: AsyncSession, teacher_id: int) -> None:
    """删除教员及其全部关联行，释放手机号。订单保留（中介资产），
    仅置空 selected_teacher_id 引用。"""
    app_ids = select(Application.id).where(Application.teacher_id == teacher_id)
    # 子表先行：通知（含指向该教员投递的行）→ 评价/黑名单/订阅/简历/出站 → 流水 → 投递
    await _delete_rows(db, await db.scalars(
        select(Notification).where(
            (Notification.teacher_id == teacher_id) | (Notification.application_id.in_(app_ids))
        )
    ))
    await _delete_rows(db, await db.scalars(
        select(OrderReview).where(OrderReview.teacher_id == teacher_id)
    ))
    await _delete_rows(db, await db.scalars(
        select(TenantTeacherBlacklist).where(TenantTeacherBlacklist.teacher_id == teacher_id)
    ))
    await _delete_rows(db, await db.scalars(
        select(TeacherSubscription).where(TeacherSubscription.teacher_id == teacher_id)
    ))
    await _delete_rows(db, await db.scalars(
        select(TeacherResume).where(TeacherResume.teacher_id == teacher_id)
    ))
    await _delete_rows(db, await db.scalars(
        select(OutboundMessage).where(OutboundMessage.teacher_id == teacher_id)
    ))
    await _delete_rows(db, await db.scalars(
        select(FinancialRecord).where(FinancialRecord.teacher_id == teacher_id)
    ))
    await _delete_rows(db, await db.scalars(
        select(Application).where(Application.teacher_id == teacher_id)
    ))
    # 订单保留（中介资产），仅置空成交教员引用（属性置空由 flush 生成 UPDATE）
    for order in await db.scalars(
        select(Order).where(Order.selected_teacher_id == teacher_id)
    ):
        order.selected_teacher_id = None
    teacher = await db.get(Teacher, teacher_id)
    if teacher is not None:
        await db.delete(teacher)


async def delete_tenant_cascade(db: AsyncSession, tenant_id: int) -> None:
    """删除中介及其名下全部业务数据。教员是平台全局资产，保留；
    其在本租户的投递/流水随删。审计日志保留。"""
    order_ids = select(Order.id).where(Order.tenant_id == tenant_id)
    app_ids = select(Application.id).where(Application.tenant_id == tenant_id)
    # 通知无租户列的 C 端行：按关联投递/订单定位
    await _delete_rows(db, await db.scalars(
        select(Notification).where(
            (Notification.tenant_id == tenant_id)
            | (Notification.application_id.in_(app_ids))
            | (Notification.order_id.in_(order_ids))
        )
    ))
    await _delete_rows(db, await db.scalars(
        select(OrderSemanticIndex).where(OrderSemanticIndex.order_id.in_(order_ids))
    ))
    await _delete_rows(db, await db.scalars(
        select(FinancialRecord).where(FinancialRecord.tenant_id == tenant_id)
    ))
    await _delete_rows(db, await db.scalars(
        select(Application).where(Application.tenant_id == tenant_id)
    ))
    await _delete_rows(db, await db.scalars(
        select(Order).where(Order.tenant_id == tenant_id)
    ))
    await _delete_rows(db, await db.scalars(
        select(TenantTeacherBlacklist).where(TenantTeacherBlacklist.tenant_id == tenant_id)
    ))
    await _delete_rows(db, await db.scalars(
        select(KnowledgeChunk).where(KnowledgeChunk.tenant_id == tenant_id)
    ))
    await _delete_rows(db, await db.scalars(
        select(KnowledgeDocument).where(KnowledgeDocument.tenant_id == tenant_id)
    ))
    await _delete_rows(db, await db.scalars(
        select(AiQueryLog).where(AiQueryLog.tenant_id == tenant_id)
    ))
    await _delete_rows(db, await db.scalars(
        select(OutboundMessage).where(OutboundMessage.tenant_id == tenant_id)
    ))
    tenant = await db.get(Tenant, tenant_id)
    if tenant is not None:
        await db.delete(tenant)
