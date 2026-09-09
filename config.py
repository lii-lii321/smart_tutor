from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Smart Tutor Router"
    VERSION: str = "1.0.0"
    DEBUG: bool = False

    # 日志：级别 + 落盘目录（按天轮转，保留 14 天，见 utils/logging_config.py）
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"

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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def model_post_init(self, __context) -> None:
        if self.DEV_MODE:
            return
        # 长度校验而非枚举占位串：漏配环境变量时拿到的空串同样必须拒绝
        if len(self.JWT_SECRET) < 32:
            raise RuntimeError("生产环境必须通过环境变量设置 32 位以上的强随机 JWT_SECRET。")
        if self.OWNER_ACCESS_CODE == "boss888":
            raise RuntimeError("生产环境必须通过环境变量设置 OWNER_ACCESS_CODE。")


settings = Settings()
