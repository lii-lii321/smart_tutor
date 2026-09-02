from services.parser import _parse_labeled_orders
from services.parser import parse_wechat_batch


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

    orders = _parse_labeled_orders(raw_text)

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

    orders = _parse_labeled_orders(raw_text)

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

    orders = _parse_labeled_orders(raw_text)

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

    orders = _parse_labeled_orders(raw_text)

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

    orders = await parse_wechat_batch(raw_text)

    assert len(orders) == 2
    assert "成都家教77845931" not in orders[0]["raw_text"]
    assert "双流区华阳海昌路" not in orders[0]["raw_text"]
    assert "成都家教042004" not in orders[1]["raw_text"]
    assert "双流区悦榕东方" not in orders[1]["raw_text"]


def test_parse_batch_keeps_split_raw_text():
    import asyncio

    asyncio.run(_parse_batch_keeps_split_raw_text())
