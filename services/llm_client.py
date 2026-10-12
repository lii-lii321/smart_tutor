"""
DeepSeek Chat 通用调用封装：services/parser.py 同款模式（json_object / tenacity
只重试传输与解析错误 / AI 派生内容落日志先掩码），供 AI 找单、知识库问答等新
AI 能力复用。

parser.py 保持自包含不迁移（窄改原则）；新增 AI 能力一律走本模块，避免每个
服务各带一份 HTTP 调用样板。校验类失败抛 LLMBadResponseError（ValueError 子类），
路由层与 batch-parse 同契约转 422。
"""
import json
import logging

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings
from utils.masking import mask_contact_info

logger = logging.getLogger(__name__)


class LLMBadResponseError(ValueError):
    """AI 返回无法解析/结构不符合预期：确定性结果，不重试，由路由层转 422。"""


def _strip_code_fence(content: str) -> str:
    content = content.strip()
    if not content.startswith("```"):
        return content
    lines = content.split("\n")[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    # 与 parser._deepseek_once 同口径：只重试网络/传输错误与 JSON 解析错误；
    # 校验类 ValueError 是确定性结果，重试只会按原输入重复烧 AI 调用费
    retry=retry_if_exception_type((json.JSONDecodeError, httpx.HTTPError)),
)
async def _chat_once(
    client: httpx.AsyncClient,
    *,
    system: str,
    user: str,
    json_mode: bool,
    temperature: float,
    max_tokens: int,
) -> str:
    body: dict = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    resp = await client.post(
        settings.DEEPSEEK_BASE_URL,
        headers={
            "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
            "Content-Type": "application/json",
        },
        json=body,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def _chat(
    *,
    system: str,
    user: str,
    json_mode: bool,
    temperature: float,
    max_tokens: int,
) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        return await _chat_once(
            client,
            system=system,
            user=user,
            json_mode=json_mode,
            temperature=temperature,
            max_tokens=max_tokens,
        )


async def chat_json(
    system: str,
    user: str,
    *,
    temperature: float = 0.1,
    max_tokens: int = 2048,
) -> dict:
    """结构化提取：强制 json_object 输出并解析为 dict；解析失败抛 LLMBadResponseError。"""
    content = await _chat(
        system=system, user=user, json_mode=True, temperature=temperature, max_tokens=max_tokens
    )
    try:
        data = json.loads(_strip_code_fence(content))
    except json.JSONDecodeError as e:
        # AI 输出可能派生自含敏感信息的原文：落日志前先掩码
        logger.warning("AI 返回无效 JSON：%s", mask_contact_info(content[:200]))
        raise LLMBadResponseError("AI 返回了无法解析的内容，请稍后重试。") from e
    if not isinstance(data, dict):
        raise LLMBadResponseError("AI 返回了非预期的数据结构，请稍后重试。")
    return data


async def chat(
    system: str,
    user: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 1024,
) -> str:
    """自由文本生成（知识库问答等）；返回去空白后的回答正文。"""
    content = await _chat(
        system=system, user=user, json_mode=False, temperature=temperature, max_tokens=max_tokens
    )
    return content.strip()
