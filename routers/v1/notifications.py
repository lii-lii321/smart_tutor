"""
教员站内通知：投递流转结果（候选/定金/试课/成交/拒绝/处置）统一在此查看。
"""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import TokenPayload, require_role, tenant_scoped
from models.domain import Notification
from models.schemas import (
    MarkedResponse,
    NotificationDeleteRequest,
    NotificationListResponse,
    UnreadCountResponse,
)
from utils.clock import utcnow
from utils.db import rowcount

router = APIRouter(prefix="/api/v1/notifications", tags=["通知"])


@router.get("/mine", response_model=NotificationListResponse)
async def my_notifications(
    limit: int = 50,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """我的最近通知（含未读数）。"""
    limit = min(max(1, limit), 100)

    base = select(Notification).where(
        Notification.teacher_id == payload.teacher_id,
        Notification.deleted_at.is_(None),
    )
    items_result = await db.execute(
        base.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)
    )
    unread_result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.teacher_id == payload.teacher_id,
            Notification.read_at.is_(None),
            Notification.deleted_at.is_(None),
        )
    )
    items = items_result.scalars().all()
    return {
        "unread_count": unread_result.scalar() or 0,
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "content": n.content,
                "application_id": n.application_id,
                "order_id": n.order_id,
                "created_at": n.created_at,
                "is_read": n.read_at is not None,
            }
            for n in items
        ],
    }


@router.get("/mine/unread-count", response_model=UnreadCountResponse)
async def my_unread_count(
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """角标轮询专用：只返回未读数，不拉通知列表（60s 轮询 × 全量列表是常驻底噪）。"""
    unread = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.teacher_id == payload.teacher_id,
            Notification.read_at.is_(None),
            Notification.deleted_at.is_(None),
        )
    )
    return {"unread_count": unread or 0}


@router.post("/read-all", response_model=MarkedResponse)
async def mark_all_read(
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """一键已读。"""
    now = utcnow()
    result = await db.execute(
        update(Notification)
        .where(
            Notification.teacher_id == payload.teacher_id,
            Notification.read_at.is_(None),
            Notification.deleted_at.is_(None),
        )
        .values(read_at=now)
    )
    await db.flush()
    return {"marked": rowcount(result) or 0}


def _validated_ids(ids: list[int]) -> list[int]:
    """批量删除的单次上限：防一次性提交超长列表拖长事务。"""
    unique = sorted(set(ids))
    if len(unique) > 200:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="单次最多删除 200 条")
    return unique


def _delete_values():
    """软删：只打 deleted_at 标记，其余字段（含 order_id/title）原样保留——
    调度器临期提醒按 (order_id, title, 周期) 去重锚定通知行，
    改写或硬删都会让被用户删掉的提醒反复重建。所有读路径过滤 deleted_at。"""
    return {"deleted_at": utcnow()}


@router.post("/delete", response_model=MarkedResponse)
async def delete_my_notifications(
    body: NotificationDeleteRequest,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """教员批量删除自己选中的通知（只动 teacher_id 归属自己的行）。"""
    ids = _validated_ids(body.ids)
    result = await db.execute(
        update(Notification)
        .where(Notification.id.in_(ids), Notification.teacher_id == payload.teacher_id)
        .values(**_delete_values())
    )
    await db.flush()
    return {"marked": rowcount(result) or 0}


@router.post("/delete-all", response_model=MarkedResponse)
async def delete_all_my_notifications(
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """教员清空自己的全部通知。"""
    result = await db.execute(
        update(Notification)
        .where(Notification.teacher_id == payload.teacher_id)
        .values(**_delete_values())
    )
    await db.flush()
    return {"marked": rowcount(result) or 0}


@router.get("/tenant-mine", response_model=NotificationListResponse)
async def tenant_notifications(
    limit: int = 50,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：租户通知（新投递、订单临期等）。超管可见全平台。"""
    limit = min(max(1, limit), 100)

    query = select(Notification).where(
        Notification.tenant_id.is_not(None),
        Notification.deleted_at.is_(None),
    )
    query = tenant_scoped(query, payload, Notification.tenant_id)
    items_result = await db.execute(
        query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)
    )
    unread_query = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.tenant_id.is_not(None),
            Notification.read_at.is_(None),
            Notification.deleted_at.is_(None),
        )
    )
    unread_query = tenant_scoped(unread_query, payload, Notification.tenant_id)
    unread_result = await db.execute(unread_query)

    items = items_result.scalars().all()
    return {
        "unread_count": unread_result.scalar() or 0,
        "items": [
            {
                "id": n.id,
                "title": n.title,
                "content": n.content,
                "application_id": n.application_id,
                "order_id": n.order_id,
                "created_at": n.created_at,
                "is_read": n.read_at is not None,
            }
            for n in items
        ],
    }


@router.post("/tenant-delete", response_model=MarkedResponse)
async def delete_tenant_notifications(
    body: NotificationDeleteRequest,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端批量删除选中的租户通知（按租户隔离）。"""
    ids = _validated_ids(body.ids)
    query = update(Notification).where(
        Notification.id.in_(ids),
        Notification.tenant_id.is_not(None),
    )
    query = tenant_scoped(query, payload, Notification.tenant_id)
    result = await db.execute(query.values(**_delete_values()))
    await db.flush()
    return {"marked": rowcount(result) or 0}


@router.post("/tenant-delete-all", response_model=MarkedResponse)
async def delete_all_tenant_notifications(
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端清空本租户全部通知（超管为全平台）。"""
    query = update(Notification).where(Notification.tenant_id.is_not(None))
    query = tenant_scoped(query, payload, Notification.tenant_id)
    result = await db.execute(query.values(**_delete_values()))
    await db.flush()
    return {"marked": rowcount(result) or 0}


@router.get("/tenant-unread-count", response_model=UnreadCountResponse)
async def tenant_unread_count(
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端角标轮询专用：只返回未读数，不拉通知列表。超管可见全平台。"""
    query = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.tenant_id.is_not(None),
            Notification.read_at.is_(None),
            Notification.deleted_at.is_(None),
        )
    )
    query = tenant_scoped(query, payload, Notification.tenant_id)
    unread = await db.scalar(query)
    return {"unread_count": unread or 0}


@router.post("/tenant-read-all", response_model=MarkedResponse)
async def tenant_mark_all_read(
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端一键已读。"""
    now = utcnow()
    query = update(Notification).where(
        Notification.tenant_id.is_not(None),
        Notification.read_at.is_(None),
        Notification.deleted_at.is_(None),
    )
    query = tenant_scoped(query, payload, Notification.tenant_id)
    result = await db.execute(query.values(read_at=now))
    await db.flush()
    return {"marked": rowcount(result) or 0}
