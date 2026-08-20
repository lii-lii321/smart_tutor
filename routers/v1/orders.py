"""
订单路由：B 端批量解析/导入 + 状态流转 + 地址解锁。
"""
import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from database import get_db
from models.domain import Order, OrderStatus, Application, ApplicationStatus
from models.schemas import (
    BatchParseRequest, BatchParseResponse, BatchImportRequest, BatchImportResponse,
    TransitRequest, TransitResponse, AddressUnlockResponse, OrderDetailResponse,
    OrderUpdateRequest,
)
from services.parser import parse_wechat_batch
from services.geo import batch_sync_to_redis, remove_from_redis
from services.calculator import calculate_info_fee
from services.order_maintenance import archive_expired_recruiting_orders, get_redis_client
from middleware.auth import TokenPayload, get_current_user, require_role, require_tenant_owner
from utils.state_machine import validate_transition
from config import settings

router = APIRouter(prefix="/api/v1/orders", tags=["订单"])


def _build_order_detail(order: Order) -> OrderDetailResponse:
    return OrderDetailResponse.model_validate(
        {
            "id": order.id,
            "raw_id": order.raw_id,
            "raw_text": order.raw_text,
            "grade_subject": order.grade_subject,
            "requirements": order.requirements,
            "price_total": order.price_total,
            "base_price": float(order.base_price),
            "weekly_frequency": order.weekly_frequency,
            "is_summer_vacation": order.is_summer_vacation,
            "fuzzy_address": order.fuzzy_address,
            "subway_remark": order.subway_remark,
            "lng": float(order.lng),
            "lat": float(order.lat),
            "calculated_info_fee": float(order.calculated_info_fee),
            "deposit_amount": float(order.deposit_amount),
            "balance_amount": float(order.balance_amount),
            "needs_manual_price": float(order.base_price) <= 0,
            "status": order.status,
            "created_at": order.created_at,
            "expired_at": order.expired_at,
        }
    )


async def _get_managed_order(
    order_id: int,
    payload: TokenPayload,
    db: AsyncSession,
) -> Order:
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    if payload.role != "super_admin" and order.tenant_id != payload.tenant_id:
        raise HTTPException(status_code=404, detail="订单不存在")
    return order


async def _sync_order_geo(order: Order) -> None:
    redis = None
    try:
        redis = await get_redis_client()
        if order.status == OrderStatus.recruiting:
            await batch_sync_to_redis([order], redis)
        else:
            await remove_from_redis(order.tenant_id, order.id, redis)
    except Exception:
        pass
    finally:
        if redis is not None:
            await redis.aclose()


async def _reset_applications_for_republish(
    db: AsyncSession,
    order_id: int,
) -> None:
    result = await db.execute(
        select(Application).where(Application.order_id == order_id)
    )
    applications = result.scalars().all()
    now = datetime.datetime.utcnow()
    for application in applications:
        if application.status in (
            ApplicationStatus.shortlisted,
            ApplicationStatus.deposit_paid,
            ApplicationStatus.trial_in_progress,
            ApplicationStatus.balance_paid,
        ):
            application.status = ApplicationStatus.rejected
            application.rejected_at = now
        if application.status == ApplicationStatus.refunded:
            application.rejected_at = application.rejected_at or now


# ── B 端接口 ──

@router.post("/batch-parse", response_model=BatchParseResponse)
async def batch_parse(
    body: BatchParseRequest,
    payload: TokenPayload = Depends(require_tenant_owner()),
):
    """
    接收微信文本 → DeepSeek 解析 → 高德编码 → 精算 → 返回预览。
    B 端中介专属。
    """
    try:
        items = await parse_wechat_batch(body.raw_text)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500,
            detail=f"AI 解析服务异常（已重试3次）：{str(e)}。TRACEBACK: {tb[-500:]}",
        )
    return BatchParseResponse(items=items, count=len(items))


@router.post("/batch-import", response_model=BatchImportResponse)
async def batch_import(
    body: BatchImportRequest,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """
    前端勾选确认的订单数组 → 批量入库 → 同步 Redis GEO。
    B 端中介专属。
    """
    now = datetime.datetime.utcnow()
    expire_at = now + datetime.timedelta(hours=settings.ORDER_EXPIRE_HOURS)

    orders = []
    for item in body.items:
        order = Order(
            tenant_id=payload.tenant_id,
            raw_id=item.raw_id,
            raw_text=item.raw_text,
            grade_subject=item.grade_subject,
            requirements=item.requirements,
            price_total=item.price_total,
            base_price=item.base_price,
            weekly_frequency=item.weekly_frequency,
            is_summer_vacation=item.is_summer_vacation,
            exact_address=item.exact_address,
            parent_phone=item.parent_phone,
            fuzzy_address=item.fuzzy_address,
            subway_remark=item.subway_remark,
            lng=item.lng,
            lat=item.lat,
            calculated_info_fee=item.calculated_info_fee,
            deposit_amount=item.deposit_amount,
            balance_amount=item.balance_amount,
            status=OrderStatus.recruiting,
            expired_at=expire_at,
        )
        db.add(order)
        orders.append(order)

    await db.flush()  # 获取 ID

    # 异步写入 Redis GEO
    try:
        redis = await get_redis_client()
        await batch_sync_to_redis(orders, redis)
        await redis.aclose()
    except Exception:
        pass  # Redis 不可用时降级，MySQL 仍可正常工作

    return BatchImportResponse(imported=len(orders))


# ── 状态流转（B 端 + C 端） ──

@router.post("/{order_id}/transit", response_model=TransitResponse)
async def transit_status(
    order_id: int,
    body: TransitRequest,
    payload: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """订单状态流转。角色不同可触发的目标状态不同。"""
    result = await db.execute(select(Order).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 租户隔离：非超管只能操作自己租户的订单
    if payload.role != "super_admin" and order.tenant_id != payload.tenant_id:
        raise HTTPException(status_code=404, detail="订单不存在")

    previous_status = order.status

    try:
        validate_transition(order.status, body.target_status, payload.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    order.status = body.target_status

    # 状态流转时的副操作
    if body.target_status == OrderStatus.archived:
        try:
            redis = await get_redis_client()
            await remove_from_redis(order.tenant_id, order.id, redis)
            await redis.aclose()
        except Exception:
            pass

    return TransitResponse(
        order_id=order_id,
        previous_status=previous_status,
        current_status=order.status,
    )


# ── C 端 / B 端：地址解锁（卡点接口） ──

@router.get("/{order_id}/address-unlock", response_model=AddressUnlockResponse)
async def address_unlock(
    order_id: int,
    payload: TokenPayload = Depends(require_role("teacher")),
    db: AsyncSession = Depends(get_db),
):
    """
    获取家长真实地址与电话。
    仅正在试课或已补齐尾款的教员可解锁。
    """
    result = await db.execute(
        select(Application).where(
            Application.order_id == order_id,
            Application.teacher_id == payload.teacher_id,
        )
    )
    application = result.scalar_one_or_none()

    if not application or application.status not in (
        ApplicationStatus.trial_in_progress,
        ApplicationStatus.balance_paid,
    ):
        raise HTTPException(
            status_code=403,
            detail="当前还未轮到你试课，暂不能查看家长真实电话与门牌号。",
        )

    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    return AddressUnlockResponse(
        exact_address=order.exact_address,
        parent_phone=order.parent_phone,
    )


# ── 查询接口 ──

@router.get("/")
async def list_orders(
    status: OrderStatus | None = None,
    page: int = 1,
    page_size: int = 20,
    payload: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """分页查询订单列表。B 端看自己的，C 端看所有 recruiting。"""
    if payload.role in ("tenant_admin", "super_admin"):
        await archive_expired_recruiting_orders(
            db,
            tenant_id=payload.tenant_id if payload.role != "super_admin" else None,
        )

    query = select(Order)

    if payload.role in ("tenant_admin", "super_admin") and payload.tenant_id:
        query = query.where(Order.tenant_id == payload.tenant_id)
    elif payload.role == "teacher":
        query = query.where(Order.status == OrderStatus.recruiting)

    if status:
        query = query.where(Order.status == status)

    query = query.order_by(Order.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    orders = result.scalars().all()

    return {
        "items": [
            {
                "id": o.id,
                "raw_id": o.raw_id,
                "grade_subject": o.grade_subject,
                "price_total": o.price_total,
                "base_price": float(o.base_price),
                "fuzzy_address": o.fuzzy_address,
                "status": o.status.value,
                "needs_manual_price": float(o.base_price) <= 0,
                "calculated_info_fee": float(o.calculated_info_fee),
                "deposit_amount": float(o.deposit_amount),
                "balance_amount": float(o.balance_amount),
                "weekly_frequency": o.weekly_frequency,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "expired_at": o.expired_at.isoformat() if o.expired_at else None,
            }
            for o in orders
        ],
        "page": page,
        "page_size": page_size,
    }


@router.get("/{order_id}", response_model=OrderDetailResponse)
async def get_order_detail(
    order_id: int,
    payload: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查看订单详情。教员可看招募中的脱敏完整信息，B 端看自己租户订单。"""
    order = await db.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    if payload.role in ("tenant_admin", "super_admin"):
        if payload.role != "super_admin" and order.tenant_id != payload.tenant_id:
            raise HTTPException(status_code=404, detail="订单不存在")
    elif payload.role == "teacher":
        if order.status != OrderStatus.recruiting:
            result = await db.execute(
                select(Application).where(
                    Application.order_id == order_id,
                    Application.teacher_id == payload.teacher_id,
                )
            )
            if not result.scalar_one_or_none():
                raise HTTPException(status_code=404, detail="订单不存在")
    else:
        raise HTTPException(status_code=403, detail="无权查看订单")

    return _build_order_detail(order)


@router.patch("/{order_id}", response_model=OrderDetailResponse)
async def update_order(
    order_id: int,
    body: OrderUpdateRequest,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """B 端：编辑订单基础信息、价格、地址和有效期。"""
    order = await _get_managed_order(order_id, payload, db)
    data = body.model_dump(exclude_unset=True)

    recalculation_fields = {"base_price", "weekly_frequency", "is_summer_vacation"}
    should_recalculate = bool(recalculation_fields & data.keys())

    for field, value in data.items():
        setattr(order, field, value)

    if should_recalculate and float(order.base_price) > 0:
        try:
            fee = calculate_info_fee(
                base_price=float(order.base_price),
                weekly_frequency=order.weekly_frequency,
                is_summer_vacation=order.is_summer_vacation,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        order.calculated_info_fee = fee["total_info_fee"]
        order.deposit_amount = fee["deposit"]
        order.balance_amount = fee["balance"]

    await db.flush()
    await _sync_order_geo(order)
    return _build_order_detail(order)


@router.post("/{order_id}/archive", response_model=OrderDetailResponse)
async def archive_order(
    order_id: int,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """B 端：手动下架订单。"""
    order = await _get_managed_order(order_id, payload, db)
    order.status = OrderStatus.archived
    await db.flush()
    await _sync_order_geo(order)
    return _build_order_detail(order)


@router.post("/{order_id}/republish", response_model=OrderDetailResponse)
async def republish_order(
    order_id: int,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """B 端：重新发布订单，并刷新有效期。"""
    order = await _get_managed_order(order_id, payload, db)
    if order.status in (OrderStatus.trial_in_progress, OrderStatus.completed):
        raise HTTPException(status_code=400, detail="试课中或已完成订单不能直接重新发布")

    await _reset_applications_for_republish(db, order.id)
    order.status = OrderStatus.recruiting
    order.selected_teacher_id = None
    order.expired_at = datetime.datetime.utcnow() + datetime.timedelta(
        hours=settings.ORDER_EXPIRE_HOURS
    )
    await db.flush()
    await _sync_order_geo(order)
    return _build_order_detail(order)


@router.post("/expire-stale")
async def expire_stale_orders(
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """
    B 端手动整理过期招聘单。
    当前策略：超过有效期且仍在招聘中的订单自动归档，已排队/试课中的订单不动。
    """
    archived = await archive_expired_recruiting_orders(
        db,
        tenant_id=payload.tenant_id if payload.role != "super_admin" else None,
    )
    return {"archived": archived}
