"""
订单语义索引测试（阶段 2）：白名单红线、租户隔离、状态复核、降级契约。
Embedding 全部 mock（确定性向量，不烧真实调用费）。
运行：pytest tests/test_order_semantic.py
"""

import datetime

from conftest import (
    BASE,
    auth_header,
    make_order,
    make_tenant,
    teacher_token,
    tenant_token,
)
from sqlalchemy import select

from middleware.auth import TokenPayload
from models.domain import Order, OrderSemanticIndex, OrderStatus
from services import order_semantic
from services.embedding import EmbeddingUnavailableError
from utils.clock import utcnow


def _vec(text: str) -> list[float]:
    """确定性 8 维向量：按字符分桶。共享字符越多相似度越高。"""
    v = [0.0] * 8
    for ch in text:
        v[ord(ch) % 8] += 1.0
    return v


def _mock_embed(monkeypatch):
    async def fake_embed_texts(texts):
        return [_vec(text) for text in texts]

    monkeypatch.setattr(order_semantic, "embed_texts", fake_embed_texts)


def _payload(tenant_id: int) -> TokenPayload:
    return TokenPayload(
        sub=f"tenant_admin_{tenant_id}", role="tenant_admin", tenant_id=tenant_id, issued_at=0
    )


async def _sync_all(db) -> None:
    orders = list((await db.scalars(select(Order))).all())
    for order in orders:
        await order_semantic.sync_orders_batch(db, [order])
    await db.commit()


# ── 白名单红线 ──


def test_order_index_text_never_contains_sensitive_fields():
    """家长电话/门牌地址/微信原文永不进入索引文本——白名单的锁定桩。"""
    order = Order(
        tenant_id=1,
        raw_id="X",
        raw_text="家长微信 wx_abc123 电话 13800001234",
        grade_subject="初三数学",
        requirements="女教员有耐心",
        price_total="200/次",
        base_price=200,
        fuzzy_address="成都市武侯区某小区",
        subway_remark="近地铁",
        lng=104.06,
        lat=30.66,
        expired_at=utcnow() + datetime.timedelta(hours=1),
        exact_address="武侯区某小区3栋2单元501",
        parent_phone="13800001234",
    )
    text = order_semantic.order_index_text(order)
    assert "初三数学" in text and "女教员有耐心" in text
    # 红线：三个敏感来源一个都不能出现
    assert "13800001234" not in text
    assert "wx_abc123" not in text
    assert "3栋2单元501" not in text


# ── 同步与回填 ──


async def test_sync_and_backfill(db, monkeypatch):
    _mock_embed(monkeypatch)
    tenant = await make_tenant(db, "osi_sync")
    await make_order(db, tenant.id, "S1")
    await db.commit()

    assert await order_semantic.backfill_missing(db) == 1
    await db.commit()
    rows = (await db.scalars(select(OrderSemanticIndex))).all()
    assert len(rows) == 1 and rows[0].tenant_id == tenant.id
    assert "初三数学" in rows[0].content

    # 已有索引不重复建：第二轮回填为 0
    assert await order_semantic.backfill_missing(db) == 0


async def test_sync_updates_content_on_change(db, monkeypatch):
    _mock_embed(monkeypatch)
    tenant = await make_tenant(db, "osi_upd")
    order = await make_order(db, tenant.id, "U1")
    await db.commit()

    await order_semantic.sync_orders_batch(db, [order])
    order.requirements = "改成了高中物理要求"
    await order_semantic.sync_orders_batch(db, [order])
    await db.commit()

    row = await db.get(OrderSemanticIndex, order.id)
    assert "高中物理" in row.content


async def test_backfill_catches_stale_after_edit(db, monkeypatch):
    """updated_at 晚于 synced_at 的订单视为过期：写入钩子漏掉的编辑由调度回填自愈。"""
    _mock_embed(monkeypatch)
    tenant = await make_tenant(db, "osi_stale")
    order = await make_order(db, tenant.id, "ST1")
    await db.commit()

    assert await order_semantic.backfill_missing(db) == 1
    await db.commit()
    assert await order_semantic.backfill_missing(db) == 0  # 新鲜索引不再回填

    # 模拟「同步之后发生编辑」：把 synced_at 拨回 1 秒前——时间戳秒级精度下
    # 等价于跨秒编辑（同秒内的编辑由写入钩子即时覆盖，不走本回填）
    row = await db.get(OrderSemanticIndex, order.id)
    row.synced_at = utcnow() - datetime.timedelta(seconds=1)
    order.requirements = "编辑后的新要求"
    await db.flush()
    assert await order_semantic.backfill_missing(db) == 1
    await db.commit()
    row = await db.get(OrderSemanticIndex, order.id)
    assert "编辑后的新要求" in row.content
    assert await order_semantic.backfill_missing(db) == 0


# ── 相似检索 ──


async def test_similar_tenant_isolation_and_self_exclude(db, monkeypatch):
    _mock_embed(monkeypatch)
    tenant_a = await make_tenant(db, "osi_a")
    tenant_b = await make_tenant(db, "osi_b")
    order_a1 = await make_order(db, tenant_a.id, "A1")
    await make_order(db, tenant_a.id, "A2")  # 同租户同文本 → 应命中
    await make_order(db, tenant_b.id, "B1")  # 他租户 → 永不出现
    await db.commit()
    await _sync_all(db)

    items = await order_semantic.find_similar_orders(db, order_a1)
    assert [item["raw_id"] for item in items] == ["A2"]
    assert items[0]["similarity"] > 0.99  # 相同白名单文本 → 余弦≈1


async def test_similar_excludes_archived_and_expired(db, monkeypatch):
    _mock_embed(monkeypatch)
    tenant = await make_tenant(db, "osi_st")
    base = await make_order(db, tenant.id, "BASE")
    archived = await make_order(db, tenant.id, "ARCH")
    archived.status = OrderStatus.archived
    expired = await make_order(db, tenant.id, "EXPIRED")
    expired.expired_at = utcnow() - datetime.timedelta(hours=1)
    await db.commit()
    await _sync_all(db)

    # 归档与过期都不入结果（状态/有效期以实时 orders 表复核为准）
    assert await order_semantic.find_similar_orders(db, base) == []


# ── 路由契约 ──


async def test_similar_route_and_teacher_forbidden(client, db, monkeypatch):
    _mock_embed(monkeypatch)
    tenant = await make_tenant(db, "osi_rt")
    order = await make_order(db, tenant.id, "R1")
    other = await make_order(db, tenant.id, "R2")
    await db.commit()
    await _sync_all(db)

    headers = auth_header(tenant_token(tenant.id))
    resp = await client.get(f"{BASE}/api/v1/ai/orders/{order.id}/similar", headers=headers)
    assert resp.status_code == 200, resp.text
    assert [item["raw_id"] for item in resp.json()["items"]] == ["R2"]

    # 教员无权
    resp = await client.get(
        f"{BASE}/api/v1/ai/orders/{order.id}/similar",
        headers=auth_header(teacher_token(9999)),
    )
    assert resp.status_code == 403


async def test_similar_route_cross_tenant_404(client, db, monkeypatch):
    _mock_embed(monkeypatch)
    tenant_a = await make_tenant(db, "osi_xa")
    tenant_b = await make_tenant(db, "osi_xb")
    order_b = await make_order(db, tenant_b.id, "XB")
    await db.commit()

    resp = await client.get(
        f"{BASE}/api/v1/ai/orders/{order_b.id}/similar",
        headers=auth_header(tenant_token(tenant_a.id)),
    )
    assert resp.status_code == 404


async def test_similar_route_embedding_unavailable_503(client, db, monkeypatch):
    tenant = await make_tenant(db, "osi_503")
    order = await make_order(db, tenant.id, "NF")
    await db.commit()  # 不建索引 → 现场向量化 → 不可用

    async def raise_unavailable(texts):
        raise EmbeddingUnavailableError("Embedding 服务暂时不可用")

    monkeypatch.setattr(order_semantic, "embed_texts", raise_unavailable)
    resp = await client.get(
        f"{BASE}/api/v1/ai/orders/{order.id}/similar",
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 503
    assert "暂不可用" in resp.json()["detail"]
