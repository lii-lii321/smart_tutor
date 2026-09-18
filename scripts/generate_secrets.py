"""
生成 .env.production 必填密钥块（仅标准库，本机/服务器均可跑）。

用法：
    python scripts/generate_secrets.py             # 打印一组可直接粘贴的配置块
    python scripts/generate_secrets.py --count 3   # 生成 3 组备选（人工挑一组）

设计约定：
- 密钥只打印到 stdout，不落盘——粘贴进 .env.production 后由使用者保管；
- DB_PASSWORD 与 MYSQL_ROOT_PASSWORD 必然不同（compose 红线要求）；
- OWNER_ACCESS_CODE 用无歧义字符集（不含 0/O/1/l/I），老板手输不易错。
- 轮换时机与各密钥影响面见 docs/DEPLOY_CHECKLIST.md §7「密钥轮换操作单」。
"""
import argparse
import secrets
import string

# 无歧义字符集：去掉 0/O/1/l/I 后仍保留足够熵（12 位 ≈ 66 bit）
_CODE_ALPHABET = "".join(c for c in string.ascii_uppercase + string.digits if c not in set("0O1lI"))


def readable_code(length: int = 12) -> str:
    """人工可输入的访问码：分组排版，无歧义字符。"""
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))
    return "-".join(raw[i:i + 4] for i in range(0, length, 4))


def generate() -> dict[str, str]:
    """生成一组必填密钥。两次调用之间不共享任何随机源状态。"""
    return {
        "DB_PASSWORD": secrets.token_hex(16),
        "MYSQL_ROOT_PASSWORD": secrets.token_hex(16),
        "JWT_SECRET": secrets.token_hex(32),
        "OWNER_ACCESS_CODE": readable_code(),
    }


def build_block(values: dict[str, str]) -> str:
    """格式化为可直接粘贴进 .env.production 的配置块。"""
    assert values["DB_PASSWORD"] != values["MYSQL_ROOT_PASSWORD"], "两个数据库密码必须不同"
    return (
        "# ── 生成密钥（scripts/generate_secrets.py）────────────\n"
        f"DB_PASSWORD={values['DB_PASSWORD']}\n"
        f"MYSQL_ROOT_PASSWORD={values['MYSQL_ROOT_PASSWORD']}\n"
        f"JWT_SECRET={values['JWT_SECRET']}\n"
        f"OWNER_ACCESS_CODE={values['OWNER_ACCESS_CODE']}\n"
        "# 用 Caddy HTTPS 时追加：SITE_DOMAIN=你的域名\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 .env.production 必填密钥块")
    parser.add_argument("--count", type=int, default=1, help="生成组数（默认 1）")
    args = parser.parse_args()

    for _ in range(max(1, args.count)):
        print(build_block(generate()))


if __name__ == "__main__":
    main()
