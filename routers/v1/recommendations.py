"""
订单推荐路由：C 端教员按中介橱窗获取个性化订单推荐。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from middleware.auth import TokenPayload, require_role
from models.domain import Tenant
from models.schemas import TeacherOrderRecommendationResponse
from services.recommendation import build_teacher_recommendation_response

router = APIRouter(prefix="/api/v1/recommendations", tags=["订单推荐"])


@router.get("/{invite_code}", response_model=TeacherOrderRecommendationResponse)
async def get_recommendations(
    invite_code: str,
    limit: int = 12,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """教员端：按教员画像（距离/科目/年级/院校/课酬/历史）生成指定中介橱窗的订单推荐。"""
    if payload.teacher_id is None:
        raise HTTPException(status_code=401, detail="请先登录教员账号")

    result = await db.execute(select(Tenant).where(Tenant.invite_code == invite_code))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail="中介不存在或邀请码无效")

    return await build_teacher_recommendation_response(
        db=db,
        teacher_id=payload.teacher_id,
        tenant_id=tenant.id,
        tenant_name=tenant.tenant_name,
        invite_code=tenant.invite_code,
        limit=limit,
    )
