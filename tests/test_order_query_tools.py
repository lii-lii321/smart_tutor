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
from services.order_search import search_orders
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
