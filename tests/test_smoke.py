"""基础冒烟测试：验证所有模块可导入且核心逻辑正确。"""
import sys
sys.path.insert(0, '.')


def test_config():
    from config import settings
    assert settings.PROJECT_NAME == "Smart Tutor Router"
    assert settings.ORDER_EXPIRE_HOURS == 72


def test_calculator():
    from services.calculator import calculate_info_fee, calculate_refund

    # 一周 2 次：1.0 倍
    fee = calculate_info_fee(200.0, 2, False)
    assert fee == {"total_info_fee": 200.0, "deposit": 100.0, "balance": 100.0}

    # 暑假：2.5 倍
    fee = calculate_info_fee(200.0, 1, True)
    assert fee == {"total_info_fee": 500.0, "deposit": 100.0, "balance": 400.0}

    # 金额过低被拒绝
    try:
        calculate_info_fee(10.0, 1, False)
        assert False, "should have raised"
    except ValueError:
        pass

    # 退费
    assert calculate_refund(300.0, 200.0, False, False) == 160.0
    assert calculate_refund(300.0, 200.0, True, False) == 0.0
    assert calculate_refund(300.0, 200.0, False, True) == 0.0


def test_state_machine():
    from utils.state_machine import validate_transition
    from models.domain import OrderStatus as OS

    # 通用 transit 入口只允许归档/重新开放
    validate_transition(OS.recruiting, OS.archived, "tenant_admin")
    validate_transition(OS.trial_in_progress, OS.archived, "tenant_admin")
    validate_transition(OS.trial_in_progress, OS.recruiting, "tenant_admin")
    validate_transition(OS.recruiting, OS.archived, "super_admin")

    # 业务状态（试课/完成）必须由投递流程驱动，不能走通用 transit
    for target in (OS.trial_in_progress, OS.completed):
        try:
            validate_transition(OS.recruiting, target, "tenant_admin")
            assert False, f"transit 到 {target} 应被拒绝"
        except (ValueError, PermissionError):
            pass

    # 不允许：废弃状态（含 pending_deposit）不可作为目标或来源
    for target in (OS.pending_deposit, OS.pending_approval, OS.pending_balance):
        try:
            validate_transition(OS.recruiting, target, "tenant_admin")
            assert False, f"transit 到废弃状态 {target} 应被拒绝"
        except ValueError:
            pass
    try:
        validate_transition(OS.pending_deposit, OS.recruiting, "tenant_admin")
        assert False, "从废弃状态出发应被拒绝"
    except ValueError:
        pass

    # 不允许：教员不能直接驱动订单状态（只能投递/支付）
    try:
        validate_transition(OS.recruiting, OS.archived, "teacher")
        assert False
    except PermissionError:
        pass

    # 不允许：completed 不可回退
    try:
        validate_transition(OS.completed, OS.recruiting, "tenant_admin")
        assert False
    except ValueError:
        pass


def test_geo_utils():
    from utils.geo import offset_coordinate, haversine_distance

    lng, lat = offset_coordinate(104.065735, 30.659462, 30, 80)
    dist = haversine_distance(104.065735, 30.659462, lng, lat)
    assert 20 < dist < 120, f"dist={dist}m out of range"


def test_jwt():
    from services.auth import create_jwt, decode_jwt

    token = create_jwt(sub="teacher_1", role="teacher")
    payload = decode_jwt(token)
    assert payload["sub"] == "teacher_1"
    assert payload["role"] == "teacher"
    assert payload["tid"] is None

    token2 = create_jwt(sub="tenant_1", role="tenant_admin", tenant_id=1)
    payload2 = decode_jwt(token2)
    assert payload2["tid"] == 1


def test_parser_validate():
    from services.parser import _split_wechat_text, _validate_and_parse

    # markdown 清洗
    raw = '```json\n[{"grade_subject": "初三数学", "base_price": 200.0, "address": "成都"}]\n```'
    items = _validate_and_parse(raw)
    assert len(items) == 1
    assert items[0]["grade_subject"] == "初三数学"

    # dict 解包
    raw2 = '{"orders": [{"grade_subject": "高三英语", "base_price": 260.0, "address": "成都金牛"}]}'
    items2 = _validate_and_parse(raw2)
    assert len(items2) == 1

    # 线上单允许 AI 按约定返回空地址，服务端归一为线上授课
    raw3 = '{"orders": [{"grade_subject": "高一数学", "address": "", "requirements": "线上教学"}]}'
    items3 = _validate_and_parse(raw3)
    assert items3[0]["address"] == "线上授课"

    # 缺年级科目拒绝
    try:
        _validate_and_parse('[{"address": "成都"}]')
        assert False
    except ValueError:
        pass

    long_text = """
Shmily: 07-18 12:02:13
＃招聘线上暑假工
只需要转发家教信息，成为正式小助手。

Shmily: 07-18 15:36:44
成都家教m1014
地址：新都体育森林公园
辅导科目：英语
老师薪水：100-130/一次课两小时
""".strip()
    chunks = _split_wechat_text(long_text)
    assert len(chunks) == 1
    assert "招聘线上暑假工" not in chunks[0]
    assert "成都家教m1014" in chunks[0]


if __name__ == "__main__":
    test_config();          print("[OK] config")
    test_calculator();      print("[OK] calculator")
    test_state_machine();   print("[OK] state_machine")
    test_geo_utils();       print("[OK] geo_utils")
    test_jwt();             print("[OK] jwt")
    test_parser_validate(); print("[OK] parser_validate")
    print()
    print("=== All tests passed ===")
