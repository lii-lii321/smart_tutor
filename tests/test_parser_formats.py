from services.parser import _parse_labeled_orders, extract_order_block, parse_wechat_batch


def test_parse_labeled_chengdu_tutor_order():
    raw_text = """
💎【成都家教000001】
联系地址： 成华区示例小区-1栋
年级性别： 初一升初二
辅导科目： 数学英语物理（各一位）
时间安排： 8月试课 开学后各周末1-2次课 每次2小时
教员要求： 有经验的 发音标准 性别不限
薪资待遇： 70元/小时
"""

    orders, _failed = _parse_labeled_orders(raw_text)

    assert len(orders) == 1
    assert orders[0]["raw_id"] == "成都家教000001"
    assert orders[0]["address"] == "成华区示例小区-1栋"
    assert orders[0]["grade_subject"] == "初一升初二 数学英语物理（各一位）"
    assert orders[0]["price_total"] == "70元/小时"
    assert orders[0]["base_price"] == 140
    assert orders[0]["weekly_frequency"] == 2
    assert orders[0]["lesson_hours"] == 2
    assert "成都家教000001" in orders[0]["raw_text"]


def test_parse_id_block_orders_are_split_exactly():
    raw_text = """
🟥【成都家教 84590346】
联系地址：双流区天府数智谷西门地下停车场-出入口
年级性别：预初二，男
辅导科目：作业辅导
学员情况：娃娃基础比较好，主要做作业自觉性差点，需要旁边有人守
时间安排：开学周六日选一天上午8：30-12：00 。#上课一小时，语文英语皆可，其余两个半小时监督指导批改娃娃作业
教员要求：男女皆可，有耐心，  认真负责品行好 语文英语好的
薪资待遇：135元/3.5小时

🟥【成都家教 77412637】
联系地址：双流区海昌路附近
年级性别：初二
辅导科目：物理
学员情况：初二物理
时间安排：一周1次，一次2小时 开学周末上课
教员要求：男女皆可，有家教经验，有耐心，负责任，一本院校
薪资待遇：80元/小时

🟥成都家教082202#加急
【年级性别】：新初三 男
【补习科目】：语数英陪学，不讲课
【补习时间】：开学前一周天天都需要，每次4小时，近期开始：九点或十点开始，下午两点或者三点开始；#中午需自己回家午休两小时
【地址】：双流区华阳南阳盛世附近
【对老师要求】:男/女老师均可，经验丰富，性格开朗，认真负责
【薪资】：200元一天
"""

    orders, _failed = _parse_labeled_orders(raw_text)

    assert len(orders) == 3
    assert [order["raw_id"] for order in orders] == [
        "成都家教84590346",
        "成都家教77412637",
        "成都家教082202",
    ]
    assert orders[0]["price_total"] == "135元/3.5小时"
    assert orders[1]["price_total"] == "80元/小时"
    assert orders[2]["price_total"] == "200元一天"
    assert orders[0]["needs_manual_price"] is True
    assert orders[1]["needs_manual_price"] is False
    assert orders[2]["needs_manual_price"] is True
    assert "成都家教77412637" not in orders[0]["raw_text"]
    assert "成都家教84590346" not in orders[1]["raw_text"]


def test_parse_multiple_orders_with_preamble_and_noise():
    raw_text = """
#新都家教单
这里是群里转发的摘要，不是订单正文。

🚗【成都家教 58147046】
联系地址：新都区大都保峰玖著
年级性别：准初二，男
辅导科目：数学
学员情况：成绩120+
时间安排：8月可以上几天 开学后一周1次周末上课 每次2小时
教员要求：男女皆可，有家教经验，有耐心，负责任，一本院校
薪资待遇：80元/小时

一些无关说明，中间不要当成单子。

🚗【成都家教 61201156】
联系地址：新都区廖家湾
年级性别：预初一，女
辅导科目：数学,英语
学员情况：一个人带两科最好
时间安排：一周1次，一次2小时 开学周末上课
教员要求：女，有家教经验，有耐心，负责任，一本院校
薪资待遇：70元/小时

🚗【成都家教082001】
联系地址：新都区 木锦新城
年级性别：准三年级 男孩
辅导科目：语数英
学员情况：数学为主 语英顺带
时间安排：暑假8月 每周4次，一次2小时 开学待定
教员要求：有经验的老师
薪资待遇：60元/小时
"""

    orders, _failed = _parse_labeled_orders(raw_text)

    assert len(orders) == 3
    assert [order["raw_id"] for order in orders] == [
        "成都家教58147046",
        "成都家教61201156",
        "成都家教082001",
    ]
    assert orders[0]["grade_subject"] == "准初二，男 数学"
    assert orders[1]["grade_subject"] == "预初一，女 数学,英语"
    assert orders[2]["grade_subject"] == "准三年级 男孩 语数英"
    assert orders[0]["price_total"] == "80元/小时"
    assert orders[1]["weekly_frequency"] == 1
    assert orders[2]["weekly_frequency"] == 4
    assert "成都家教61201156" not in orders[0]["raw_text"]
    assert "成都家教58147046" not in orders[1]["raw_text"]
    assert "成都家教082001" not in orders[1]["raw_text"]


def test_parsed_order_keeps_only_its_own_raw_text():
    raw_text = """
【成都家教042004】
联系地址：双流区悦榕东方
年级性别：预一年级 男孩
辅导科目：数学
学员情况：数学启蒙 实验游戏等
时间安排：每周1-2次，一次1小时  开学后上课
教员要求：有经验的 #理工科男生
薪资待遇：80元/小时

【成都家教 77845931】
联系地址：双流区华阳海昌路
年级性别：一升二年级 男孩
辅导科目：语数英
学员情况：主要作业辅导
时间安排：开学周1-5每周2-3次 每次2小时 晚上5-7点上课
教员要求：师范专业的   性别都可以  #有低年级的家教经验
薪资待遇：50元/1小时
"""

    orders, _failed = _parse_labeled_orders(raw_text)

    assert len(orders) == 2
    assert orders[0]["raw_id"] == "成都家教042004"
    assert orders[1]["raw_id"] == "成都家教77845931"
    assert "成都家教77845931" not in orders[0]["raw_text"]
    assert "双流区华阳海昌路" not in orders[0]["raw_text"]
    assert "成都家教042004" not in orders[1]["raw_text"]
    assert "双流区悦榕东方" not in orders[1]["raw_text"]


async def _parse_batch_keeps_split_raw_text():
    raw_text = """
【成都家教042004】
联系地址：双流区悦榕东方
年级性别：预一年级 男孩
辅导科目：数学
学员情况：数学启蒙 实验游戏等
时间安排：每周1-2次，一次1小时  开学后上课
教员要求：有经验的 #理工科男生
薪资待遇：80元/小时

【成都家教 77845931】
联系地址：双流区华阳海昌路
年级性别：一升二年级 男孩
辅导科目：语数英
学员情况：主要作业辅导
时间安排：开学周1-5每周2-3次 每次2小时 晚上5-7点上课
教员要求：师范专业的   性别都可以  #有低年级的家教经验
薪资待遇：50元/1小时
"""

    orders, warnings = await parse_wechat_batch(raw_text)

    assert len(orders) == 2
    assert warnings == []
    assert "成都家教77845931" not in orders[0]["raw_text"]
    assert "双流区华阳海昌路" not in orders[0]["raw_text"]
    assert "成都家教042004" not in orders[1]["raw_text"]
    assert "双流区悦榕东方" not in orders[1]["raw_text"]


def test_parse_batch_keeps_split_raw_text():
    import asyncio

    asyncio.run(_parse_batch_keeps_split_raw_text())


async def test_parse_headless_multi_order_falls_back_to_ai(monkeypatch):
    """无头多单粘贴（轻量解析会合并成一条）必须转 AI 解析，避免静默丢单。"""
    from services import parser

    raw_text = """
联系地址：双流区悦榕东方
年级：预一年级 男孩
科目：数学
薪资待遇：80元/小时

联系地址：锦江区万科城
年级：一升二年级 男孩
科目：语数英
薪资待遇：50元/1小时
"""
    # 无头文本 → labeled 解析合并成 1 条；断言触发 AI 兜底并返回两单
    labeled, _labeled_failed = parser._parse_labeled_orders(raw_text)
    assert len(labeled) == 1, "前置假设：无头多单被轻量解析合并为一条"

    async def fake_deepseek(text, source_profile=""):
        # AI 按语义返回两单；断言触发时机正确（无头多单文本）
        assert parser._looks_like_multi_order(text)
        return [
            {"raw_id": "AI-001", "grade_subject": "预一年级 数学", "address": "双流区悦榕东方", "price_total": "80元/小时"},
            {"raw_id": "AI-002", "grade_subject": "一升二年级 语数英", "address": "锦江区万科城", "price_total": "50元/1小时"},
        ]

    monkeypatch.setattr(parser, "_call_deepseek", fake_deepseek)
    orders, warnings = await parser.parse_wechat_batch(raw_text)

    assert len(orders) == 2, "无头多单必须逐单解析，不得合并丢失"
    assert {o["raw_id"] for o in orders} == {"AI-001", "AI-002"}
    # AI 条目原文 = 所属段文本（本例单段即全量文本，但绝不允许为空或错位）
    assert orders[0]["raw_text"] == raw_text.strip()
    assert warnings == []


async def test_parse_partial_failure_surfaces_warning(monkeypatch):
    """部分段 AI 失败：成功段照常返回，失败原因进 warnings（不再静默吞掉）。"""
    from services import parser

    async def fake_deepseek(text, source_profile=""):
        if "可解析段" in text:
            return [
                {"raw_id": "OK-001", "grade_subject": "一年级 数学", "address": "双流区悦榕东方", "price_total": "80元/小时"}
            ]
        raise RuntimeError("network down")

    monkeypatch.setattr(parser, "_call_deepseek", fake_deepseek)
    # 强制走 AI 路径，并把切分固定为两段（第二段模拟 AI 故障）
    monkeypatch.setattr(parser, "_parse_labeled_orders", lambda _t, _p=None: ([], []))
    monkeypatch.setattr(parser, "_split_wechat_text", lambda _t, max_chars=3200: ["第一段可解析段", "第二段故障段"])
    orders, warnings = await parser.parse_wechat_batch("任意文本")

    assert len(orders) == 1, "成功段照常返回"
    # AI 条目原文 = 所属段，绝不回退到整批文本（多段场景防交叉泄露）
    assert orders[0]["raw_text"] == "第一段可解析段"
    assert warnings and "AI 服务暂时不可用" in warnings[0]





async def _validate_null_grade_subject_raises_value_error():
    """AI 返回 grade_subject 显式 null 时应抛 ValueError（面向用户的校验失败），而非 AttributeError。"""
    import json

    from services.parser import _validate_and_parse

    content = json.dumps({"orders": [{"grade_subject": None, "address": "成都", "raw_id": "N-1"}]}, ensure_ascii=False)
    try:
        _validate_and_parse(content)
    except ValueError as e:
        assert "年级科目" in str(e)
        return
    raise AssertionError("null 年级科目应触发面向用户的校验失败")


def test_validate_null_grade_subject_raises_value_error():
    import asyncio

    asyncio.run(_validate_null_grade_subject_raises_value_error())


def test_extract_order_block_picks_own_block():
    """混合多单文本按单号截取自身块（修复整段混入其他订单的问题）。"""
    text = (
        "【成都家教 58147046】\n联系地址：新都区大都保峰玖著\n辅导科目：数学\n"
        "【成都家教 61201156】\n联系地址：新都区廖家湾\n辅导科目：数学,英语\n"
        "【成都家教082001】\n联系地址：新都区木锦新城\n辅导科目：语数英"
    )

    own = extract_order_block(text, "成都家教 58147046")
    assert own is not None
    assert "58147046" in own
    assert "大都保峰玖著" in own
    assert "61201156" not in own and "082001" not in own

    own3 = extract_order_block(text, "成都家教082001")
    assert own3 is not None and "木锦新城" in own3 and "58147046" not in own3

    # 单号在文本中不存在时返回 None（含兜底号 ITEM-xx）
    assert extract_order_block(text, "成都家教99999999") is None
    assert extract_order_block(text, "ITEM-01") is None


async def test_ai_path_assigns_per_order_raw_text(monkeypatch):
    """AI 段内含多单时，每单原文必须是自身块，而非整段。"""
    from services import parser

    chunk = (
        "【成都家教 58147046】\n联系地址：新都区大都保峰玖著\n辅导科目：数学\n"
        "【成都家教 61201156】\n联系地址：新都区廖家湾\n辅导科目：数学,英语"
    )

    async def fake_deepseek(text, source_profile=""):
        return [
            {"raw_id": "成都家教 58147046", "grade_subject": "准初二 数学", "address": "新都区大都保峰玖著"},
            {"raw_id": "成都家教 61201156", "grade_subject": "预初一 数学英语", "address": "新都区廖家湾"},
        ]

    monkeypatch.setattr(parser, "_call_deepseek", fake_deepseek)
    monkeypatch.setattr(parser, "_parse_labeled_orders", lambda _t, _p=None: ([], []))
    monkeypatch.setattr(parser, "_split_wechat_text", lambda _t, max_chars=3200: [chunk])

    orders, _warnings = await parser.parse_wechat_batch(chunk)

    assert "58147046" in orders[0]["raw_text"]
    assert "61201156" not in orders[0]["raw_text"]
    assert "58147046" not in orders[1]["raw_text"]
    assert "廖家湾" in orders[1]["raw_text"]


async def test_deepseek_prompt_masks_contact_info():
    """订单原文送第三方 AI 前必须掩码联系方式（PIPL 出境最小化）。
    掩码原地等长替换，不影响地址/科目提取。"""
    import json as _json

    from services import parser

    captured = {}

    class _FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            content = _json.dumps(
                {
                    "orders": [
                        {
                            "raw_id": "AI-M-001",
                            "grade_subject": "初三 数学",
                            "address": "成都市郫都区红光兰台府",
                            "price_total": "100/h",
                        }
                    ]
                },
                ensure_ascii=False,
            )
            return {"choices": [{"message": {"content": content}}]}

    class _FakeClient:
        async def post(self, url, **kwargs):
            captured["body"] = kwargs["json"]
            return _FakeResp()

    raw_text = (
        "【成都家教 12345678】联系地址：成都市郫都区红光兰台府\n"
        "科目：数学 薪资：100/h 家长电话 13800000001，微信：parent_wx_01"
    )

    result = await parser._deepseek_once(_FakeClient(), raw_text, "微信自然语言")

    sent = captured["body"]["messages"][1]["content"]
    assert "13800000001" not in sent, "手机号原文不得出境"
    assert "138****0001" in sent
    assert "parent_wx_01" not in sent, "微信号原文不得出境"
    assert "红光兰台府" in sent and "数学" in sent, "掩码不得影响地址/科目"
    assert result[0]["raw_id"] == "AI-M-001"


async def test_geocode_address_cached_in_redis(fake_redis, monkeypatch):
    """同一地址的地理编码结果走 Redis 缓存：第二次调用不再打 API（省配额）。"""
    from services import parser

    calls = {"count": 0}

    async def fake_request(client, address):
        calls["count"] += 1
        return (104.1234, 30.5678)

    monkeypatch.setattr(parser, "_geocode_request", fake_request)

    first = await parser.geocode_address("成都市郫都区红光兰台府")
    second = await parser.geocode_address("成都市郫都区红光兰台府")

    assert first == second == (104.1234, 30.5678)
    assert calls["count"] == 1, "第二次同址调用必须命中缓存"



async def _real_world_family_format_splits_and_fills_raw_text():
    """真实样本（0.9.0 后）："成都 20262208D12"式无家教头 + "学生年级及性别/辅导的科目及情况/
    上课时间安排/课时费"标签 + 后续"专职单"第二单。此前三连败：标签不识别转 AI、
    AI 原文回填失败（无家教头）、整段塞给第一单。"""
    from services import parser

    raw_text = """
成都 20262208D12
地址：武侯区石羊街道，三元地铁站
学生年级及性别：五年级女孩
辅导的科目及情况：英语
对老师的要求：负责任，有经验，有耐心，能够提高孩子学习成绩的女老师，长期
上课时间安排：周末，一周1次，一次两个小时
课时费：60/一个小时

专职单
成都20262207DD2
地址：武侯区火车南站
学生年级及性别：初一，男孩
辅导的科目及情况：英语，基础还不错
对老师的要求：有英语教师资格证，过专八，有耐心，口语好的在职专职女老师，长期
上课时间安排：周天下午，一周1次，一次两个小时
课时费：在职专职160-170/一个小时，试课半价
"""

    labeled, failed = parser._parse_labeled_orders(raw_text)
    # 标签覆盖后轻量解析应直接命中两单（不再依赖 AI 兜底）
    assert len(labeled) == 2, f"轻量应解析出两单，实际 {len(labeled)}，失败块 {len(failed)}"
    assert [o["raw_id"] for o in labeled] == ["成都20262208D12", "成都20262207DD2"]
    assert labeled[0]["grade_subject"] == "五年级女孩 英语"
    assert "火车南站" not in labeled[0]["raw_text"], "第二单内容不得混入第一单"
    assert "石羊街道" not in labeled[1]["raw_text"], "第一单内容不得混入第二单"

    orders, warnings = await parser.parse_wechat_batch(raw_text)
    assert len(orders) == 2 and warnings == []
    assert "成都20262207DD2" not in orders[0]["raw_text"]


def test_real_world_family_format_splits_and_fills_raw_text():
    import asyncio

    asyncio.run(_real_world_family_format_splits_and_fills_raw_text())


def test_shijia_standalone_code_header_not_swallowed():
    """真实样本："hsjj0704"独立短编号头（无家教字样）此前被吞进上一单。"""
    raw_text = """
【成都家教 21515260】
联系地址：青羊区金沙·柏林郡
年级性别：初二，女
辅导科目：数理化
时间安排：一周5次，一次1.5小时
薪资待遇：80元/小时

hsjj0704
学员地址：青羊区石人北路100号
辅导科目：数学
学员年级:   初三 男孩
老师薪水：70/80小时
"""

    orders, _failed = _parse_labeled_orders(raw_text)
    ids = [o["raw_id"] for o in orders]
    assert any("hsjj0704" in i for i in ids), f"短编号单不得被吞进上一单：{ids}"
    assert any("石人北路" in o["address"] for o in orders)


def test_promo_line_online_keyword_does_not_poison_previous_order():
    """真实样本：下一条订单的推广语含"线上单"字样，不得把上一条线下单误判为线上授课。"""
    raw_text = """
【成都家教 04498103】
联系地址：青羊区心愿花园2期
年级性别：初一，男
辅导科目：全科作业辅导
时间安排：一周6次 一次2小时
薪资待遇：60-70元/小时

初三英语线上单 要英语语法厉害的985女老师 @所有人

【成都家教 81048798】
联系地址：线上
年级性别：初三，女
辅导科目：英语
薪资待遇：140元/次
"""

    orders, _failed = _parse_labeled_orders(raw_text)
    by_id = {o["raw_id"]: o for o in orders}
    offline = by_id.get("成都家教04498103")
    assert offline is not None and offline["address"] != "线上授课", "线下单不得被导语的'线上'污染"
    online = by_id.get("成都家教81048798")
    assert online is not None and online["address"] == "线上授课"


def test_book_title_bracket_family_orders_parse():
    """真实样本：『地址』书名号式家庭单（此前标签包裹符不识别导致整组丢失）。"""
    raw_text = """
成都家庭单26091354#重新找
『地址』：青羊区泡桐树街
『年级』：新三年级
『科目』：英语
『时间』：一次课2小时，周六上午上课
『报酬』：70/小时
"""

    orders, _failed = _parse_labeled_orders(raw_text)
    assert len(orders) == 1
    assert orders[0]["raw_id"].startswith("26091354") or "26091354" in orders[0]["raw_id"]
    assert "泡桐树街" in orders[0]["address"]
    assert orders[0]["grade_subject"].startswith("新三年级")
