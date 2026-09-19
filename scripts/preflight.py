"""上线预检（只读体检）：对当前环境配置做一次全面检查，月末上线前跑一遍。

用法（生产容器内，读取即真实生产配置）：
    docker compose exec api python scripts/preflight.py

退出码：0 = 无失败项；1 = 存在必须修复项（[FAIL]）。
[WARN] 不阻断上线，但建议逐条确认。

检查面：
- 生产红线：DEV_MODE/AUTO_CREATE_SCHEMA 关闭，JWT_SECRET 强度，OWNER_ACCESS_CODE 非默认；
- 数据库：可连接，且 alembic 版本戳 == 迁移脚本 head（未跑迁移直接 503 的最常见原因）；
- Redis：可 ping（降级可跑，但限流/橱窗缓存/地图索引全部失效，应确认是有意为之）；
- 第三方 Key：DeepSeek/高德（缺了对应功能退化）、微信/Sentry（可选，仅提示）；
- 日志目录可写。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAILED: list[str] = []
WARNED: list[str] = []
OK: list[str] = []


def ok(msg: str) -> None:
    OK.append(msg)
    print(f"  [ OK ] {msg}")


def warn(msg: str) -> None:
    WARNED.append(msg)
    print(f"  [WARN] {msg}")


def fail(msg: str) -> None:
    FAILED.append(msg)
    print(f"  [FAIL] {msg}")


def check_red_lines(settings) -> None:
    print("\n== 1. 生产红线 ==")
    if settings.DEV_MODE:
        fail("DEV_MODE=true：演示数据播种与 dev 登录全开，生产必须关闭")
    else:
        ok("DEV_MODE=false")
    if settings.AUTO_CREATE_SCHEMA:
        fail("AUTO_CREATE_SCHEMA=true：生产建表必须走 alembic（多 worker 并发 DDL 会互相踩踏）")
    else:
        ok("AUTO_CREATE_SCHEMA=false")
    # 词表与 config.JWT_SECRET_PLACEHOLDER_PREFIXES 同源（config 生产启动硬校验同一规则）
    from config import JWT_SECRET_PLACEHOLDER_PREFIXES

    if len(settings.JWT_SECRET) < 32:
        fail(f"JWT_SECRET 长度 {len(settings.JWT_SECRET)} < 32")
    elif settings.JWT_SECRET.startswith(JWT_SECRET_PLACEHOLDER_PREFIXES):
        fail("JWT_SECRET 疑似占位值，必须换成强随机串（openssl rand -hex 32）")
    else:
        ok("JWT_SECRET 强度合格")
    if not settings.OWNER_ACCESS_CODE:
        fail("OWNER_ACCESS_CODE 为空：老板入口将永远无法登录")
    elif settings.OWNER_ACCESS_CODE == "boss888":
        fail("OWNER_ACCESS_CODE 仍是默认值 boss888")
    elif len(settings.OWNER_ACCESS_CODE) < 8:
        fail("OWNER_ACCESS_CODE 少于 8 位，易被暴力枚举")
    else:
        ok("OWNER_ACCESS_CODE 已自定义")


def check_database() -> None:
    print("\n== 2. 数据库 ==")
    import asyncio

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    script_head = ScriptDirectory.from_config(cfg).get_current_head()

    async def _db_checks() -> tuple[bool, str, str | None]:
        """返回 (是否可连接, 描述, 当前版本戳)。"""
        from sqlalchemy import text

        from database import _get_database_url, _get_engine

        engine = _get_engine()
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                try:
                    row = (await conn.execute(
                        text("SELECT version_num FROM alembic_version")
                    )).first()
                    stamp = row[0] if row else None
                except Exception:  # noqa: BLE001  alembic_version 表不存在 = 从未跑过迁移
                    stamp = None
            dialect = _get_database_url().split("+")[0]
            return True, dialect, stamp
        except Exception as e:  # noqa: BLE001
            return False, str(e), None

    reachable, detail, stamp = asyncio.run(_db_checks())
    if not reachable:
        fail(f"数据库不可连接：{detail}")
        return
    ok(f"{detail} 可连接")
    if stamp is None:
        fail("数据库从未跑过迁移（alembic_version 为空）：先执行 docker compose exec api alembic upgrade head")
    elif stamp != script_head:
        fail(f"迁移落后：库中 {stamp} != 脚本 head {script_head}，执行 alembic upgrade head")
    else:
        ok(f"迁移已到位（{stamp}）")


def check_redis() -> None:
    print("\n== 3. Redis ==")
    import asyncio

    async def _ping() -> bool:
        from services.order_maintenance import get_redis_client

        try:
            redis = await get_redis_client()
            return bool(await redis.ping())
        except Exception:  # noqa: BLE001
            return False

    if asyncio.run(_ping()):
        ok("Redis 可 ping（限流共享计数 / 橱窗缓存 / 地图 GEO 索引就绪）")
    else:
        warn("Redis 不可用：服务可降级运行，但限流退化为单进程、地图索引退化为直查 MySQL、橱窗无缓存")


def check_third_party(settings) -> None:
    print("\n== 4. 第三方 Key ==")
    if settings.DEEPSEEK_API_KEY:
        ok("DEEPSEEK_API_KEY 已配置（AI 批量解析可用）")
    else:
        warn("DEEPSEEK_API_KEY 未配置：批量解析 AI 回退不可用（轻量解析仍可用）")
    if settings.AMAP_API_KEY:
        ok("AMAP_API_KEY 已配置（地理编码可用）")
    else:
        warn("AMAP_API_KEY 未配置：新订单将落到区县兜底坐标")
    if settings.WX_APPID and settings.WX_SECRET:
        ok("微信登录已配置")
    else:
        print("  [info] 微信登录未配置（可选，手机号登录不受影响）")
    if settings.SENTRY_DSN:
        ok("Sentry 已启用（错误将上报）")
    else:
        print("  [info] Sentry 未配置（可选）")


def check_log_dir(settings) -> None:
    print("\n== 5. 日志目录 ==")
    if not settings.LOG_TO_FILE:
        # 容器部署标准形态：纯 stdout 由 docker json-file 收集，不落盘
        ok("LOG_TO_FILE=false：纯 stdout 模式，无需落盘目录")
        return
    try:
        probe = os.path.join(settings.LOG_DIR, ".preflight_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("probe")
        os.remove(probe)
        ok(f"LOG_DIR 可写：{settings.LOG_DIR}")
    except Exception as e:  # noqa: BLE001
        fail(f"LOG_DIR 不可写（{settings.LOG_DIR}）：{e}")


def check_receipt_dir(settings) -> None:
    print("\n== 5b. 收款凭证目录 ==")
    try:
        from services.receipts import receipt_dir

        target = receipt_dir()
        probe = target / ".preflight_probe"
        probe.write_text("probe", encoding="utf-8")
        probe.unlink()
        ok(f"RECEIPT_DIR 可写：{settings.RECEIPT_DIR}")
    except Exception as e:  # noqa: BLE001
        fail(f"RECEIPT_DIR 不可写（{settings.RECEIPT_DIR}）：凭证上传将全部失败，检查卷挂载/权限：{e}")
    if not settings.NOTIFY_WECOM_WEBHOOK_URL and not settings.NOTIFY_WEBHOOK_URL:
        print("  [info] 触达通道未配置：通知仅站内信 + 日志（配置 NOTIFY_WECOM_WEBHOOK_URL 可实时推企业微信群）")
    else:
        ok("触达通道已配置（出站消息将实时推送）")


def check_temp() -> None:
    print("\n== 6. 临时目录（scheduler 心跳文件落点）==")
    try:
        probe = os.path.join(tempfile.gettempdir(), ".preflight_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("probe")
        os.remove(probe)
        ok("临时目录可写")
    except Exception as e:  # noqa: BLE001
        fail(f"临时目录不可写：{e}")


def main() -> int:
    from config import settings

    print(f"== 智派家教平台 上线预检 ==（{settings.PROJECT_NAME} v{settings.VERSION}）")
    check_red_lines(settings)
    check_database()
    check_redis()
    check_third_party(settings)
    check_log_dir(settings)
    check_receipt_dir(settings)
    check_temp()

    print("\n== 结果 ==")
    print(f"通过 {len(OK)} 项；警告 {len(WARNED)} 项；失败 {len(FAILED)} 项")
    for item in FAILED:
        print(f"  必须修复: {item}")
    for item in WARNED:
        print(f"  建议确认: {item}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
