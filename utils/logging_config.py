"""
日志体系：统一控制台 + 按天轮转文件。

在此之前的仓库没有任何 logging 配置，各模块的 logger.info 全部被丢弃、
WARNING 走 lastResort 裸吐 stderr。main.py 的 lifespan 调用 setup_logging() 后：
- 应用日志写入 logs/app.log（按天轮转，保留 14 天）；
- uvicorn 的 access/error 日志复用同一格式；
- 未配置 LOG_LEVEL 时默认 INFO。
"""
import logging
import logging.config
import os

from config import settings

_LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"


def setup_logging() -> None:
    log_dir = settings.LOG_DIR
    os.makedirs(log_dir, exist_ok=True)

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {"format": _LOG_FORMAT},
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "standard",
                "level": settings.LOG_LEVEL,
            },
            "file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "formatter": "standard",
                "level": settings.LOG_LEVEL,
                "filename": os.path.join(log_dir, "app.log"),
                "when": "midnight",
                "backupCount": 14,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "uvicorn": {"handlers": ["console", "file"], "level": settings.LOG_LEVEL, "propagate": False},
            "uvicorn.error": {"handlers": ["console", "file"], "level": settings.LOG_LEVEL, "propagate": False},
            "uvicorn.access": {"handlers": ["console", "file"], "level": settings.LOG_LEVEL, "propagate": False},
        },
        "root": {
            "handlers": ["console", "file"],
            "level": settings.LOG_LEVEL,
        },
    })
