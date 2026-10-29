"""
教员端 AI 助手测试：按邀请码定位当前中介、租户+公共库检索、配额软降级、权限。
Embedding 与 LLM 全部 mock（确定性向量与固定回答，不烧真实调用费）。
运行：pytest tests/test_teacher_assistant.py
"""

from conftest import BASE, auth_header, make_teacher, make_tenant, teacher_token

from services import assistant as assistant_service
from services import knowledge as knowledge_service


def _vec(text: str) -> list[float]:
    v = [0.0] * 8
    for ch in text:
        v[ord(ch) % 8] += 1.0
    return v


def _mock_embed(monkeypatch):
    async def fake_embed_texts(texts):
        return [_vec(text) for text in texts]

    monkeypatch.setattr(knowledge_service, "embed_texts", fake_embed_texts)


def _mock_chat(monkeypatch, reply: str):
    async def fake_chat(system, user, **kwargs):
        return reply

    monkeypatch.setattr(assistant_service, "chat", fake_chat)


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


async def test_teacher_assistant_answers_from_current_tenant(client, db, monkeypatch):
    _mock_embed(monkeypatch)
    _mock_chat(monkeypatch, "根据知识库 [1]，信息费为 480 元，定金固定 100 元。")
    tenant = await make_tenant(db, "tas_a")
    await make_teacher(db, "tas_a_t")
    await _create_doc(db, tenant.id, "收费规则", "信息费为周课时费乘以频次倍率，一周三次以上八折。")
    await db.commit()

    resp = await client.post(
        f"{BASE}/api/v1/ai/teacher/assistant",
        json={"question": "信息费怎么算？", "invite_code": "tas_a"},
        headers=auth_header(teacher_token(1)),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "480" in body["answer"]
    assert body["citations"], "回答应带来源引用"
    assert body["citations"][0]["title"] == "收费规则"


async def test_teacher_assistant_isolated_by_invite_code(client, db, monkeypatch):
    """教员用 A 中介邀请码提问：B 中介的文档不可见，平台公共库可见。"""
    _mock_embed(monkeypatch)
    _mock_chat(monkeypatch, "知识库中找到了相关内容 [1]。")
    tenant_a = await make_tenant(db, "tas_xa")
    tenant_b = await make_tenant(db, "tas_xb")
    await make_teacher(db, "tas_x_t")
    await _create_doc(db, tenant_b.id, "B 中介私有规则", "B 中介专属的秘密规则内容。")
    await _create_doc(db, None, "平台公共规则", "平台级公共规则：试课失败按公式退费。")
    await db.commit()

    resp = await client.post(
        f"{BASE}/api/v1/ai/teacher/assistant",
        json={"question": "试课失败怎么退？", "invite_code": "tas_xa"},
        headers=auth_header(teacher_token(1)),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    titles = [c["title"] for c in body["citations"]]
    assert "平台公共规则" in titles
    assert "B 中介私有规则" not in titles, "其他中介的文档不得被检索到"


async def test_teacher_assistant_rejects_invalid_invite(client, db):
    await make_teacher(db, "tas_inv_t")
    resp = await client.post(
        f"{BASE}/api/v1/ai/teacher/assistant",
        json={"question": "信息费怎么算？", "invite_code": "nope_nope"},
        headers=auth_header(teacher_token(1)),
    )
    assert resp.status_code == 404


async def test_teacher_assistant_requires_teacher_role(client, db):
    tenant = await make_tenant(db, "tas_r")
    resp = await client.post(
        f"{BASE}/api/v1/ai/teacher/assistant",
        json={"question": "信息费怎么算？", "invite_code": "tas_r"},
    )
    assert resp.status_code in (401, 403)


async def test_teacher_assistant_quota_soft_degrade(client, db, monkeypatch):
    """配额用完不 429：返回诚实提示（软降级口径与教员找单一致）。"""
    from routers.v1 import ai as ai_router

    async def no_quota(payload, *, now=None):
        return False

    monkeypatch.setattr(ai_router, "try_consume_teacher_ai_quota", no_quota)
    tenant = await make_tenant(db, "tas_q")
    await make_teacher(db, "tas_q_t")
    await db.commit()

    resp = await client.post(
        f"{BASE}/api/v1/ai/teacher/assistant",
        json={"question": "信息费怎么算？", "invite_code": "tas_q"},
        headers=auth_header(teacher_token(1)),
    )
    assert resp.status_code == 200, resp.text
    assert "次数已用完" in resp.json()["answer"]
