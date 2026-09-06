"""敏感信息掩码：教员侧展示订单原文时屏蔽手机号/座机/微信号/QQ 号。"""
import re

# 兼容带空格/横线分隔的号码（如 138 0000 0001、139-0000-0002）
_MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_MOBILE_SEPARATED_RE = re.compile(r"(?<!\d)1[3-9]\d[\s-]\d{4}[\s-]\d{4}(?!\d)")
_LANDLINE_RE = re.compile(r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)")
# 仅匹配带有明确前缀的联系方式（微信号：xxx / WX: xxx / QQ：123456），
# 避免把英文单词误伤成掩码
_WECHAT_ID_RE = re.compile(
    r"(微信|微信号|weixin|wechat|WX|VX|wx|vx)(号|ID|Id|id)?([:：\s]+)([A-Za-z][A-Za-z0-9_-]{5,19})"
)
_QQ_RE = re.compile(r"(?i)(qq|扣扣|企鹅)(号)?([:：\s]+)(\d{5,11})")


def _mask_id(value: str) -> str:
    if len(value) <= 4:
        return value[0] + "***"
    return value[:2] + "****" + value[-2:]


def mask_contact_info(text: str | None) -> str:
    """掩码手机号/座机/带前缀的微信号与 QQ 号，家长联系方式只能通过地址解锁卡点获取。"""
    if not text:
        return text or ""

    def _sub_wechat(m: re.Match) -> str:
        return f"{m.group(1)}{m.group(2) or ''}{m.group(3)}{_mask_id(m.group(4))}"

    masked = _MOBILE_SEPARATED_RE.sub(
        lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:].replace(" ", "").replace("-", ""),
        text,
    )
    masked = _MOBILE_RE.sub(lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:], masked)
    masked = _LANDLINE_RE.sub(lambda m: m.group(0)[:4] + "****", masked)
    masked = _WECHAT_ID_RE.sub(_sub_wechat, masked)
    masked = _QQ_RE.sub(lambda m: f"{m.group(1)}{m.group(2) or ''}{m.group(3)}{_mask_id(m.group(4))}", masked)
    return masked
