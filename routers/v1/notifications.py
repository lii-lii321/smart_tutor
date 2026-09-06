"""
教员站内通知：投递流转结果（候选/定金/试课/成交/拒绝/处置）统一在此查看。
"""
import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.domain import Notification
from middleware.auth import TokenPayload, require_role

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
        select(Notification).where(
            Notification.teacher_id == payload.teacher_id,
            Notification.read_at.is_(None),
        )
    )
    count = 0
    for notification in result.scalars().all():
        notification.read_at = now
        count += 1
    await db.flush()
    return {"marked": count}
