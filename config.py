import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Smart Tutor Router"
    VERSION: str = "1.0.0"
    DEBUG: bool = False

    # 数据库连接字符串（留空则自动使用 SQLite 开发模式）
    DATABASE_URL: str = ""

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

    # GEO 坐标偏移范围（米）
    GEO_OFFSET_MIN: int = 30
    GEO_OFFSET_MAX: int = 80

    # 订单过期时间（小时）
    ORDER_EXPIRE_HOURS: int = 72

    # 批量解析频率限制（每租户每分钟最大调用次数，防止刷爆 AI 账单）
    MAX_PARSE_PER_MINUTE: int = 20

    # 开发模式：跳过微信 OAuth，用 openid 直接登录。
    # 安全默认关闭；本地开发请在 .env 中设置 DEV_MODE=true。
    DEV_MODE: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    def model_post_init(self, __context) -> None:
        if not self.DEV_MODE and self.JWT_SECRET in (
            "change-me-to-a-random-secret-in-production",
            "change-me-to-a-random-64-char-string",
        ):
            raise RuntimeError(
                "JWT_SECRET 仍为默认值，生产环境必须通过环境变量设置强随机密钥，"
                "否则 Token 可被伪造。"
            )


settings = Settings()
