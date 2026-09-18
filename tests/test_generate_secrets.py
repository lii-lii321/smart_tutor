"""generate_secrets 生成物的属性锁定：强度、互异、可读性。"""
import re
import sys

sys.path.insert(0, "scripts")

from generate_secrets import _CODE_ALPHABET, generate, readable_code


def test_generate_strength_and_distinctness():
    values = generate()
    assert len(values["DB_PASSWORD"]) == 32
    assert len(values["MYSQL_ROOT_PASSWORD"]) == 32
    assert len(values["JWT_SECRET"]) == 64  # hex 32 字节
    assert values["DB_PASSWORD"] != values["MYSQL_ROOT_PASSWORD"]
    # 生产红线：JWT_SECRET ≥32 字符
    assert len(values["JWT_SECRET"]) >= 32


def test_readable_code_charset_and_shape():
    code = readable_code()
    assert re.fullmatch(r"[A-Z2-9]{4}(-[A-Z2-9]{4}){2}", code), code
    assert not set("0O1lI") & set(code.replace("-", ""))
    # 字符集确实排除了歧义字符
    assert not (set("0O1lI") & set(_CODE_ALPHABET))


def test_build_block_is_pasteable():
    values = generate()
    block = __import__("generate_secrets").build_block(values)
    for key in ("DB_PASSWORD", "MYSQL_ROOT_PASSWORD", "JWT_SECRET", "OWNER_ACCESS_CODE"):
        assert f"{key}={values[key]}" in block
