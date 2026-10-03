"""
家长 PII 静态加密（ADR-0005）：Order.parent_phone / exact_address 落库前 AES-256-GCM 加密。

形态：列内密文 = "v1:" + base64(nonce(12B) + ciphertext + tag(16B))，密钥版本随前缀演进
（轮换 = 新增前缀版本 + 批量重加密，读取按前缀选密钥）。

双格式兼容：无前缀的值按"明文遗留行"原样返回——DEV_MODE 未配密钥时写入即为明文，
生产回填迁移前的存量行同理，读端永远不需要区分。

密钥来自环境变量 PII_ENC_KEY（base64 编码的 32 字节）；生产环境由 config 的启动校验强制，
DEV_MODE 缺省时进入"明文直存"直通模式（开发零感知）。加密与解密都无状态、不缓存密钥
（每次 base64 解码的开销远低于一次 DB 往返），测试可随时换键。
"""
import base64
import binascii
import os

from config import settings

_PREFIX = "v1:"
_NONCE_LEN = 12


def _load_key() -> bytes | None:
    """返回 32 字节密钥；未配置（开发直通模式）返回 None。"""
    raw = (settings.PII_ENC_KEY or "").strip()
    if not raw:
        return None
    try:
        key = base64.b64decode(raw)
    except (binascii.Error, ValueError) as e:
        raise RuntimeError("PII_ENC_KEY 不是合法 base64，请用 scripts/generate_secrets.py 生成") from e
    if len(key) != 32:
        raise RuntimeError(f"PII_ENC_KEY 解码后必须为 32 字节，当前 {len(key)}")
    return key


def encrypt_pii(plain: str | None) -> str | None:
    """落库前加密；None/空串原样透传；未配密钥（开发模式）明文直存。"""
    if not plain:
        return plain
    key = _load_key()
    if key is None:
        return plain
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(_NONCE_LEN)
    ct = AESGCM(key).encrypt(nonce, plain.encode("utf-8"), None)
    return _PREFIX + base64.b64encode(nonce + ct).decode("ascii")


def decrypt_pii(stored: str | None) -> str | None:
    """读路径解密；无前缀按明文遗留行原样返回。

    有密文但无密钥属于误配置（生产启动校验已拦截）：明确报错优于把 "v1:..."
    当明文展示给 B 端。
    """
    if not stored or not stored.startswith(_PREFIX):
        return stored
    key = _load_key()
    if key is None:
        raise RuntimeError("检测到加密 PII 但未配置 PII_ENC_KEY，无法解密（生产必须配置该密钥）")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    raw = base64.b64decode(stored[len(_PREFIX):])
    nonce, ct = raw[:_NONCE_LEN], raw[_NONCE_LEN:]
    return AESGCM(key).decrypt(nonce, ct, None).decode("utf-8")
