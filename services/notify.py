"""
触达通道：站内信之外的出站推送（企业微信群机器人 / 通用 Webhook / 日志兜底）。

设计（为什么走队列而不是请求内直发）：
- 出站消息先落 outbound_messages 表，与站内信**同事务提交**——业务回滚时
  不会发出"假通知"；
- scheduler 每隔 NOTIFY_DISPATCH_INTERVAL 秒调 dispatch_pending() 异步投递，
  通道故障消息留痕（failed + last_error），重试 3 次耗尽转 dead 人工排查；
- 投递失败绝不反噬业务事务：所有通道异常在 dispatch 内消化。

通道开关（均为选填，未配置的通道自动跳过）：
- NOTIFY_WECOM_WEBHOOK_URL  企业微信群机器人（中介运营最常用，秒级触达）
- NOTIFY_WEBHOOK_URL        通用 Webhook（POST JSON，配 NOTIFY_WEBHOOK_TOKEN 做简单鉴权）
- 日志通道                  恒开：未配任何通道时保证"通知去过哪"可观测。

短信/微信订阅消息：接口已留（Channel 协议 + 接收方解析），凭证与模板报备
到位后按 LogChannel 的样子补一个 Channel 实现即可，投递与重试逻辑复用。
"""
import logging
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from models.domain import OutboundMessage
from utils.clock import utcnow

logger = logging.getLogger(__name__)

# 单条消息最大尝试次数：耗尽后转 dead（人工排查），不再自动重试
MAX_ATTEMPTS = 3
# 单通道 HTTP 超时（秒）：触达是尽力而为，不能拖住调度循环
HTTP_TIMEOUT = 5.0


def queue_outbound(
    db: AsyncSession,
    *,
    event: str,
    title: str,
    content: str | None = None,
    teacher_id: int | None = None,
    tenant_id: int | None = None,
) -> None:
    """把出站消息写进队列（与业务同事务提交）。纯入库，无 IO，任何调用点都安全。"""
    db.add(
        OutboundMessage(
            event=event[:50],
            title=title[:50],
            content=(content or "")[:255] or None,
            teacher_id=teacher_id,
            tenant_id=tenant_id,
        )
    )


def build_text(msg: OutboundMessage) -> str:
    """统一的消息文本格式：标题 + 正文，通道侧不再各自拼接。"""
    return f"{msg.title}\n{msg.content}" if msg.content else msg.title


async def _post_wecom(url: str, msg: OutboundMessage, client: httpx.AsyncClient) -> None:
    """企业微信群机器人格式：text 消息体，markdown 换行语义与纯文本一致。"""
    resp = await client.post(url, json={"msgtype": "text", "text": {"content": build_text(msg)}})
    resp.raise_for_status()


async def _post_generic(
    url: str, token: str | None, msg: OutboundMessage, client: httpx.AsyncClient
) -> None:
    """通用 Webhook：自有 JSON 结构，接收方按 event 字段路由；可选令牌头鉴权。"""
    headers = {"X-Notify-Token": token} if token else None
    payload: dict[str, Any] = {
        "event": msg.event,
        "title": msg.title,
        "content": msg.content,
        "teacher_id": msg.teacher_id,
        "tenant_id": msg.tenant_id,
    }
    resp = await client.post(url, json=payload, headers=headers)
    resp.raise_for_status()


def _active_channels() -> list[str]:
    """当前配置启用的网络通道（日志通道恒在但不计入，避免掩盖网络通道失败）。"""
    channels = []
    if settings.NOTIFY_WECOM_WEBHOOK_URL:
        channels.append("wecom")
    if settings.NOTIFY_WEBHOOK_URL:
        channels.append("webhook")
    return channels


async def _deliver(msg: OutboundMessage) -> tuple[bool, str]:
    """把一条消息投到所有已启用通道。

    返回 (是否成功, 结果摘要)。语义：
    - 未配置任何网络通道 → 日志兜底即视为成功（本地开发/未开通触达时消息有处可查）；
    - 配置了网络通道 → 任一通道成功即算成功，全部失败才算失败（下轮重试）。
    通道异常在内部消化，不外抛。
    """
    channels = _active_channels()
    if not channels:
        logger.info("outbound #%s [%s] log-only: %r", msg.id, msg.event, build_text(msg))
        return (True, "log")

    errors: list[str] = []
    delivered: list[str] = []
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        if "wecom" in channels:
            try:
                await _post_wecom(settings.NOTIFY_WECOM_WEBHOOK_URL, msg, client)
                delivered.append("wecom")
            except Exception as exc:
                errors.append(f"wecom: {exc}")
        if "webhook" in channels:
            try:
                await _post_generic(
                    settings.NOTIFY_WEBHOOK_URL, settings.NOTIFY_WEBHOOK_TOKEN, msg, client
                )
                delivered.append("webhook")
            except Exception as exc:
                errors.append(f"webhook: {exc}")

    if delivered:
        logger.info(
            "outbound #%s [%s] delivered=%s failed_channels=%s text=%r",
            msg.id, msg.event, delivered, errors or "-", build_text(msg),
        )
        return (True, ",".join(delivered))
    logger.warning("outbound #%s [%s] all channels failed: %s", msg.id, msg.event, "; ".join(errors))
    return (False, "; ".join(errors)[:255])


async def dispatch_pending(db: AsyncSession, *, batch_size: int = 50) -> tuple[int, int]:
    """
    投递一批待发/待重试消息（scheduler 周期调用；也可测试直调）。

    返回 (sent, dead)。单条失败不中断整批：标记 failed/attempts+1，
    超过 MAX_ATTEMPTS 转 dead（人工排查，不再自动重试）。
    批内消息串行投递——量级小（每天几十条），串行足够且避免打爆接收方。
    """
    result = await db.execute(
        select(OutboundMessage)
        .where(OutboundMessage.status.in_(["pending", "failed"]))
        .order_by(OutboundMessage.id)
        .limit(batch_size)
    )
    pending = result.scalars().all()
    if not pending:
        return (0, 0)

    sent = dead = 0
    for msg in pending:
        ok, detail = await _deliver(msg)
        if ok:
            msg.status = "sent"
            msg.sent_at = utcnow()
            msg.last_error = None
            sent += 1
        else:
            msg.attempts += 1
            msg.last_error = detail
            if msg.attempts >= MAX_ATTEMPTS:
                msg.status = "dead"
                dead += 1
            else:
                msg.status = "failed"
    await db.commit()
    return (sent, dead)
