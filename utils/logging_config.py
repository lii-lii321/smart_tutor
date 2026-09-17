"""
日志体系：统一控制台 + 可选按天轮转文件。

在此之前的仓库没有任何 logging 配置，各模块的 logger.info 全部被丢弃、
WARNING 走 lastResort 裸吐 stderr。main.py 的 lifespan 调用 setup_logging() 后：
- 应用日志写入 stdout（容器环境由 docker json-file 驱动收集）；
- LOG_TO_FILE=true 时（本地开发默认）同时写入 logs/app.log（按天轮转，保留 14 天）；
- 未配置 LOG_LEVEL 时默认 INFO。

多进程（uvicorn --workers 2）下 Python 的 TimedRotatingFileHandler 轮转 rename
不是进程安全操作，官方明确不保证多进程共享同一文件——生产容器必须用
LOG_TO_FILE=false 走纯 stdout（compose 已固定），文件轮转仅限单进程本地开发。
"""
import logging
import logging.config
import os

from config import settings

_LOG_FORMAT = "%(asctime)s %(levelname)-7s [%(name)s] %(message)s"


def setup_logging() -> None:
    use_file = settings.LOG_TO_FILE
    if use_file:
        os.makedirs(settings.LOG_DIR, exist_ok=True)

    handlers = ["console"] + (["file"] if use_file else [])
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
            **({
                "file": {
                    "class": "logging.handlers.TimedRotatingFileHandler",
                    "formatter": "standard",
                    "level": settings.LOG_LEVEL,
                    "filename": os.path.join(settings.LOG_DIR, "app.log"),
                    "when": "midnight",
                    "backupCount": 14,
                    "encoding": "utf-8",
                },
            } if use_file else {}),
        },
        "loggers": {
            "uvicorn": {"handlers": handlers, "level": settings.LOG_LEVEL, "propagate": False},
            "uvicorn.error": {"handlers": handlers, "level": settings.LOG_LEVEL, "propagate": False},
            "uvicorn.access": {"handlers": handlers, "level": settings.LOG_LEVEL, "propagate": False},
        },
        "root": {
            "handlers": handlers,
            "level": settings.LOG_LEVEL,
        },
    })
