"""
知识库测试：切分器、租户隔离矩阵、文档生命周期与问答契约。
Embedding 与 LLM 全部 mock（确定性向量，不烧真实调用费）。
运行：pytest tests/test_knowledge.py
"""

from conftest import (
    BASE,
    auth_header,
    make_tenant,
    teacher_token,
    tenant_token,
)
from sqlalchemy import select

from middleware.auth import TokenPayload
from models.domain import KnowledgeChunk
from services import assistant as assistant_service
from services import knowledge as knowledge_service
from services.auth import create_jwt
from services.embedding import EmbeddingUnavailableError


def _vec(text: str) -> list[float]:
    """确定性 8 维向量：按字符分桶落位。共享字符越多相似度越高，
    完全不交叠的文档对相似度为 0——足够支撑隔离断言。"""
    v = [0.0] * 8
    for ch in text:
        v[ord(ch) % 8] += 1.0
    return v


def _mock_embed(monkeypatch):
    async def fake_embed_texts(texts):
        return [_vec(text) for text in texts]

    monkeypatch.setattr(knowledge_service, "embed_texts", fake_embed_texts)


def _boss_token() -> str:
    return create_jwt(sub="super_admin_1", role="super_admin")


def _payload(tenant_id: int | None, role: str = "tenant_admin") -> TokenPayload:
    return TokenPayload(sub=f"{role}_{tenant_id or 0}", role=role, tenant_id=tenant_id, issued_at=0)


async def _create_doc(db, tenant_id: int | None, title: str, content: str):
    from models.domain import KnowledgeDocument

    doc = KnowledgeDocument(
        tenant_id=tenant_id,
        title=title,
        source_type="paste",
        content=content,
        status="pending",
        created_by_role="tenant_admin" if tenant_id else "super_admin",
    )
    db.add(doc)
    await db.flush()
    await knowledge_service.process_document(db, doc)
    return doc


# ── 切分器 ──


def test_split_chunks_empty():
    assert knowledge_service.split_chunks("") == []
    assert knowledge_service.split_chunks("   \n  ") == []


def test_split_chunks_paragraphs_and_limit():
    content = "\n\n".join(f"第{i}段：" + "内容" * 60 for i in range(5))  # 每段约 126 字
    chunks = knowledge_service.split_chunks(content)
    assert len(chunks) > 1
    assert all(len(chunk) <= knowledge_service.CHUNK_MAX for chunk in chunks)
    assert "".join(chunks).startswith("第0段")


def test_split_chunks_hard_split_oversized_sentence():
    content = "超" * 1200  # 无句读的单块
    chunks = knowledge_service.split_chunks(content)
    assert all(len(chunk) <= knowledge_service.CHUNK_MAX for chunk in chunks)
    assert sum(len(chunk) for chunk in chunks) == 1200


# ── 检索租户隔离 ─--


async def test_search_tenancy_isolation(db, monkeypatch):
    _mock_embed(monkeypatch)
    tenant_a = await make_tenant(db, "kb_a")
    tenant_b = await make_tenant(db, "kb_b")
    await _create_doc(db, tenant_a.id, "A规则", "甲甲甲甲收费规则")
    await _create_doc(db, tenant_b.id, "B规则", "乙乙乙乙退款规则")
    await _create_doc(db, None, "平台规则", "丙丙丙丙试课规范")
    await db.commit()

    # A 检索自己的文档：命中；B 的文档不可见
    hits_a = await knowledge_service.search_chunks(db, tenant_a.id, "甲甲甲甲")
    assert [hit["document_id"] for hit in hits_a] and all(
        hit["content"].startswith("甲") for hit in hits_a
    )

    # super_admin 平台检索：只见平台库
    hits_boss = await knowledge_service.search_chunks(db, None, "丙丙丙丙")
    assert len(hits_boss) == 1 and hits_boss[0]["content"].startswith("丙")


async def test_deleted_doc_not_searchable(db, monkeypatch):
    _mock_embed(monkeypatch)
    tenant = await make_tenant(db, "kb_del")
    doc = await _create_doc(db, tenant.id, "规则", "丁丁丁丁流程说明")
    await db.commit()

    await knowledge_service.delete_document(db, doc)
    await db.commit()

    assert await knowledge_service.search_chunks(db, tenant.id, "丁丁丁丁") == []
    remaining = (await db.scalars(select(KnowledgeChunk))).all()
    assert remaining == []


# ── 路由：文档生命周期 ─--


async def test_router_create_list_and_teacher_forbidden(client, db, monkeypatch):
    _mock_embed(monkeypatch)
    tenant = await make_tenant(db, "kb_api")
    await db.commit()

    headers = auth_header(tenant_token(tenant.id))
    resp = await client.post(
        f"{BASE}/api/v1/ai/knowledge/documents",
        json={"title": "收费规则", "content": "收费规则：信息费为课酬的一点五倍"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "ready"
    assert body["chunk_count"] > 0
    assert body["tenant_id"] == tenant.id

    resp = await client.get(f"{BASE}/api/v1/ai/knowledge/documents", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    # 教员无权访问知识库管理
    resp = await client.get(
        f"{BASE}/api/v1/ai/knowledge/documents", headers=auth_header(teacher_token(9999))
    )
    assert resp.status_code == 403


async def test_router_platform_doc_visibility_and_delete_guard(client, db, monkeypatch):
    _mock_embed(monkeypatch)
    tenant = await make_tenant(db, "kb_pf")
    await db.commit()

    boss_headers = auth_header(_boss_token())
    resp = await client.post(
        f"{BASE}/api/v1/ai/knowledge/documents",
        json={"title": "平台试课规范", "content": "平台规范：试课前必须确认定金到账"},
        headers=boss_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["tenant_id"] is None
    platform_id = resp.json()["id"]

    # 租户可见平台文档、可读详情
    tenant_headers = auth_header(tenant_token(tenant.id))
    resp = await client.get(f"{BASE}/api/v1/ai/knowledge/documents", headers=tenant_headers)
    assert any(item["id"] == platform_id for item in resp.json()["items"])
    resp = await client.get(
        f"{BASE}/api/v1/ai/knowledge/documents/{platform_id}", headers=tenant_headers
    )
    assert resp.status_code == 200

    # 租户不能删平台文档（404 不泄露存在性）；boss 可以删
    resp = await client.delete(
        f"{BASE}/api/v1/ai/knowledge/documents/{platform_id}", headers=tenant_headers
    )
    assert resp.status_code == 404
    resp = await client.delete(
        f"{BASE}/api/v1/ai/knowledge/documents/{platform_id}", headers=boss_headers
    )
    assert resp.status_code == 200
    resp = await client.get(
        f"{BASE}/api/v1/ai/knowledge/documents/{platform_id}", headers=boss_headers
    )
    assert resp.status_code == 404


async def test_router_update_reembeds_content(client, db, monkeypatch):
    _mock_embed(monkeypatch)
    tenant = await make_tenant(db, "kb_upd")
    await db.commit()
    headers = auth_header(tenant_token(tenant.id))

    resp = await client.post(
        f"{BASE}/api/v1/ai/knowledge/documents",
        json={"title": "旧规则", "content": "旧内容"},
        headers=headers,
    )
    doc_id = resp.json()["id"]

    new_content = "新规则内容\n\n" + "补充说明。" * 60
    resp = await client.put(
        f"{BASE}/api/v1/ai/knowledge/documents/{doc_id}",
        json={"content": new_content},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    expected_chunks = len(knowledge_service.split_chunks(new_content))
    assert resp.json()["chunk_count"] == expected_chunks


async def test_router_cross_tenant_doc_invisible(client, db, monkeypatch):
    _mock_embed(monkeypatch)
    tenant_a = await make_tenant(db, "kb_xa")
    tenant_b = await make_tenant(db, "kb_xb")
    doc_b = await _create_doc(db, tenant_b.id, "B私有", "戊戊戊戊B中介私有规则")
    await db.commit()

    headers_a = auth_header(tenant_token(tenant_a.id))
    resp = await client.get(f"{BASE}/api/v1/ai/knowledge/documents", headers=headers_a)
    assert resp.json()["total"] == 0

    resp = await client.get(f"{BASE}/api/v1/ai/knowledge/documents/{doc_b.id}", headers=headers_a)
    assert resp.status_code == 404


# ── 问答契约 ──


async def test_assistant_query_with_citations(client, db, monkeypatch):
    from models.domain import AiQueryLog

    tenant = await make_tenant(db, "kb_qa")
    doc = await _create_doc(db, tenant.id, "收费规则", "收费规则正文")
    tenant_id, doc_id = tenant.id, doc.id  # commit 过期实例前捕获 id
    await db.commit()

    async def fake_search(session, scope_tenant_id, query, **kwargs):
        assert scope_tenant_id == tenant_id
        return [{"document_id": doc_id, "content": "收费规则正文", "score": 0.9}]

    async def fake_chat(system, user, **kwargs):
        assert "[1]" in system and "收费规则正文" in system
        return "根据规则，信息费为课酬的 1.5 倍 [1]。"

    monkeypatch.setattr(knowledge_service, "search_chunks", fake_search)
    monkeypatch.setattr(assistant_service, "chat", fake_chat)

    resp = await client.post(
        f"{BASE}/api/v1/ai/assistant/query",
        json={"question": "信息费怎么算？"},
        headers=auth_header(tenant_token(tenant_id)),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "[1]" in body["answer"]
    assert body["citations"][0]["title"] == "收费规则"
    assert body["citations"][0]["document_id"] == doc_id
    assert body["latency_ms"] is not None

    # 调用日志已落库（应用会话独立 commit；测试会话新事务可见）
    logs = (await db.scalars(select(AiQueryLog).where(AiQueryLog.intent == "knowledge"))).all()
    assert len(logs) == 1
    assert logs[0].tenant_id == tenant_id
    assert logs[0].hit_document_ids == f"[{doc_id}]"


async def test_assistant_no_result_is_honest(client, db, monkeypatch):
    tenant = await make_tenant(db, "kb_qa0")
    await db.commit()

    async def fake_search(session, tenant_id, query, **kwargs):
        return []

    monkeypatch.setattr(knowledge_service, "search_chunks", fake_search)
    resp = await client.post(
        f"{BASE}/api/v1/ai/assistant/query",
        json={"question": "完全无关的问题"},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "没有找到" in body["answer"]
    assert body["citations"] == []


async def test_assistant_embedding_unavailable_degrades(client, db, monkeypatch):
    tenant = await make_tenant(db, "kb_qafail")
    await db.commit()

    async def fake_search(session, tenant_id, query, **kwargs):
        raise EmbeddingUnavailableError("Embedding 服务暂时不可用")

    monkeypatch.setattr(knowledge_service, "search_chunks", fake_search)
    resp = await client.post(
        f"{BASE}/api/v1/ai/assistant/query",
        json={"question": "收费规则是什么"},
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 200
    assert "暂时不可用" in resp.json()["answer"]


async def test_assistant_rejects_teacher(client, db):
    resp = await client.post(
        f"{BASE}/api/v1/ai/assistant/query",
        json={"question": "信息费怎么算"},
        headers=auth_header(teacher_token(9999)),
    )
    assert resp.status_code == 403
