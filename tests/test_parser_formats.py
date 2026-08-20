from services.parser import _parse_labeled_orders


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
