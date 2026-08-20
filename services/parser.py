"""
AI 解析服务：DeepSeek 文本提取 + 高德地图地理编码。
"""
import json
import httpx
import re
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config import settings
from services.calculator import calculate_info_fee

SYSTEM_PROMPT = """你是一个专业的家教中介信息提取助手。从用户输入的微信聊天文本中，提取所有家教订单信息。

对于每条订单，提取以下字段：
1. raw_id: 原文编号（如 "✨✨2026081023"、"涨分🐶410"），若无则生成 "ITEM-01"
2. grade_subject: 年级与科目（如 "初三数学"、"大一高数"，用原文表述）
3. requirements: 对教员的要求，合并"要求"和"性别"字段（如 "985男大学生有经验，女生"）
4. price_total: 原始薪资文本，原样保留（如 "70-100/h"、"自带价"、"100/h"）
5. base_price: 每次课（按2h标准）的最高薪资，为数字。
   - "160-200/2h" → base_price=200
   - "70-100/h" 按2h算 → base_price=200
   - "100/h" 按2h算 → base_price=200
   - "自带价" 或无法提取 → base_price=0
6. weekly_frequency: 每周上课次数（数字，默认1。从"一周N次/上N休M/共N次课"推算）
7. is_summer_vacation: 是否暑期/寒假密集单（布尔，出现"暑假/暑期/寒假/密集/8月集中"等词为true）
8. address: 地址，需补全城市名（如 "成都市郫都区红光兰台府"、"成都市锦江区川师狮子山"）。
   若只有区名如"郫都区"则补全为"成都市郫都区"。
   重要：若标注了"#线上"或"线上教学"或地址明确指出"线上"，address 设为空字符串 ""。
   "学生上门"表示学生来老师处上课，不要把这部分填为 address，应提取学生的实际住址。
9. subway_remark: 地铁/交通备注，无则为null
10. lesson_count: 总课次数（数字。从"15次/共12次课/暑假15次"提取），无则为null
11. lesson_hours: 每次课时长（数字，默认2。从"上课时长：2h/两个小时"提取）

**输出格式**（纯JSON对象，无markdown）：
{"orders":[{"raw_id":"✨✨2026081023","grade_subject":"大一高数","requirements":"数学专业研究生，女生","price_total":"自带价","base_price":0,"weekly_frequency":2,"is_summer_vacation":true,"address":"成都市郫都区","subway_remark":null,"lesson_count":15,"lesson_hours":2}]}"""


REQUIRED_FIELDS = {"grade_subject"}  # base_price/address 允许服务端兜底处理


def _extract_base_price(price_total: str, lesson_hours: int = 2) -> float:
    """
    从原始薪资文本中提取每次课的最高薪资。
    不依赖 AI 做数学换算，服务端统一处理。

    规则：
    - "自带价" / "待定" / 空 → 0
    - "100/h" → 100 * lesson_hours
    - "70-100/h" → 100 * lesson_hours（取最高）
    - "160-200/2h" → 200
    - "200/次" → 200
    - 纯数字如 "200" → 200
    """
    if not price_total or "自带" in price_total or "待定" in price_total:
        return 0.0

    text = str(price_total).strip()

    # 范围格式: X-Y/单位 → 取 Y * 换算
    range_match = re.match(r'(\d+)\s*-\s*(\d+)\s*/\s*(\d*)\s*[hH小时]?', text)
    if range_match:
        high = float(range_match.group(2))
        hours = float(range_match.group(3) or 1)  # 分母的小时数，如 2h
        if hours > 0:
            return round(high / hours * lesson_hours, 2)
        return high

    # 单值/单位: X/单位 → X * 换算
    single_match = re.match(r'(\d+)\s*/\s*(\d*)\s*[hH小时]?', text)
    if single_match:
        val = float(single_match.group(1))
        hours = float(single_match.group(2) or 1)
        if hours > 0:
            return round(val / hours * lesson_hours, 2)
        return val

    # 纯数字
    pure_match = re.match(r'^(\d+\.?\d*)$', text)
    if pure_match:
        return float(pure_match.group(1))

    # 兜底: 尝试提取第一个数字
    any_num = re.findall(r'(\d+)', text)
    if any_num:
        return float(any_num[-1])  # 取最后一个（通常是最高价）

    return 0.0


def _is_online_order(item: dict) -> bool:
    text = " ".join(
        str(item.get(key) or "")
        for key in ("raw_text", "grade_subject", "requirements", "address", "subway_remark")
    )
    return any(token in text for token in ("#线上", "线上教学", "线上授课", "网课", "线上"))


def _looks_like_order_text(text: str) -> bool:
    normalized = text.strip()
    if not normalized:
        return False
    order_signals = (
        "学员地址", "学生地址", "地址", "辅导科目", "需求科目", "学生科目",
        "老师薪水", "薪资报价", "课时费", "薪酬", "费用",
    )
    non_order_signals = ("招聘线上暑假工", "小助手", "转发家教信息")
    if any(signal in normalized for signal in non_order_signals):
        return False
    return sum(1 for signal in order_signals if signal in normalized) >= 2


def _split_wechat_text(raw_text: str, max_chars: int = 3200) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []

    for line in raw_text.splitlines():
        if re.match(r"^\S+:\s*\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", line) and current:
            block = "\n".join(current).strip()
            if _looks_like_order_text(block):
                blocks.append(block)
            current = [line]
        else:
            current.append(line)

    tail = "\n".join(current).strip()
    if _looks_like_order_text(tail):
        blocks.append(tail)

    if not blocks and raw_text.strip():
        blocks = [raw_text.strip()]

    chunks: list[str] = []
    chunk = ""
    for block in blocks:
        if chunk and len(chunk) + len(block) + 2 > max_chars:
            chunks.append(chunk)
            chunk = block
        else:
            chunk = f"{chunk}\n\n{block}".strip()
    if chunk:
        chunks.append(chunk)

    return chunks


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((json.JSONDecodeError, httpx.HTTPError, ValueError)),
)
async def _call_deepseek(raw_text: str) -> list[dict]:
    """调用 DeepSeek API 解析微信文本，最多重试 3 次。"""
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            settings.DEEPSEEK_BASE_URL,
            headers={
                "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": raw_text},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
                "max_tokens": 8192,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        return _validate_and_parse(content)


def _validate_and_parse(content: str) -> list[dict]:
    """
    校验层：清洗 DeepSeek 输出 → 解析 JSON → 校验必填字段。
    处理 json_object 模式强制包装的 {"orders": [...]} 格式。
    """
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        snippet = content[:200]
        raise ValueError(f"AI 返回了无效的 JSON。内容预览：{snippet}")

    # json_object 模式强制输出对象，提取 orders/items/data 字段
    if isinstance(data, dict):
        orders = data.get("orders") or data.get("items") or data.get("data")
        if orders is None:
            for key in data:
                if isinstance(data[key], list):
                    orders = data[key]
                    break
            if orders is None:
                snippet = json.dumps(data, ensure_ascii=False)[:300]
                raise ValueError(f"AI 返回的 JSON 中找不到订单数组。内容：{snippet}")
        data = orders

    if not isinstance(data, list):
        raise ValueError(f"AI 返回了非预期的数据结构，预期订单数组。")

    if len(data) == 0:
        raise ValueError("AI 未从文本中识别出任何家教订单。请检查文本格式是否正确。")

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"第 {i + 1} 条订单格式异常。")
        missing = REQUIRED_FIELDS - set(item.keys())
        if missing:
            raise ValueError(
                f"第 {i + 1} 条订单缺少必填字段: {', '.join(missing)}。"
                f"请确保文本中包含「科目年级」「地址」信息。"
            )
        # 类型修正
        try:
            item["base_price"] = float(item.get("base_price", 0) or 0)
        except (TypeError, ValueError):
            item["base_price"] = 0.0
        item["weekly_frequency"] = int(item.get("weekly_frequency", 1) or 1)
        item["is_summer_vacation"] = bool(item.get("is_summer_vacation", False))
        item["lesson_count"] = item.get("lesson_count")  # 可为 null
        item["lesson_hours"] = int(item.get("lesson_hours", 2) or 2)
        # 确保字符串不为空
        if not item.get("grade_subject", "").strip():
            raise ValueError(f"第 {i + 1} 条订单的「年级科目」为空。")
        if not item.get("address", "").strip() and _is_online_order(item):
            item["address"] = "线上授课"
        # 补全 requirements
        if not item.get("requirements"):
            item["requirements"] = ""
        # price_total 默认值
        if not item.get("price_total"):
            item["price_total"] = "待定"
        if not item.get("raw_id"):
            item["raw_id"] = f"ITEM-{i + 1:02d}"

    return data


async def _geocode_address(address: str) -> tuple[float, float] | None:
    """调用高德地图地理编码 API，返回 (lng, lat) 或 None。"""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            settings.AMAP_GEOCODE_URL,
            params={
                "key": settings.AMAP_API_KEY,
                "address": address,
                "output": "JSON",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") != "1" or not data.get("geocodes"):
            return None
        location = data["geocodes"][0]["location"]
        lng_str, lat_str = location.split(",")
        return float(lng_str), float(lat_str)


async def parse_wechat_batch(raw_text: str) -> list[dict]:
    """
    主流程：
    1. DeepSeek 解析微信文本 → JSON 数组
    2. 每条订单调高德地图获取坐标
    3. 使用精确坐标展示地图位置
    4. 调用精算模块计算信息费（自带价跳过）
    5. 返回预览数据
    """
    chunks = _split_wechat_text(raw_text)
    parsed: list[dict] = []
    errors: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        try:
            parsed.extend(await _call_deepseek(chunk))
        except Exception as e:
            errors.append(f"第 {index} 段解析失败：{e}")

    if not parsed:
        if errors:
            raise ValueError("；".join(errors[:3]))
        raise ValueError("未从文本中识别出任何家教订单。")

    results = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        if not item.get("grade_subject"):
            continue

        # 服务端重新计算 base_price（不依赖 AI 做数学）
        lesson_hours = item.get("lesson_hours", 2) or 2
        price_total = item.get("price_total", "") or ""
        server_base_price = _extract_base_price(price_total, lesson_hours)

        # 以服务端计算结果为准；若 AI 算对了也保留，但服务端优先
        if server_base_price > 0:
            item["base_price"] = server_base_price
        elif item.get("base_price", 0) > 0:
            server_base_price = item["base_price"]
        else:
            item["base_price"] = 0
            server_base_price = 0

        is_online = _is_online_order(item)

        if not item.get("address", "").strip():
            if is_online:
                item["address"] = "线上授课"
            else:
                continue

        # 地理编码
        coords = None if is_online else await _geocode_address(item["address"])
        if coords:
            lng, lat = coords
        elif is_online:
            lng, lat = 104.0668, 30.5728
        else:
            lng, lat = 0.0, 0.0

        # 精算（自带价跳过计算，标记为待定价）
        if server_base_price > 0:
            try:
                fee = calculate_info_fee(
                    base_price=server_base_price,
                    weekly_frequency=item.get("weekly_frequency", 1),
                    is_summer_vacation=item.get("is_summer_vacation", False),
                )
            except ValueError:
                fee = {"total_info_fee": 0, "deposit": 0, "balance": 0}
        else:
            fee = {"total_info_fee": 0, "deposit": 0, "balance": 0}

        results.append({
            "raw_id": item["raw_id"],
            "raw_text": raw_text,
            "grade_subject": item["grade_subject"],
            "requirements": item.get("requirements", ""),
            "price_total": item.get("price_total", "待定"),
            "base_price": server_base_price,
            "weekly_frequency": item.get("weekly_frequency", 1),
            "is_summer_vacation": item.get("is_summer_vacation", False),
            "address": "线上授课" if is_online else item["address"],
            "subway_remark": item.get("subway_remark") or ("线上授课" if is_online else None),
            "lesson_count": item.get("lesson_count"),
            "lesson_hours": item.get("lesson_hours", 2),
            "lng": lng,
            "lat": lat,
            "fuzzy_address": "线上授课" if is_online else item["address"],
            "calculated_info_fee": fee["total_info_fee"],
            "deposit_amount": fee["deposit"],
            "balance_amount": fee["balance"],
            "needs_manual_price": server_base_price <= 0,  # 前端据此显示"需手动定价"
        })

    if not results:
        raise ValueError("AI 未识别出可导入的有效家教订单，请检查文本中是否包含地址、科目和薪资。")

    return results
