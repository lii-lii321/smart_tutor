"""DeepSeek 调用重试语义测试（此前 3 次重试循环零覆盖）。

核心契约（services/parser.py @retry 装饰器）：
- 网络类错误（httpx.HTTPError）→ 重试，最多 3 次；
- 校验类错误（ValueError，如 AI 返回无法解析的内容）→ 立即失败不重试
  （重试只会按原输入重复烧 AI 调用费）；
- 出境原文先掩码：家长手机号不出现在请求体里。
"""
import json

import httpx
import pytest

from services import parser
from utils.masking import mask_contact_info

RAW_TEXT = "联系家长 13912345678，地址天府大道，初三数学 200/次"


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    """记录请求体并按脚本逐次抛错/返回；支持 async with（_call_deepseek 的用法）。"""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.request_bodies: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        self.request_bodies.append(json or {})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _ai_payload(text: str) -> _FakeResponse:
    # 校验层要求 orders 非空且含 grade_subject；空数组会触发"未识别订单"的 ValueError
    return _FakeResponse({
        "choices": [{"message": {"content": json.dumps({"orders": [{"grade_subject": "初三数学"}]})}}]
    })


async def test_retry_on_network_error_then_success(monkeypatch):
    # 第一次连接失败（可重试），第二次成功 → 总调用 2 次
    client = _FakeClient(httpx.ConnectError("boom"), _ai_payload("[]"))
    monkeypatch.setattr(parser.httpx, "AsyncClient", lambda timeout: client)

    items = await parser._call_deepseek(RAW_TEXT)
    assert len(items) == 1
    assert items[0]["grade_subject"] == "初三数学"
    assert len(client.request_bodies) == 2


async def test_no_retry_on_validation_error(monkeypatch):
    # AI 返回坏 JSON → ValueError 确定性失败，不烧第二次调用费
    client = _FakeClient(_FakeResponse({"choices": [{"message": {"content": "not-json"}}]}))
    monkeypatch.setattr(parser.httpx, "AsyncClient", lambda timeout: client)

    with pytest.raises(ValueError):
        await parser._deepseek_once(client, RAW_TEXT, "通用微信格式")
    assert len(client.request_bodies) == 1


async def test_outbound_text_is_masked(monkeypatch):
    # 家长手机号在出境前必须被掩码替换
    client = _FakeClient(_ai_payload("[]"))
    monkeypatch.setattr(parser.httpx, "AsyncClient", lambda timeout: client)

    await parser._deepseek_once(client, RAW_TEXT, "通用微信格式")
    sent = json.dumps(client.request_bodies[0], ensure_ascii=False)
    assert "13912345678" not in sent
    assert mask_contact_info(RAW_TEXT) in sent
