import os
import tempfile
from datetime import datetime

from pydantic_settings import BaseSettings

# 公开仓库中的占位密钥前缀：生产环境以此开头的 JWT_SECRET 一律拒绝启动
# （scripts/preflight.py 复用同一词表，改这里即可同步）
JWT_SECRET_PLACEHOLDER_PREFIXES = ("change-me", "dev-secret", "ci-secret", "test-secret")


class Settings(BaseSettings):
    PROJECT_NAME: str = "Smart Tutor Router"
    VERSION: str = "1.0.0"
    DEBUG: bool = False

    # 日志：级别 + 落盘目录（按天轮转，保留 14 天，见 utils/logging_config.py）
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"
    # 文件日志仅限单进程本地开发；多 worker 容器必须走纯 stdout
    # （TimedRotatingFileHandler 轮转 rename 非进程安全，compose 已固定为 false）
    LOG_TO_FILE: bool = True
    # 慢请求/慢查询阈值（毫秒）：超过即升 WARNING 留痕（middleware/observability.py
    # 与 database.py 的 SQLAlchemy 计时钩子），线上排查"页面慢/单子看不到"的入口
    SLOW_REQUEST_MS: int = 800
    SLOW_QUERY_MS: int = 500

    # 数据库连接字符串。优先级高于分项配置；生产环境可直接填 MySQL async URL。
    DATABASE_URL: str = ""
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str | None = None
    DB_NAME: str = "smart_tutor"

    # Redis
    REDIS_URL: str = "redis://127.0.0.1:6379/0"

    # JWT（生产环境必须通过环境变量覆盖默认密钥）
    JWT_SECRET: str = "change-me-to-a-random-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 72
    OWNER_ACCESS_CODE: str = "boss888"
    # 老板 token 无账号行可挂失效标记：在此时间（naive UTC，ISO 串）前签发的 super_admin
    # token 一律 401。轮换 OWNER_ACCESS_CODE 时同步更新即可吊销存量老板会话；留 None 不启用
    OWNER_TOKEN_VALID_AFTER: datetime | None = None

    # CORS 白名单（逗号分隔）。开发默认放行 Vite dev server。
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 微信小程序/公众号
    WX_APPID: str = ""
    WX_SECRET: str = ""

    # DeepSeek
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/chat/completions"

    # 高德地图
    AMAP_API_KEY: str = ""
    AMAP_GEOCODE_URL: str = "https://restapi.amap.com/v3/geocode/geo"

    # Sentry 错误上报（P1-9）：留空 = 完全不初始化（本地/CI 零感知）。
    # 环境标签按 DEV_MODE 自动区分 development/production
    SENTRY_DSN: str = ""

    # 订单过期时间（小时）
    ORDER_EXPIRE_HOURS: int = 72

    # 批量解析频率限制（每租户每分钟最大调用次数，防止刷爆 AI 账单）
    MAX_PARSE_PER_MINUTE: int = 20

    # 登录尝试频率限制（每 IP+账号 每分钟最大失败次数，防止密码爆破）
    MAX_LOGIN_PER_MINUTE: int = 10

    # 开发模式：跳过微信 OAuth，用 openid 直接登录。
    # 安全默认关闭；本地开发请在 .env 中设置 DEV_MODE=true。
    DEV_MODE: bool = False
    # 生产环境应通过部署流程执行 Alembic；仅本地兼容场景才开启自动建表。
    AUTO_CREATE_SCHEMA: bool = False
    # API 容器在 compose 部署时置 true（调度由独立 scheduler 容器承担），本地开发保持 False
    DISABLE_SCHEDULER: bool = False

    # 调度循环心跳文件：容器 healthcheck 按其修改时间判断调度是否假死（见 services/scheduler.py）
    SCHEDULER_HEARTBEAT: str = os.path.join(tempfile.gettempdir(), "scheduler.heartbeat")

    # 触达通道（选填，见 services/notify.py）：站内信之外的出站推送。
    # 未配置任何通道时消息仅走日志兜底，业务无感。
    NOTIFY_WECOM_WEBHOOK_URL: str = ""
    NOTIFY_WEBHOOK_URL: str = ""
    NOTIFY_WEBHOOK_TOKEN: str = ""
    NOTIFY_DISPATCH_INTERVAL: int = 30

    # 收款凭证存储目录（services/receipts.py）：compose 生产建议挂卷持久化
    RECEIPT_DIR: str = "data/receipts"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def model_post_init(self, __context) -> None:
        if self.DEV_MODE:
            return
        # 长度 + 占位值双重校验：漏配拿到的空串必须拒绝，且默认占位串恰好 43 字符
        # 能绕过长度校验——用它启动等于把签名密钥公开给所有能看到仓库的人
        if len(self.JWT_SECRET) < 32 or self.JWT_SECRET.startswith(JWT_SECRET_PLACEHOLDER_PREFIXES):
            raise RuntimeError(
                "生产环境必须通过环境变量设置 32 位以上、非占位值的强随机 JWT_SECRET"
                "（openssl rand -hex 32）。"
            )
        if not self.OWNER_ACCESS_CODE or self.OWNER_ACCESS_CODE == "boss888":
            # 空串能通过 compose 的 ${VAR} 漏填：老板永远登录不进去且无报错指向原因
            raise RuntimeError("生产环境必须通过环境变量设置 OWNER_ACCESS_CODE（≥8 位，不能是默认值或空串）。")
        if len(self.OWNER_ACCESS_CODE) < 8:
            raise RuntimeError("OWNER_ACCESS_CODE 至少 8 位，防止暴力枚举。")
        # 自动建表会执行 _ensure_* 补丁（含 DDL/DELETE）：多 uvicorn worker 并发启动会互相踩踏，
        # 生产 schema 一律走 alembic（compose 已显式置 false，这里兜底防误配）
        if self.AUTO_CREATE_SCHEMA:
            raise RuntimeError("生产环境禁止开启 AUTO_CREATE_SCHEMA，建表请走 alembic 迁移。")


settings = Settings()
