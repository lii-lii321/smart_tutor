"""
订单展示字段单点映射：orders 列表/详情、公开橱窗、教员推荐四类视图共用。

此前金额 float 化、坐标降精度、needs_manual_price 判定在四处各写一份，
改口径时容易漏改；收敛到本模块后由测试锁定输出契约。
"""
from models.domain import Order
from utils.geo import coarse_coordinate
from utils.masking import mask_contact_info


def money_fields(order: Order) -> dict:
    """四类视图共用的金额口径：DECIMAL → float，零价单标记需人工定价。"""
    return {
        "base_price": float(order.base_price),
        "calculated_info_fee": float(order.calculated_info_fee),
        "deposit_amount": float(order.deposit_amount),
        "balance_amount": float(order.balance_amount),
        "needs_manual_price": float(order.base_price) <= 0,
    }


def teacher_brief_fields(order: Order) -> dict:
    """
    教员/公开橱窗视图共用的脱敏字段组：
    坐标降精度到小区级（防米级坐标还原家庭住址）+ 金额字段。
    """
    lng, lat = coarse_coordinate(float(order.lng), float(order.lat))
    return {
        **money_fields(order),
        "weekly_frequency": order.weekly_frequency,
        "fuzzy_address": order.fuzzy_address,
        "subway_remark": order.subway_remark,
        "lng": lng,
        "lat": lat,
    }


def order_detail_payload(order: Order, *, include_sensitive: bool = True) -> dict:
    """
    GET /orders/{id} 的完整详情。
    include_sensitive=False（教员视角）时剥离家长真实地址与电话、
    对原文做联系方式掩码、坐标降精度——家长信息只能经 /address-unlock 卡点获取。
    """
    raw_text = order.raw_text if include_sensitive else mask_contact_info(order.raw_text)
    lng, lat = float(order.lng), float(order.lat)
    if not include_sensitive:
        lng, lat = coarse_coordinate(lng, lat)
    return {
        "id": order.id,
        "raw_id": order.raw_id,
        "raw_text": raw_text,
        "grade_subject": order.grade_subject,
        "requirements": order.requirements,
        "exact_address": order.exact_address if include_sensitive else None,
        "parent_phone": order.parent_phone if include_sensitive else None,
        "price_total": order.price_total,
        "base_price": float(order.base_price),
        "weekly_frequency": order.weekly_frequency,
        "is_summer_vacation": order.is_summer_vacation,
        "fuzzy_address": order.fuzzy_address,
        "subway_remark": order.subway_remark,
        "lng": lng,
        "lat": lat,
        "calculated_info_fee": float(order.calculated_info_fee),
        "deposit_amount": float(order.deposit_amount),
        "balance_amount": float(order.balance_amount),
        "needs_manual_price": float(order.base_price) <= 0,
        "status": order.status,
        "created_at": order.created_at,
        "expired_at": order.expired_at,
    }


def order_list_payload(order: Order, *, is_teacher_view: bool) -> dict:
    """GET /orders/ 的列表项：教员视角坐标降精度，B 端保留精确坐标。"""
    lng, lat = float(order.lng), float(order.lat)
    if is_teacher_view:
        lng, lat = coarse_coordinate(lng, lat)
    return {
        "id": order.id,
        "raw_id": order.raw_id,
        "grade_subject": order.grade_subject,
        "price_total": order.price_total,
        "base_price": float(order.base_price),
        "fuzzy_address": order.fuzzy_address,
        "status": order.status.value,
        "needs_manual_price": float(order.base_price) <= 0,
        "calculated_info_fee": float(order.calculated_info_fee),
        "deposit_amount": float(order.deposit_amount),
        "balance_amount": float(order.balance_amount),
        "weekly_frequency": order.weekly_frequency,
        "lng": lng,
        "lat": lat,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "expired_at": order.expired_at.isoformat() if order.expired_at else None,
    }


def order_board_payload(order: Order) -> dict:
    """公开橱窗（/public/agent/{code}/board）：始终脱敏，无 raw_id/status。"""
    return {
        "id": order.id,
        "grade_subject": order.grade_subject,
        "price_total": order.price_total,
        **teacher_brief_fields(order),
        "created_at": order.created_at,
    }


def order_recommendation_payload(order: Order) -> dict:
    """教员推荐项的订单基础字段（推荐分等业务字段由调用方补充）。"""
    return {
        "id": order.id,
        "raw_id": order.raw_id,
        "grade_subject": order.grade_subject,
        "price_total": order.price_total,
        "status": order.status,
        "created_at": order.created_at,
        **teacher_brief_fields(order),
    }
