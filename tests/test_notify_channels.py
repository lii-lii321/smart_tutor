"""
触达通道测试：队列入库与业务同事务、投递成功/失败/重试耗尽、通道配置感知。

通道 HTTP 行为用 httpx MockTransport 隔离（不真发外呼）；队列与业务同事务的
回滚语义用独立事务包裹验证。
"""
from conftest import make_teacher

from models.domain import OutboundMessage
from services import notify


def _seed(db, *, event="teacher.notify", title="进入候选", content="正文") -> OutboundMessage:
    msg = OutboundMessage(event=event, title=title, content=content, teacher_id=None, tenant_id=None)
    db.add(msg)
    return msg


async def test_queue_outbound_rolls_back_with_business(db):
    """queue_outbound 与业务同事务：业务回滚时出站消息一起消失（不发假通知）。"""
    teacher = await make_teacher(db, "nt_teacher_a")
    notify.queue_outbound(
        db, event="teacher.notify", title="测试", content="x",
        teacher_id=teacher.id, tenant_id=None,
    )
    await db.flush()
    assert (await db.execute(
        __import__("sqlalchemy").select(OutboundMessage)
    )).scalars().all(), "flush 后应在事务内可见"

    await db.rollback()
    assert not (await db.execute(
        __import__("sqlalchemy").select(OutboundMessage)
    )).scalars().all(), "回滚后不应残留出站消息"


async def test_dispatch_log_only_when_no_channels(db, monkeypatch):
    """未配置任何网络通道：日志兜底即成功，消息转 sent。"""
    monkeypatch.setattr(notify.settings, "NOTIFY_WECOM_WEBHOOK_URL", "")
    monkeypatch.setattr(notify.settings, "NOTIFY_WEBHOOK_URL", "")
    _seed(db)
    await db.commit()

    sent, dead = await notify.dispatch_pending(db)
    assert (sent, dead) == (1, 0)
    msg = (await db.execute(__import__("sqlalchemy").select(OutboundMessage))).scalar_one()
    assert msg.status == "sent"
    assert msg.sent_at is not None


async def test_dispatch_success_and_failure_paths(db, monkeypatch):
    """配置了通道：成功 → sent；全部失败 → failed 且 attempts+1。"""
    calls: list[str] = []

    def fake_transport_factory(should_fail: bool):
        import httpx

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(str(request.url))
            if should_fail:
                raise httpx.ConnectError("boom")
            return httpx.Response(200, json={"errcode": 0})

        return httpx.MockTransport(handler)

    import httpx

    real_client_cls = httpx.AsyncClient

    def make_client(**kwargs):
        kwargs["transport"] = fake_transport_factory(FAIL_FLAG["value"])
        return real_client_cls(**kwargs)

    FAIL_FLAG = {"value": False}
    monkeypatch.setattr(notify.httpx, "AsyncClient", make_client)
    monkeypatch.setattr(notify.settings, "NOTIFY_WECOM_WEBHOOK_URL", "https://wecom.example/hook")
    monkeypatch.setattr(notify.settings, "NOTIFY_WEBHOOK_URL", "")

    # 成功路径
    _seed(db, title="成功消息")
    await db.commit()
    sent, dead = await notify.dispatch_pending(db)
    assert (sent, dead) == (1, 0)

    # 失败路径：通道全挂 → failed + attempts=1
    FAIL_FLAG["value"] = True
    _seed(db, title="失败消息")
    await db.commit()
    sent, dead = await notify.dispatch_pending(db)
    assert (sent, dead) == (0, 0)
    msg = (await db.execute(
        __import__("sqlalchemy").select(OutboundMessage).where(OutboundMessage.title == "失败消息")
    )).scalar_one()
    assert msg.status == "failed"
    assert msg.attempts == 1
    assert "boom" in (msg.last_error or "")


async def test_dispatch_retries_then_dead(db, monkeypatch):
    """重试耗尽：failed 消息下一轮仍会被投递（pending+failed 都取），
    超过 MAX_ATTEMPTS 转 dead 不再重试。"""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    real_client_cls = httpx.AsyncClient

    def make_client(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client_cls(**kwargs)

    monkeypatch.setattr(notify.httpx, "AsyncClient", make_client)
    monkeypatch.setattr(notify.settings, "NOTIFY_WEBHOOK_URL", "https://hook.example")
    monkeypatch.setattr(notify.settings, "NOTIFY_WECOM_WEBHOOK_URL", "")

    _seed(db, title="重试消息")
    await db.commit()

    for attempt in range(1, notify.MAX_ATTEMPTS):
        sent, dead = await notify.dispatch_pending(db)
        assert (sent, dead) == (0, 0)
        msg = (await db.execute(__import__("sqlalchemy").select(OutboundMessage))).scalar_one()
        assert msg.status == "failed"
        assert msg.attempts == attempt

    sent, dead = await notify.dispatch_pending(db)
    assert (sent, dead) == (0, 1)
    msg = (await db.execute(__import__("sqlalchemy").select(OutboundMessage))).scalar_one()
    assert msg.status == "dead"

    # dead 不再被拾起
    sent, dead = await notify.dispatch_pending(db)
    assert (sent, dead) == (0, 0)


async def test_wecom_payload_shape(db, monkeypatch):
    """企业微信通道请求体格式：msgtype=text。"""
    import httpx

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = request.read()
        return httpx.Response(200, json={"errcode": 0})

    real_client_cls = httpx.AsyncClient

    def make_client(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client_cls(**kwargs)

    monkeypatch.setattr(notify.httpx, "AsyncClient", make_client)
    monkeypatch.setattr(notify.settings, "NOTIFY_WECOM_WEBHOOK_URL", "https://qyapi.weixin.qq.com/hook")
    monkeypatch.setattr(notify.settings, "NOTIFY_WEBHOOK_URL", "")

    _seed(db, title="候选通知", content="正文内容")
    await db.commit()
    await notify.dispatch_pending(db)

    assert captured["url"] == "https://qyapi.weixin.qq.com/hook"
    body = __import__("json").loads(captured["json"])
    assert body["msgtype"] == "text"
    assert "候选通知" in body["text"]["content"]
    assert "正文内容" in body["text"]["content"]


async def test_generic_webhook_carries_event_and_token(db, monkeypatch):
    """通用 Webhook：携带 event/接收方 id，令牌头存在。"""
    import httpx

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["json"] = request.read()
        return httpx.Response(200)

    real_client_cls = httpx.AsyncClient

    def make_client(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client_cls(**kwargs)

    monkeypatch.setattr(notify.httpx, "AsyncClient", make_client)
    monkeypatch.setattr(notify.settings, "NOTIFY_WECOM_WEBHOOK_URL", "")
    monkeypatch.setattr(notify.settings, "NOTIFY_WEBHOOK_URL", "https://ops.example/notify")
    monkeypatch.setattr(notify.settings, "NOTIFY_WEBHOOK_TOKEN", "secret-token")

    teacher = await make_teacher(db, "nt_teacher_b")
    _seed(db, event="tenant.application_received", title="新投递")
    await db.commit()
    # 补 tenant 维度
    msg = (await db.execute(__import__("sqlalchemy").select(OutboundMessage))).scalar_one()
    msg.teacher_id = teacher.id
    await db.commit()

    await notify.dispatch_pending(db)
    body = __import__("json").loads(captured["json"])
    assert body["event"] == "tenant.application_received"
    assert body["teacher_id"] == teacher.id
    assert captured["headers"].get("x-notify-token") == "secret-token"


async def test_batch_partial_failure_isolated(db, monkeypatch):
    """批内单条失败不拖垮其余消息：3 条中 1 条持续失败，另 2 条 sent。"""
    import httpx

    real_client_cls = httpx.AsyncClient

    def make_client(**kwargs):
        def handler(request: httpx.Request) -> httpx.Response:
            body = request.read().decode("utf-8")
            if "坏消息" in body:
                raise httpx.ConnectError("x")
            return httpx.Response(200)

        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client_cls(**kwargs)

    monkeypatch.setattr(notify.httpx, "AsyncClient", make_client)
    monkeypatch.setattr(notify.settings, "NOTIFY_WEBHOOK_URL", "https://hook.example")
    monkeypatch.setattr(notify.settings, "NOTIFY_WECOM_WEBHOOK_URL", "")

    _seed(db, title="好消息一")
    _seed(db, title="坏消息")
    _seed(db, title="好消息二")
    await db.commit()

    sent, dead = await notify.dispatch_pending(db)
    assert (sent, dead) == (2, 0)
    statuses = {
        m.title: m.status
        for m in (await db.execute(__import__("sqlalchemy").select(OutboundMessage))).scalars()
    }
    assert statuses == {"好消息一": "sent", "坏消息": "failed", "好消息二": "sent"}
