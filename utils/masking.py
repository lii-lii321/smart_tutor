"""敏感信息掩码：教员侧展示订单原文时屏蔽手机号等联系方式。"""
import re

_MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_LANDLINE_RE = re.compile(r"(?<!\d)0\d{2,3}-?\d{7,8}(?!\d)")
_WECHAT_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9_-]{5,19}(?![A-Za-z0-9])")


def mask_contact_info(text: str | None) -> str:
    """掩码手机号/座机；微信号格式难精确识别，仅处理明确号码，避免误伤正常文本。"""
    if not text:
        return text or ""
    masked = _MOBILE_RE.sub(lambda m: m.group(0)[:3] + "****" + m.group(0)[-4:], text)
    masked = _LANDLINE_RE.sub(lambda m: m.group(0)[:4] + "****", masked)
    return masked
