"""
AI 找单测试：条件解析校验、租户隔离、过滤行为与路由契约。
LLM 与地理编码全部 mock，不烧真实调用费。运行：pytest tests/test_order_query_tools.py
"""

import datetime

import pytest
from conftest import (
    BASE,
    auth_header,
    make_order,
    make_tenant,
    teacher_token,
    tenant_token,
)

from middleware.auth import TokenPayload
from services.order_query_tools import parse_find_order_conditions
from services.order_search import recruiting_center, search_orders
from utils.clock import utcnow


def _payload(tenant_id: int) -> TokenPayload:
    return TokenPayload(
        sub=f"tenant_admin_{tenant_id}", role="tenant_admin", tenant_id=tenant_id, issued_at=0
    )


def _mock_chat_json(monkeypatch, data: dict) -> None:
    async def fake_chat_json(system, user, **kwargs):
        return data

    monkeypatch.setattr("services.order_query_tools.chat_json", fake_chat_json)


# ── 条件解析（LLM 输出 → 规范化条件）──


async def test_parse_rejects_no_conditions(monkeypatch):
    _mock_chat_json(
        monkeypatch,
        {
            "subject": None,
            "grade": None,
            "min_base_price": None,
            "max_base_price": None,
            "radius_km": None,
            "anchor": None,
        },
    )
    with pytest.raises(ValueError, match="未能从描述中识别出筛选条件"):
        await parse_find_order_conditions("帮我随便看看")


async def test_parse_normalizes_and_clamps(monkeypatch):
    _mock_chat_json(
        monkeypatch,
        {
            "subject": "微积分",  # 别名 → 数学
            "grade": "初三",  # → 初中
            "min_base_price": "80",  # 字符串数字 → float
            "radius_km": 999,  # 超上限 → 截断 + warning
            "anchor": " 武侯区 ",
        },
    )
    conditions, warnings = await parse_find_order_conditions("随便什么原文")
    assert conditions["subject"] == "数学"
    assert conditions["grade"] == "初中"
    assert conditions["min_base_price"] == 80.0
    assert conditions["radius_km"] == 50.0
    assert conditions["anchor"] == "武侯区"
    assert any("上限" in w for w in warnings)


async def test_parse_unknown_subject_downgrades_to_warning(monkeypatch):
    _mock_chat_json(monkeypatch, {"subject": "编程", "grade": "初中"})
    conditions, warnings = await parse_find_order_conditions("随便什么原文")
    assert "subject" not in conditions
    assert conditions["grade"] == "初中"
    assert any("科目" in w for w in warnings)


async def test_parse_extracts_weekly_frequency(monkeypatch):
    _mock_chat_json(monkeypatch, {"subject": "英语", "grade": "高中", "weekly_frequency": "3"})
    conditions, _ = await parse_find_order_conditions("随便什么原文")
    assert conditions["weekly_frequency"] == 3

    _mock_chat_json(monkeypatch, {"subject": "英语", "weekly_frequency": "没写"})  # 非法 → 忽略
    conditions, _ = await parse_find_order_conditions("随便什么原文")
    assert "weekly_frequency" not in conditions


# ── 查询执行（search_orders，无 LLM 参与）──


async def test_search_tenant_isolation(db):
    tenant_a = await make_tenant(db, "iso_a")
    tenant_b = await make_tenant(db, "iso_b")
    await make_order(db, tenant_a.id, "A1", lng=104.06, lat=30.66)
    await make_order(db, tenant_b.id, "B1", lng=104.06, lat=30.66)

    result = await search_orders(db, _payload(tenant_a.id), {"subject": "数学"}, [])
    assert result["scanned"] == 1
    assert result["total_matched"] == 1
    assert result["items"][0]["raw_id"] == "A1"


async def test_search_filters_subject_price_and_expired(db):
    tenant = await make_tenant(db, "flt")
    await make_order(db, tenant.id, "MATH200", lng=104.06, lat=30.66)  # 初三数学 / 200
    eng = await make_order(db, tenant.id, "ENG", lng=104.06, lat=30.66)
    eng.grade_subject = "高一英语"
    cheap = await make_order(db, tenant.id, "CHEAP", lng=104.06, lat=30.66)
    cheap.base_price = 100
    expired = await make_order(db, tenant.id, "EXPIRED", lng=104.06, lat=30.66)
    expired.expired_at = utcnow() - datetime.timedelta(hours=1)
    await db.flush()

    result = await search_orders(
        db, _payload(tenant.id), {"subject": "数学", "min_base_price": 150}, []
    )
    assert [item["raw_id"] for item in result["items"]] == ["MATH200"]
    assert result["warnings"] == []


async def test_search_area_match_when_anchor_without_radius(db):
    """「武侯区的高中英语」：地点不带半径 → fuzzy_address 区域包含匹配。"""
    tenant = await make_tenant(db, "area")
    wuhou = await make_order(db, tenant.id, "WH_EN", lng=104.04, lat=30.64)
    wuhou.grade_subject = "高一英语"
    wuhou.fuzzy_address = "成都市武侯区外双楠"
    shuangliu = await make_order(db, tenant.id, "SL_EN", lng=103.92, lat=30.57)
    shuangliu.grade_subject = "高一英语"
    shuangliu.fuzzy_address = "成都市双流区东升街道"
    await db.flush()

    result = await search_orders(
        db, _payload(tenant.id), {"subject": "英语", "anchor": "武侯区"}, []
    )
    assert [item["raw_id"] for item in result["items"]] == ["WH_EN"]


async def test_search_filters_weekly_frequency(db):
    tenant = await make_tenant(db, "freq")
    once = await make_order(db, tenant.id, "F1", lng=104.06, lat=30.66)
    once.weekly_frequency = 1
    thrice = await make_order(db, tenant.id, "F3", lng=104.06, lat=30.66)
    thrice.weekly_frequency = 3
    await db.flush()

    result = await search_orders(
        db, _payload(tenant.id), {"subject": "数学", "weekly_frequency": 3}, []
    )
    assert [item["raw_id"] for item in result["items"]] == ["F3"]


async def test_search_radius_filters_by_anchor_distance(db):
    tenant = await make_tenant(db, "geo")
    await make_order(db, tenant.id, "NEAR", lng=104.065735, lat=30.659462)
    await make_order(db, tenant.id, "FAR", lng=104.5, lat=30.66)  # 约 40km 外

    anchor = (104.0657, 30.6594)
    result = await search_orders(
        db, _payload(tenant.id), {"subject": "数学", "radius_km": 10}, [], anchor_point=anchor
    )
    assert [item["raw_id"] for item in result["items"]] == ["NEAR"]
    assert result["items"][0]["distance_km"] is not None


async def test_search_without_anchor_returns_no_distance(db):
    tenant = await make_tenant(db, "noanchor")
    await make_order(db, tenant.id, "PLAIN", lng=104.06, lat=30.66)

    result = await search_orders(db, _payload(tenant.id), {"subject": "数学"}, [])
    assert result["items"][0]["distance_km"] is None


# ── 路由契约 ─--


async def test_find_orders_route_happy_path(client, db, monkeypatch):
    tenant = await make_tenant(db, "route")
    await make_order(db, tenant.id, "R1", lng=104.06, lat=30.66)
    await db.commit()  # 鉴权走请求级独立会话，造数必须落库可见

    async def fake_parse(query_text):
        return {"subject": "数学"}, []

    async def fake_anchor(anchor, radius, warnings):
        return None

    monkeypatch.setattr("routers.v1.ai.parse_find_order_conditions", fake_parse)
    monkeypatch.setattr("routers.v1.ai.resolve_anchor", fake_anchor)

    resp = await client.post(
        f"{BASE}/api/v1/ai/find-orders",
        json={"query": "找几个数学单"},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["conditions"]["subject"] == "数学"
    assert body["total_matched"] == 1
    assert body["items"][0]["raw_id"] == "R1"


async def test_find_orders_route_422_when_no_conditions(client, db, monkeypatch):
    tenant = await make_tenant(db, "route422")
    await db.commit()

    async def fake_parse(query_text):
        raise ValueError("未能从描述中识别出筛选条件，请至少说明科目、年级、价格或位置。")

    monkeypatch.setattr("routers.v1.ai.parse_find_order_conditions", fake_parse)
    resp = await client.post(
        f"{BASE}/api/v1/ai/find-orders",
        json={"query": "今天天气怎么样"},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 422
    assert "筛选条件" in resp.json()["detail"]


async def test_recruiting_center_median_and_empty(db):
    tenant = await make_tenant(db, "center")
    assert await recruiting_center(db, _payload(tenant.id)) is None  # 无在招订单

    await make_order(db, tenant.id, "C1", lng=104.00, lat=30.60)
    await make_order(db, tenant.id, "C2", lng=104.10, lat=30.70)
    center = await recruiting_center(db, _payload(tenant.id))
    assert center == (104.05, 30.65)  # 两点的中位数即中点


async def test_find_orders_nearby_without_anchor_uses_recruiting_center(client, db, monkeypatch):
    tenant = await make_tenant(db, "nearby")
    near1 = await make_order(db, tenant.id, "NEARBY1", lng=104.34, lat=30.66)
    near2 = await make_order(db, tenant.id, "NEARBY2", lng=104.36, lat=30.66)
    far = await make_order(db, tenant.id, "FARAWAY", lng=105.20, lat=30.66)  # 孤点拉偏不了中位数
    await db.commit()

    async def fake_parse(query_text):
        return {"radius_km": 10}, []  # “附近10公里”：有半径、无锚点

    async def fake_anchor(anchor, radius, warnings):
        return None

    monkeypatch.setattr("routers.v1.ai.parse_find_order_conditions", fake_parse)
    monkeypatch.setattr("routers.v1.ai.resolve_anchor", fake_anchor)

    resp = await client.post(
        f"{BASE}/api/v1/ai/find-orders",
        json={"query": "附近10公里的数学单"},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 锚点回退为在招订单中心（中位数）：两近单命中且按距离排序，孤远的 FARAWAY 被过滤
    assert body["conditions"]["anchor"] == "在招订单中心"
    assert body["conditions"]["radius_km"] == 10
    assert any("中心" in w for w in body["warnings"])
    assert [item["raw_id"] for item in body["items"]] == [near2.raw_id, near1.raw_id]
    assert far.raw_id not in [item["raw_id"] for item in body["items"]]


async def test_find_orders_device_location_anchor(client, db, monkeypatch):
    """「附近」未指地点：请求携带设备定位时按"你的位置"计算，而非在招订单中心。"""
    tenant = await make_tenant(db, "devloc")
    near = await make_order(db, tenant.id, "NEARME", lng=104.34, lat=30.66)
    far = await make_order(db, tenant.id, "FARAWAY", lng=105.20, lat=30.66)
    await db.commit()

    async def fake_parse(query_text):
        return {"radius_km": 10}, []

    monkeypatch.setattr("routers.v1.ai.parse_find_order_conditions", fake_parse)

    resp = await client.post(
        f"{BASE}/api/v1/ai/find-orders",
        json={"query": "附近10公里的数学单", "anchor_lng": 104.35, "anchor_lat": 30.66},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["conditions"]["anchor"] == "你的位置"
    assert [item["raw_id"] for item in body["items"]] == [near.raw_id]
    assert far.raw_id not in [item["raw_id"] for item in body["items"]]
    assert not any("中心" in w for w in body["warnings"])  # 不再走在招订单中心兜底


async def test_typed_anchor_wins_over_device_location(client, db, monkeypatch):
    """用户写明了地点（如"武侯区"）：文字锚点优先于设备定位。"""
    tenant = await make_tenant(db, "typed")
    at_typed = await make_order(db, tenant.id, "AT_TYPED", lng=104.065, lat=30.544)
    at_device = await make_order(db, tenant.id, "AT_DEVICE", lng=104.34, lat=30.66)
    await db.commit()

    async def fake_parse(query_text):
        return {"radius_km": 10, "anchor": "高新区"}, []

    async def fake_anchor(anchor, radius, warnings):
        return (104.065, 30.544)  # 模拟高德对"高新区"的地理编码

    monkeypatch.setattr("routers.v1.ai.parse_find_order_conditions", fake_parse)
    monkeypatch.setattr("routers.v1.ai.resolve_anchor", fake_anchor)

    resp = await client.post(
        f"{BASE}/api/v1/ai/find-orders",
        json={"query": "高新区10公里内的数学单", "anchor_lng": 104.34, "anchor_lat": 30.66},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["conditions"]["anchor"] == "高新区"
    assert [item["raw_id"] for item in body["items"]] == [at_typed.raw_id]
    assert at_device.raw_id not in [item["raw_id"] for item in body["items"]]


async def test_find_orders_rejects_teacher(client, db):
    resp = await client.post(
        f"{BASE}/api/v1/ai/find-orders",
        json={"query": "初三数学"},
        headers=auth_header(teacher_token(9999)),
    )
    assert resp.status_code == 403


async def test_find_orders_rate_limited(client, db, fake_redis, monkeypatch):
    from config import settings

    tenant = await make_tenant(db, "route429")
    await db.commit()

    async def fake_parse(query_text):
        return {"subject": "数学"}, []

    async def fake_anchor(anchor, radius, warnings):
        return None

    monkeypatch.setattr("routers.v1.ai.parse_find_order_conditions", fake_parse)
    monkeypatch.setattr("routers.v1.ai.resolve_anchor", fake_anchor)

    headers = auth_header(tenant_token(tenant.id))
    limit = settings.MAX_AI_QUERY_PER_MINUTE
    for _ in range(limit):
        resp = await client.post(
            f"{BASE}/api/v1/ai/find-orders", json={"query": "数学单"}, headers=headers
        )
        assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/ai/find-orders", json={"query": "数学单"}, headers=headers
    )
    assert resp.status_code == 429
