"""
订单路由：B 端批量解析/导入 + 状态流转 + 地址解锁。
"""
import csv
import datetime
import io
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import get_db
from middleware.auth import (
    TokenPayload,
    assert_tenant_scope,
    get_current_user,
    require_role,
    require_tenant_owner,
)
from middleware.rate_limit import check_parse_rate_limit
from models.domain import Application, ApplicationStatus, Notification, Order, OrderStatus
from models.schemas import (
    AddressUnlockResponse,
    BatchImportRequest,
    BatchImportResponse,
    BatchParseRequest,
    BatchParseResponse,
    BatchStatusUpdateRequest,
    BatchStatusUpdateResponse,
    OrderDetailResponse,
    OrderListResponse,
    OrderUpdateRequest,
    TransitRequest,
    TransitResponse,
)
from services import serializers
from services.calculator import calculate_info_fee
from services.geo import batch_sync_to_redis, remove_from_redis
from services.order_maintenance import (
    get_redis_client,
    invalidate_board_cache,
    refresh_order_expiry,
)
from services.parser import parse_wechat_batch
from utils.state_machine import validate_transition

router = APIRouter(prefix="/api/v1/orders", tags=["订单"])

logger = logging.getLogger(__name__)


def _build_order_detail(order: Order, include_sensitive: bool = True) -> OrderDetailResponse:
    """字段映射单点在 services/serializers.py，此处仅做 schema 包装。"""
    return OrderDetailResponse.model_validate(
        serializers.order_detail_payload(order, include_sensitive=include_sensitive)
    )


async def _get_managed_order(
    order_id: int,
    payload: TokenPayload,
    db: AsyncSession,
) -> Order:
    # 写路径一律锁行：与投递侧资金操作互斥，避免守卫检查与状态写入之间被并发穿透
    result = await db.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")
    assert_tenant_scope(payload, order.tenant_id, detail="订单不存在")
    return order


def _refresh_order_expiry(order: Order, now: datetime.datetime) -> None:
    """重开招聘统一的有效期策略：从现在起重新计时（含周期标记，见 order_maintenance）。"""
    refresh_order_expiry(order, now)


async def _sync_order_geo(order: Order) -> None:
    try:
        redis = await get_redis_client()
        if order.status == OrderStatus.recruiting:
            await batch_sync_to_redis([order], redis)
        else:
            await remove_from_redis(order.tenant_id, order.id, redis)
    except Exception:
        pass  # Redis 不可用时降级；客户端为单例，连接由池管理
    finally:
        # 订单字段/状态变更影响橱窗 30s 缓存（update/archive/republish/batch-status 共用此钩子）
        await invalidate_board_cache(order.tenant_id)


_PAID_TRIAL_APPLICATION_STATUSES = (
    ApplicationStatus.deposit_paid,
    ApplicationStatus.trial_in_progress,
    ApplicationStatus.balance_paid,
)


async def _ensure_reopenable(db: AsyncSession, order_ids: list[int]) -> None:
    """
    重新开放订单前的资金守卫：存在已收款/试课中投递的订单必须先在投递审核中
    完成退款或没收，禁止直接重置——否则教员已付的钱在台账上凭空消失。
    """
    result = await db.execute(
        select(Application.order_id)
        .where(
            Application.order_id.in_(order_ids),
            Application.status.in_(_PAID_TRIAL_APPLICATION_STATUSES),
        )
        .group_by(Application.order_id)
    )
    if result.first() is not None:
        raise HTTPException(
            status_code=409,
            detail="订单仍有已收定金/试课中的投递，请先在投递审核中完成退款或没收，再重新开放",
        )


async def _reset_applications_for_republish(
    db: AsyncSession,
    order: Order,
) -> None:
    """重开订单时清理未产生资金往来的活跃投递并通知教员；已收款的投递由 _ensure_reopenable 先拦截。"""
    result = await db.execute(
        select(Application).where(
            Application.order_id == order.id,
            Application.status.in_(
                (ApplicationStatus.pending, ApplicationStatus.shortlisted)
            ),
        )
    )
    now = datetime.datetime.utcnow()
    for application in result.scalars().all():
        application.status = ApplicationStatus.rejected
        application.rejected_at = now
        content = f"您投递的「{order.grade_subject}」订单已重新开放，原投递自动关闭。"
        db.add(Notification(
            teacher_id=application.teacher_id,
            title="订单重新发布",
            content=content[:255],
            application_id=application.id,
            order_id=order.id,
        ))

    result = await db.execute(
        select(Application).where(
            Application.order_id == order.id,
            Application.status == ApplicationStatus.refunded,
            Application.rejected_at.is_(None),
        )
    )
    for application in result.scalars().all():
        application.rejected_at = now


# ── B 端接口 ──

@router.post("/batch-parse", response_model=BatchParseResponse)
async def batch_parse(
    body: BatchParseRequest,
    payload: TokenPayload = Depends(require_tenant_owner()),
):
    """
    接收微信文本 → DeepSeek 解析 → 高德编码 → 精算 → 返回预览。
    B 端中介专属。带每租户频率限制，防止刷爆 AI 账单。
    """
    await check_parse_rate_limit(payload)
    try:
        items = await parse_wechat_batch(body.raw_text)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:
        # 内部异常细节只进服务端日志，不回传客户端
        logger.exception("batch parse failed for tenant %s", payload.tenant_id)
        raise HTTPException(
            status_code=500,
            detail="AI 解析服务暂时不可用，请稍后重试；若持续失败请联系平台。",
        ) from e
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
    if payload.tenant_id is None:
        raise HTTPException(status_code=403, detail="未关联中介，无法导入订单")

    now = datetime.datetime.utcnow()
    expire_at = now + datetime.timedelta(hours=settings.ORDER_EXPIRE_HOURS)

    raw_ids = [item.raw_id for item in body.items]
    existing_result = await db.execute(
        select(Order.raw_id).where(
            Order.tenant_id == payload.tenant_id,
            Order.raw_id.in_(raw_ids),
        )
    )
    skipped_duplicates = set(existing_result.scalars().all())
    seen_in_batch: set[str] = set()
    orders = []
    for item in body.items:
        if item.raw_id in skipped_duplicates or item.raw_id in seen_in_batch:
            skipped_duplicates.add(item.raw_id)
            continue
        seen_in_batch.add(item.raw_id)

        # 标准价订单一律由服务端按费率重算，不信任客户端金额，
        # 防止导入 0 信息费订单绕过整个收费体系；自带价（base_price<=0）沿用原值
        if item.base_price > 0:
            try:
                fee = calculate_info_fee(
                    base_price=item.base_price,
                    weekly_frequency=item.weekly_frequency,
                    is_summer_vacation=item.is_summer_vacation,
                )
            except ValueError as e:
                raise HTTPException(status_code=422, detail=f"订单 {item.raw_id}: {e}") from e
            info_fee = fee["total_info_fee"]
            deposit_amount = fee["deposit"]
            balance_amount = fee["balance"]
        else:
            info_fee = item.calculated_info_fee
            deposit_amount = item.deposit_amount
            balance_amount = item.balance_amount

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
            calculated_info_fee=info_fee,
            deposit_amount=deposit_amount,
            balance_amount=balance_amount,
            status=OrderStatus.recruiting,
            expired_at=expire_at,
        )
        db.add(order)
        orders.append(order)

    if not orders:
        return BatchImportResponse(
            imported=0,
            skipped_duplicates=sorted(skipped_duplicates),
        )

    try:
        await db.flush()  # 获取 ID
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="存在重复订单编号，请刷新订单列表后重试") from e

    # 异步写入 Redis GEO
    try:
        redis = await get_redis_client()
        await batch_sync_to_redis(orders, redis)
    except Exception:
        pass  # Redis 不可用时降级，MySQL 仍可正常工作
    finally:
        await invalidate_board_cache(payload.tenant_id)

    return BatchImportResponse(
        imported=len(orders),
        skipped_duplicates=sorted(skipped_duplicates),
    )


# ── 状态流转（B 端 + C 端） ──

@router.post("/{order_id}/transit", response_model=TransitResponse)
async def transit_status(
    order_id: int,
    body: TransitRequest,
    payload: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """订单状态流转。角色不同可触发的目标状态不同。"""
    # 重开会触发资金守卫检查，先锁行与投递侧资金操作互斥
    result = await db.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在")

    # 租户隔离：非超管只能操作自己租户的订单
    assert_tenant_scope(payload, order.tenant_id, detail="订单不存在")

    previous_status = order.status

    try:
        validate_transition(order.status, body.target_status, payload.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    order.status = body.target_status

    # 状态流转时的副操作
    if body.target_status == OrderStatus.recruiting:
        # 重新开放招聘：存在已收款投递的订单必须先完成资金处置
        await _ensure_reopenable(db, [order_id])
        await _reset_applications_for_republish(db, order)
        order.selected_teacher_id = None
        _refresh_order_expiry(order, datetime.datetime.utcnow())
    if body.target_status == OrderStatus.archived:
        try:
            redis = await get_redis_client()
            await remove_from_redis(order.tenant_id, order.id, redis)
        except Exception:
            pass

    await invalidate_board_cache(order.tenant_id)
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


@router.get("/export")
async def export_orders(
    status: OrderStatus | None = None,
    q: str | None = None,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """B 端导出本租户订单列表（CSV，UTF-8 BOM），支持状态与编号筛选。"""
    if payload.tenant_id is None:
        raise HTTPException(status_code=403, detail="未关联中介，无法导出")

    query = select(Order).where(Order.tenant_id == payload.tenant_id)
    if status:
        query = query.where(Order.status == status)
    if q and q.strip():
        query = query.where(Order.raw_id.contains(q.strip()))
    query = query.order_by(Order.created_at.desc(), Order.id.desc())
    # 导出行数上限：防止大租户全量导出拖垮内存/延迟（业务上手动清理归档即可控制规模）
    query = query.limit(20000)

    result = await db.execute(query)
    orders = result.scalars().all()

    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow([
        "订单编号", "年级科目", "课酬文本", "单次课酬", "每周次数", "寒暑假",
        "信息费", "定金", "尾款", "展示地址", "状态", "创建时间", "过期时间",
    ])
    status_labels = {
        OrderStatus.recruiting: "招聘中",
        OrderStatus.trial_in_progress: "试课中",
        OrderStatus.completed: "已完成",
        OrderStatus.archived: "已归档",
    }
    for o in orders:
        writer.writerow([
            o.raw_id,
            o.grade_subject,
            o.price_total,
            f"{float(o.base_price):.2f}",
            o.weekly_frequency,
            "是" if o.is_summer_vacation else "否",
            f"{float(o.calculated_info_fee):.2f}",
            f"{float(o.deposit_amount):.2f}",
            f"{float(o.balance_amount):.2f}",
            o.fuzzy_address,
            status_labels.get(o.status, o.status.value),
            o.created_at.strftime("%Y-%m-%d %H:%M:%S") if o.created_at else "",
            o.expired_at.strftime("%Y-%m-%d %H:%M:%S") if o.expired_at else "",
        ])

    filename = f"orders-{datetime.date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── 查询接口 ──

@router.post("/batch-status", response_model=BatchStatusUpdateResponse)
async def batch_update_status(
    body: BatchStatusUpdateRequest,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """B 端：批量整理订单状态，用于运营侧快速收纳列表。"""
    if payload.tenant_id is None:
        raise HTTPException(status_code=403, detail="未关联中介，无法操作订单")
    if body.target_status not in (
        OrderStatus.recruiting,
        OrderStatus.archived,
    ):
        raise HTTPException(
            status_code=422,
            detail="批量状态仅支持招聘中、已归档；成交必须走投递审核流程确认",
        )

    result = await db.execute(
        select(Order).where(
            Order.tenant_id == payload.tenant_id,
            Order.id.in_(body.order_ids),
        ).with_for_update()
    )
    orders = result.scalars().all()

    for order in orders:
        try:
            validate_transition(order.status, body.target_status, payload.role)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"订单 {order.raw_id}: {e}") from e
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e)) from e

    now = datetime.datetime.utcnow()
    transition_ids = [o.id for o in orders if o.status != body.target_status]
    if body.target_status == OrderStatus.recruiting and transition_ids:
        # 批量重开同样必须先完成已收款投递的资金处置
        await _ensure_reopenable(db, transition_ids)

    updated = 0
    for order in orders:
        if order.status == body.target_status:
            continue
        order.status = body.target_status
        if body.target_status == OrderStatus.recruiting:
            _refresh_order_expiry(order, now)
            order.selected_teacher_id = None
        updated += 1

    await db.flush()

    for order in orders:
        await _sync_order_geo(order)

    return BatchStatusUpdateResponse(
        updated=updated,
        skipped=max(0, len(body.order_ids) - updated),
    )


@router.get("/", response_model=OrderListResponse)
async def list_orders(
    status: OrderStatus | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 20,
    payload: TokenPayload = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """分页查询订单列表。B 端看自己的，C 端看所有 recruiting。"""
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    query = select(Order)

    if payload.role in ("tenant_admin", "super_admin") and payload.tenant_id:
        query = query.where(Order.tenant_id == payload.tenant_id)
    elif payload.role == "teacher":
        query = query.where(Order.status == OrderStatus.recruiting)

    now = datetime.datetime.utcnow()
    query = query.where(
        (Order.status != OrderStatus.recruiting) | (Order.expired_at > now)
    )

    if status:
        query = query.where(Order.status == status)
    elif not q:
        query = query.where(Order.status.notin_([OrderStatus.completed, OrderStatus.archived]))

    if q:
        keyword = q.strip()
        if keyword:
            query = query.where(Order.raw_id.contains(keyword))

    query = query.order_by(Order.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    orders = result.scalars().all()

    total_result = await db.execute(select(func.count()).select_from(query.order_by(None).offset(None).limit(None).subquery()))
    total = total_result.scalar() or 0

    is_teacher_view = payload.role not in ("tenant_admin", "super_admin")
    return {
        "items": [serializers.order_list_payload(o, is_teacher_view=is_teacher_view) for o in orders],
        "page": page,
        "page_size": page_size,
        "total": total,
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

    is_teacher = payload.role not in ("tenant_admin", "super_admin")
    if not is_teacher:
        assert_tenant_scope(payload, order.tenant_id, detail="订单不存在")
    elif order.status != OrderStatus.recruiting:
        result = await db.execute(
            select(Application).where(
                Application.order_id == order_id,
                Application.teacher_id == payload.teacher_id,
            )
        )
        if not result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="订单不存在")

    # 教员侧一律脱敏：家长真实地址/电话仅可通过 address-unlock 卡点获取
    return _build_order_detail(order, include_sensitive=not is_teacher)


@router.patch("/{order_id}", response_model=OrderDetailResponse)
async def update_order(
    order_id: int,
    body: OrderUpdateRequest,
    payload: TokenPayload = Depends(require_tenant_owner()),
    db: AsyncSession = Depends(get_db),
):
    """B 端：编辑订单基础信息、价格、地址和有效期。"""
    order = await _get_managed_order(order_id, payload, db)
    if order.status != OrderStatus.recruiting:
        raise HTTPException(
            status_code=409,
            detail="仅招聘中的订单可编辑；试课中/已完成订单的价格与家长信息已被锁定",
        )
    data = body.model_dump(exclude_unset=True)
    # 显式 null 只对可空字段生效（清空备注/联系方式）；写入非空列会 500，这里按未提供处理
    clearable = {"requirements", "exact_address", "parent_phone", "subway_remark"}
    data = {field: value for field, value in data.items() if value is not None or field in clearable}

    recalculation_fields = {"base_price", "weekly_frequency", "is_summer_vacation"}
    should_recalculate = any(
        field in data and data[field] != getattr(order, field)
        for field in recalculation_fields
    )

    for field, value in data.items():
        setattr(order, field, value)

    # 管理端直接改有效期 = 开启新的提醒周期：打标，临期提醒按它去重（OPEN-ISSUES §1.1）
    if "expired_at" in data:
        order.expiry_refreshed_at = datetime.datetime.utcnow()

    if should_recalculate and float(order.base_price) > 0:
        try:
            fee = calculate_info_fee(
                base_price=float(order.base_price),
                weekly_frequency=order.weekly_frequency,
                is_summer_vacation=order.is_summer_vacation,
            )
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e)) from e
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
    try:
        validate_transition(order.status, OrderStatus.archived, payload.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
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

    await _ensure_reopenable(db, [order.id])
    await _reset_applications_for_republish(db, order)
    order.status = OrderStatus.recruiting
    order.selected_teacher_id = None
    _refresh_order_expiry(order, datetime.datetime.utcnow())
    await db.flush()
    await _sync_order_geo(order)
    return _build_order_detail(order)
