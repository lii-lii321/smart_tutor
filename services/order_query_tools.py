"""
AI 找单 · 条件解析：自然语言 → 结构化查询条件。

本模块只做"人话 → 条件 JSON"，不含任何数据库访问；SQL 执行在
services/order_search.py。两段物理隔离：LLM 输出只能以规范化后的
条件字典（键白名单 + 类型收敛）流向查询层，提示注入无法携带任何
查询语义。科目/年级归一复用推荐服务的别名表，保证与推荐同口径。
"""

import logging

from services.llm_client import chat_json
from services.recommendation import (
    SUBJECT_ALIASES,
    extract_grade,
    extract_subject,
    extract_subjects,
)

logger = logging.getLogger(__name__)

FIND_ORDER_SYSTEM_PROMPT = """你是家教中介的找单条件解析助手。把用户用自然语言描述的找单需求解析为 JSON 查询条件。

可提取的条件：
1. subject: 科目，只能取：数学/英语/语文/物理/化学/生物/历史/地理/政治，无法判断则为 null
2. grade: 学段，只能取：小学/初中/高中，无法判断则为 null
3. min_base_price: 单次课最低课酬（数字），无法判断则为 null
4. max_base_price: 单次课最高课酬（数字），无法判断则为 null
5. weekly_frequency: 每周上课次数（数字），仅在用户提到频次时提取（"一周3次""每周两次"→3/2），否则为 null
6. radius_km: 距离半径（公里，数字），仅当用户提到具体距离时提取，否则为 null
7. anchor: 地点文本（如"武侯区""天府广场"），保留用户原文；仅当用户提到具体地点时提取，否则为 null。
   地点很重要：用户提到地点就提取，不论是否同时提到距离——"武侯区的英语单"也按区域过滤。

价格口径换算（重要，系统按"每次课=2小时"存储课酬）：
- "时薪 X""X 元/小时""X/h" → 最低/最高课酬 = X*2
- "一次课 X 元""X 元/2h""X/次" → 直接取 X
- 未注明口径的"X 以上/X 以内" → 按单次课价格直接采用
- 例子："时薪 80 以上" → min_base_price=160；"100 以内的初三数学" → max_base_price=100

地点与半径：用户说"附近"但没说参照哪里时，anchor 为 null（后续会向用户追问）。

只输出 JSON 对象，无任何其他内容：
{"subject":null,"grade":null,"min_base_price":null,"max_base_price":null,"weekly_frequency":null,"radius_km":null,"anchor":null}"""

_MAX_RADIUS_KM = 50.0
_MAX_WEEKLY_FREQUENCY = 14


def _coerce_optional_float(value) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num if num > 0 else None


def _coerce_weekly_frequency(value) -> int | None:
    try:
        freq = int(float(value))
    except (TypeError, ValueError):
        return None
    return freq if 1 <= freq <= _MAX_WEEKLY_FREQUENCY else None


def _normalize_subject(raw: str | None, warnings: list[str]) -> str | None:
    """LLM 科目 → 别名表规范名；对不上号时降级为忽略该项而非报错（宁宽勿漏）。"""
    text = (raw or "").strip()
    if not text:
        return None
    if text in SUBJECT_ALIASES:
        return text
    normalized = extract_subject(text)
    if normalized:
        return normalized
    warnings.append(f"科目「{text}」暂未收录，已忽略科目条件")
    return None


def _normalize_grade(raw: str | None, warnings: list[str]) -> str | None:
    text = (raw or "").strip()
    if not text:
        return None
    normalized = extract_grade(text)
    if normalized:
        return normalized
    warnings.append(f"学段「{text}」未识别，已忽略学段条件")
    return None


async def parse_find_order_conditions(query_text: str) -> tuple[dict, list[str]]:
    """
    自然语言 → 规范化条件。识别不出任何条件时抛 ValueError（路由转 422），
    单项识别失败只降级进 warnings，不整体失败。
    """
    data = await chat_json(FIND_ORDER_SYSTEM_PROMPT, f"用户需求：{query_text}")

    warnings: list[str] = []
    conditions: dict = {
        "subject": _normalize_subject(data.get("subject"), warnings),
        "grade": _normalize_grade(data.get("grade"), warnings),
        "min_base_price": _coerce_optional_float(data.get("min_base_price")),
        "max_base_price": _coerce_optional_float(data.get("max_base_price")),
        "weekly_frequency": _coerce_weekly_frequency(data.get("weekly_frequency")),
        "radius_km": None,
        "anchor": (data.get("anchor") or "").strip() or None,
    }

    radius = _coerce_optional_float(data.get("radius_km"))
    if radius is not None:
        conditions["radius_km"] = min(radius, _MAX_RADIUS_KM)
        if radius > _MAX_RADIUS_KM:
            warnings.append(f"距离半径超出上限，已按 {_MAX_RADIUS_KM:g} 公里处理")

    if (
        conditions["subject"] is None
        and conditions["grade"] is None
        and conditions["min_base_price"] is None
        and conditions["max_base_price"] is None
        and conditions["anchor"] is None
        and conditions["radius_km"] is None
    ):
        raise ValueError("未能从描述中识别出筛选条件，请至少说明科目、年级、价格或位置。")

    conditions = {key: value for key, value in conditions.items() if value is not None}
    return conditions, warnings


async def resolve_anchor(
    anchor: str | None, radius_km: float | None, warnings: list[str]
) -> tuple[float, float] | None:
    """参照地点 → 坐标（复用地理编码 Redis 缓存）；编码失败降级为忽略距离条件。"""
    if not anchor or radius_km is None:
        return None
    from services.parser import geocode_address

    point = await geocode_address(anchor)
    if point is None:
        warnings.append(f"未能识别位置「{anchor}」，已忽略距离条件，改为按「{anchor}」区域匹配")
    return point


def match_conditions(order, conditions: dict, now) -> bool:
    """
    精筛一条候选订单（过期/科目/年级/频次/价格/区域）。科目/年级口径与推荐
    服务一致：从年级科目+教员要求做别名包含匹配。

    地点条件的两种形态：
    - 带 radius_km：距离过滤（search_orders 按锚点坐标算），此处不管；
    - 不带 radius_km：区域包含匹配——anchor 文本须出现在 fuzzy_address 里
      （录单规范要求地址补全区县，如"成都市武侯区桐梓林片区"含"武侯区"）。
    """
    if order.expired_at is not None and order.expired_at <= now:
        return False

    text = f"{order.grade_subject} {order.requirements or ''}"
    subject = conditions.get("subject")
    if subject and subject not in extract_subjects(text):
        return False
    grade = conditions.get("grade")
    if grade and extract_grade(order.grade_subject) != grade:
        return False

    weekly = conditions.get("weekly_frequency")
    if weekly is not None and (order.weekly_frequency or 1) != weekly:
        return False

    anchor = conditions.get("anchor")
    if anchor and "radius_km" not in conditions and anchor not in (order.fuzzy_address or ""):
        return False

    min_price = conditions.get("min_base_price")
    if min_price is not None and float(order.base_price) < min_price:
        return False
    max_price = conditions.get("max_base_price")
    return not (max_price is not None and float(order.base_price) > max_price)
