"""调度器出站投递接线测试（此前仅 dispatch_pending 有覆盖，_dispatch_outbound_once 无）。

验证三件事：
1. 拿到锁时正常消费 pending 消息并记日志；
2. 没拿到锁（其他 worker 持有）时静默跳过；
3. dispatch_pending 抛异常只留日志不外抛——投递故障不得影响调度节拍。
"""
import logging

import services.scheduler as scheduler


class _DummySession:
    """scheduler 只把 session 透传给 dispatch_pending，不真正使用。"""


def _fake_sessionmaker():
    """模拟 sessionmaker：可调用、返回 async 上下文管理器。"""

    class _Factory:
        def __call__(self):
            return _CM()

    return _Factory()


class _CM:
    async def __aenter__(self):
        return _DummySession()

    async def __aexit__(self, *args):
        return False


async def test_dispatch_outbound_once_consumes_pending(monkeypatch, caplog):
    async def lock_acquired(*args, **kwargs):
        return True

    monkeypatch.setattr(scheduler, "_acquire_schedule_lock", lock_acquired)
    monkeypatch.setattr(scheduler, "_get_sessionmaker", _fake_sessionmaker)
    calls = []

    async def fake_dispatch(session, *, batch_size=50):
        calls.append(session)
        return (3, 1)

    monkeypatch.setattr(scheduler, "dispatch_pending", fake_dispatch)
    with caplog.at_level(logging.INFO, logger="services.scheduler"):
        await scheduler._dispatch_outbound_once()

    assert len(calls) == 1
    assert any("outbound dispatch: sent=3 dead=1" in r.message for r in caplog.records)


async def test_dispatch_outbound_once_skips_without_lock(monkeypatch, caplog):
    async def lock_held(*args, **kwargs):
        return False

    monkeypatch.setattr(scheduler, "_acquire_schedule_lock", lock_held)
    called = []

    async def fake_dispatch(session, *, batch_size=50):
        called.append(session)
        return (0, 0)

    monkeypatch.setattr(scheduler, "dispatch_pending", fake_dispatch)
    await scheduler._dispatch_outbound_once()
    assert called == []


async def test_dispatch_outbound_once_swallows_failure(monkeypatch, caplog):
    async def lock_acquired(*args, **kwargs):
        return True

    monkeypatch.setattr(scheduler, "_acquire_schedule_lock", lock_acquired)
    monkeypatch.setattr(scheduler, "_get_sessionmaker", _fake_sessionmaker)

    async def broken_dispatch(session, *, batch_size=50):
        raise RuntimeError("redis down")

    monkeypatch.setattr(scheduler, "dispatch_pending", broken_dispatch)
    with caplog.at_level(logging.ERROR, logger="services.scheduler"):
        # 不应外抛：出站投递失败与业务调度是独立异常域
        await scheduler._dispatch_outbound_once()

    assert any("outbound dispatch failed" in r.message for r in caplog.records)
