"""
家长 PII 静态加密（ADR-0005 / services/pii_crypto.py）：

- 加解密往返、密文格式（v1: 前缀 + 随机 nonce）、篡改检测；
- 双格式兼容：明文遗留行读端原样返回；
- 开发直通模式（未配 PII_ENC_KEY）：写入明文、读端不报错；
- API 集成：配钥后 B 端导入/编辑落库为密文，详情/address-unlock 解密返回。

运行方式：
    pytest tests/test_pii_encryption.py
"""
import base64

import pytest
from conftest import make_order, make_teacher, make_tenant, teacher_token, tenant_token
from sqlalchemy import text

from config import settings
from services.pii_crypto import decrypt_pii, encrypt_pii

_TEST_KEY = base64.b64encode(bytes(range(32))).decode("ascii")


@pytest.fixture()
def pii_key(monkeypatch):
    """为单测注入固定密钥；测试结束自动还原（settings 是全局单例）。"""
    monkeypatch.setattr(settings, "PII_ENC_KEY", _TEST_KEY)
    return _TEST_KEY


def test_roundtrip_and_format(pii_key):
    cipher = encrypt_pii("13800001111")
    assert cipher.startswith("v1:")
    assert cipher != "13800001111"
    # 随机 nonce：同一明文两次加密密文不同（防密文比对攻击）
    assert encrypt_pii("13800001111") != cipher
    assert decrypt_pii(cipher) == "13800001111"


def test_empty_and_none_passthrough(pii_key):
    assert encrypt_pii(None) is None
    assert encrypt_pii("") == ""
    assert decrypt_pii(None) is None
    assert decrypt_pii("") == ""


def test_legacy_plaintext_tolerated(pii_key):
    # 无 v1: 前缀 = 明文遗留行（回填前存量/开发直通写入），读端原样返回
    assert decrypt_pii("明文地址#101") == "明文地址#101"


def test_tamper_detected(pii_key):
    from cryptography.exceptions import InvalidTag

    cipher = encrypt_pii("13800001111")
    raw = bytearray(base64.b64decode(cipher[3:]))
    raw[-1] ^= 0xFF  # 翻转密文末位（GCM tag 校验必炸）
    with pytest.raises(InvalidTag):
        decrypt_pii("v1:" + base64.b64encode(bytes(raw)).decode("ascii"))


def test_dev_passthrough_without_key(monkeypatch):
    monkeypatch.setattr(settings, "PII_ENC_KEY", "")
    assert encrypt_pii("13800001111") == "13800001111"  # 明文直存
    assert decrypt_pii("13800001111") == "13800001111"  # 读端不报错


def test_cipher_without_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "PII_ENC_KEY", "")
    with pytest.raises(RuntimeError, match="PII_ENC_KEY"):
        decrypt_pii("v1:AAAA")


def test_invalid_key_rejected(monkeypatch):
    monkeypatch.setattr(settings, "PII_ENC_KEY", "not-base64!!")
    with pytest.raises(RuntimeError, match="base64"):
        encrypt_pii("x")
    short = base64.b64encode(b"short").decode("ascii")
    monkeypatch.setattr(settings, "PII_ENC_KEY", short)
    with pytest.raises(RuntimeError, match="32"):
        encrypt_pii("x")


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


_IMPORT_ITEM = {
    "raw_id": "PII-001",
    "raw_text": "高二数学 家长电话13800001111",
    "grade_subject": "高二数学",
    "price_total": "200元/小时",
    "base_price": 200,
    "weekly_frequency": 2,
    "is_summer_vacation": False,
    "fuzzy_address": "某区某街道",
    "exact_address": "某区某街道1号院2栋301",
    "parent_phone": "13800001111",
    "lng": 104.06,
    "lat": 30.65,
    "calculated_info_fee": 200,
    "deposit_amount": 100,
    "balance_amount": 100,
}


async def test_import_stores_cipher_and_detail_decrypts(client, db, pii_key):
    tenant = await make_tenant(db, "piit001")
    await db.commit()
    headers = _auth(tenant_token(tenant.id))

    resp = await client.post(
        "/api/v1/orders/batch-import", headers=headers, json={"items": [_IMPORT_ITEM]}
    )
    assert resp.status_code == 200, resp.text
    order_id = (await db.execute(
        text("SELECT id FROM orders WHERE raw_id='PII-001'")
    )).scalar_one()

    # 绕开 ORM 直接看列：落库的是密文，明文不出现在任何一列
    row = (await db.execute(
        text("SELECT exact_address, parent_phone FROM orders WHERE id=:id"),
        {"id": order_id},
    )).one()
    assert row.exact_address.startswith("v1:")
    assert row.parent_phone.startswith("v1:")
    assert "13800001111" not in (row.parent_phone or "")
    assert "1号院" not in (row.exact_address or "")

    # B 端详情解密返回明文
    detail = await client.get(f"/api/v1/orders/{order_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["parent_phone"] == "13800001111"
    assert detail.json()["exact_address"] == "某区某街道1号院2栋301"


async def test_patch_reencrypts_new_values(client, db, pii_key):
    tenant = await make_tenant(db, "piit002")
    order = await make_order(db, tenant.id, "PII-101")
    await db.commit()
    headers = _auth(tenant_token(tenant.id))

    resp = await client.patch(
        f"/api/v1/orders/{order.id}",
        headers=headers,
        json={"parent_phone": "13700003333", "exact_address": "新地址5栋"},
    )
    assert resp.status_code == 200, resp.text

    row = (await db.execute(
        text("SELECT exact_address, parent_phone FROM orders WHERE id=:id"),
        {"id": order.id},
    )).one()
    assert row.parent_phone.startswith("v1:")
    assert decrypt_pii(row.parent_phone) == "13700003333"
    assert decrypt_pii(row.exact_address) == "新地址5栋"


async def test_unlock_decrypts_cipher_for_trial_teacher(client, db, pii_key):
    tenant = await make_tenant(db, "piit003")
    teacher = await make_teacher(db, "pii_t1")
    order = await make_order(db, tenant.id, "PII-201")
    order.exact_address = encrypt_pii("解锁测试门牌7号")
    order.parent_phone = encrypt_pii("13600004444")
    from models.domain import Application, ApplicationStatus

    db.add(Application(
        tenant_id=tenant.id,
        order_id=order.id,
        teacher_id=teacher.id,
        status=ApplicationStatus.trial_in_progress,
    ))
    await db.commit()

    resp = await client.get(
        f"/api/v1/orders/{order.id}/address-unlock",
        headers=_auth(teacher_token(teacher.id)),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["parent_phone"] == "13600004444"
    assert body["exact_address"] == "解锁测试门牌7号"


async def test_legacy_plaintext_row_still_unlocks(client, db, pii_key):
    """回填前存量行（明文）与密文行走同一条解锁路径。"""
    tenant = await make_tenant(db, "piit004")
    teacher = await make_teacher(db, "pii_t2")
    order = await make_order(db, tenant.id, "PII-301")
    order.exact_address = "明文遗留地址"
    order.parent_phone = "13500005555"
    from models.domain import Application, ApplicationStatus

    db.add(Application(
        tenant_id=tenant.id,
        order_id=order.id,
        teacher_id=teacher.id,
        status=ApplicationStatus.trial_in_progress,
    ))
    await db.commit()

    resp = await client.get(
        f"/api/v1/orders/{order.id}/address-unlock",
        headers=_auth(teacher_token(teacher.id)),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["parent_phone"] == "13500005555"
