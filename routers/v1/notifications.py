"""
教员站内通知：投递流转结果（候选/定金/试课/成交/拒绝/处置）统一在此查看。
"""
import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import TokenPayload, require_role
from models.domain import Notification

router = APIRouter(prefix="/api/v1/notifications", tags=["通知"])


@router.get("/mine")
async def my_notifications(
    limit: int = 50,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """我的最近通知（含未读数）。"""
    limit = min(max(1, limit), 100)

    base = select(Notification).where(Notification.teacher_id == payload.teacher_id)
    items_result = await db.execute(
        base.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)
    )
    unread_result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.teacher_id == payload.teacher_id,
            Notification.read_at.is_(None),
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


@router.post("/read-all")
async def mark_all_read(
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """一键已读。"""
    now = datetime.datetime.utcnow()
    result = await db.execute(
        update(Notification)
        .where(
            Notification.teacher_id == payload.teacher_id,
            Notification.read_at.is_(None),
        )
        .values(read_at=now)
    )
    await db.flush()
    return {"marked": result.rowcount or 0}


@router.get("/tenant-mine")
async def tenant_notifications(
    limit: int = 50,
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端：租户通知（新投递、订单临期等）。超管可见全平台。"""
    limit = min(max(1, limit), 100)

    query = select(Notification).where(Notification.tenant_id.is_not(None))
    if payload.role != "super_admin":
        query = query.where(Notification.tenant_id == payload.tenant_id)
    items_result = await db.execute(
        query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)
    )
    unread_query = (
        select(func.count())
        .select_from(Notification)
        .where(Notification.tenant_id.is_not(None), Notification.read_at.is_(None))
    )
    if payload.role != "super_admin":
        unread_query = unread_query.where(Notification.tenant_id == payload.tenant_id)
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


@router.post("/tenant-read-all")
async def tenant_mark_all_read(
    payload: TokenPayload = Depends(require_role("tenant_admin", "super_admin")),
    db: AsyncSession = Depends(get_db),
):
    """B 端一键已读。"""
    now = datetime.datetime.utcnow()
    query = update(Notification).where(
        Notification.tenant_id.is_not(None),
        Notification.read_at.is_(None),
    )
    if payload.role != "super_admin":
        query = query.where(Notification.tenant_id == payload.tenant_id)
    result = await db.execute(query.values(read_at=now))
    await db.flush()
    return {"marked": result.rowcount or 0}
