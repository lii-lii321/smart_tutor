"""
订单序列化单点映射（services/serializers.py）的输出契约测试。

背景：同一套字段映射此前散落 orders/public/recommendation 四处，收敛后由本文件锁定：
- 教员/公开视图坐标必须降精度，B 端保留精确坐标；
- 教员视角详情必须剥离家长地址电话并掩码原文；
- needs_manual_price 与金额 float 化口径一致。
"""
import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from services import serializers
from utils.geo import coarse_coordinate
from utils.masking import mask_contact_info

if TYPE_CHECKING:
    from models.domain import Order


def _sample_order() -> "Order":
    from models.domain import Order, OrderStatus

    return Order(
        id=42,
        tenant_id=1,
        raw_id="EQ-042",
        raw_text="【EQ-042】家长张女士 13812345678 地址天府大道1号",
        grade_subject="初三数学",
        requirements="",
        price_total="200/次",
        base_price=Decimal("200.00"),
        weekly_frequency=2,
        is_summer_vacation=False,
        exact_address="天府大道1号101室",
        parent_phone="13812345678",
        fuzzy_address="成都市天府大道",
        subway_remark="近1号线",
        lng=Decimal("104.123456"),
        lat=Decimal("30.654321"),
        calculated_info_fee=Decimal("200.00"),
        deposit_amount=Decimal("100.00"),
        balance_amount=Decimal("100.00"),
        status=OrderStatus.recruiting,
        created_at=datetime.datetime(2026, 9, 9, 12, 0, 0),
        expired_at=datetime.datetime(2026, 9, 12, 12, 0, 0),
    )


def test_order_list_payload_teacher_vs_admin():
    order = _sample_order()
    teacher = serializers.order_list_payload(order, is_teacher_view=True)
    admin = serializers.order_list_payload(order, is_teacher_view=False)

    coarse_lng, coarse_lat = coarse_coordinate(104.123456, 30.654321)
    assert (teacher["lng"], teacher["lat"]) == (coarse_lng, coarse_lat)
    assert (admin["lng"], admin["lat"]) == (104.123456, 30.654321)
    assert teacher["status"] == "recruiting", "列表视图状态为字符串值"
    assert teacher["created_at"] == "2026-09-09T12:00:00"
    assert teacher["needs_manual_price"] is False
    assert teacher["base_price"] == 200.0


def test_order_detail_payload_sensitive_toggle():
    order = _sample_order()
    full = serializers.order_detail_payload(order, include_sensitive=True)
    masked = serializers.order_detail_payload(order, include_sensitive=False)

    assert full["parent_phone"] == "13812345678"
    assert full["exact_address"] == "天府大道1号101室"
    assert full["raw_text"] == order.raw_text
    assert full["lng"] == 104.123456

    assert masked["parent_phone"] is None
    assert masked["exact_address"] is None
    assert masked["raw_text"] == mask_contact_info(order.raw_text), "教员视角原文必须掩码"
    assert masked["needs_manual_price"] is False


def test_order_board_payload_is_masked():
    import pytest

    order = _sample_order()
    payload = serializers.order_board_payload(order)

    assert "raw_id" not in payload and "status" not in payload
    coarse_lng, coarse_lat = coarse_coordinate(104.123456, 30.654321)
    assert (payload["lng"], payload["lat"]) == (coarse_lng, coarse_lat)
    assert payload["deposit_amount"] == 100.0
    with pytest.raises(KeyError):
        payload["parent_phone"]


def test_order_recommendation_payload_shape():
    order = _sample_order()
    payload = serializers.order_recommendation_payload(order)

    assert payload["raw_id"] == "EQ-042"
    assert payload["status"].value == "recruiting"
    coarse_lng, coarse_lat = coarse_coordinate(104.123456, 30.654321)
    assert (payload["lng"], payload["lat"]) == (coarse_lng, coarse_lat)
