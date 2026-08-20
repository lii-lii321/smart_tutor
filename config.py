import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = "Smart Tutor Router"
    VERSION: str = "1.0.0"
    DEBUG: bool = True

    # 数据库连接字符串（留空则自动使用 SQLite 开发模式）
    DATABASE_URL: str = ""

    # Redis
    REDIS_URL: str = "redis://127.0.0.1:6379/0"

    # JWT
    JWT_SECRET: str = "change-me-to-a-random-secret-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 72
    OWNER_ACCESS_CODE: str = "boss888"

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

    # 开发模式：跳过微信 OAuth，用 openid 直接登录
    DEV_MODE: bool = True

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
