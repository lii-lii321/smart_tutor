"""
掩码工具边界回归（ADR-0002 的序列化脱敏依赖本模块）。

锁定：连续数字不重复掩码、分隔号格式、座机、带前缀的微信/QQ、
英文单词不被误伤、None/空串安全。
"""

from utils.masking import mask_contact_info


def test_mobile_masked_with_boundary_guards():
    # 前后紧贴数字时不掩码（那是更长数字的一部分，如订单编号）
    assert mask_contact_info("编号1138012345678901") == "编号1138012345678901"
    assert mask_contact_info("联系家长 13812345678") == "联系家长 138****5678"


def test_separated_mobile_masked():
    assert mask_contact_info("电话 138 0000 0001") == "电话 138****0001"
    assert mask_contact_info("电话 139-0000-0002") == "电话 139****0002"


def test_landline_masked():
    assert mask_contact_info("座机 028-87654321") == "座机 028-****"
    assert mask_contact_info("座机 01087654321") == "座机 0108****"


def test_prefixed_wechat_and_qq_masked():
    assert "wx_ab12cd" not in mask_contact_info("微信：wx_ab12cd")
    assert "wx****cd" in mask_contact_info("微信：wx_ab12cd")
    assert "12345678" not in mask_contact_info("QQ: 12345678")
    # 无前缀的英文串不受影响
    assert mask_contact_info("备注 happydays") == "备注 happydays"


def test_none_and_empty_safe():
    assert mask_contact_info(None) == ""
    assert mask_contact_info("") == ""
