"""
统一时间入口：当前 UTC 时刻（naive，与历史 datetime.utcnow() 完全同值）。

全库存 naive UTC 是既定约定（MySQL 会话时区固定 +00:00，读取按 UTC 解释，
见 docs/adr）。datetime.utcnow() 在 Python 3.12+ 为 DeprecationWarning，
统一走本函数：取值语义不变，未来若升级解释器或改 aware UTC 只动这里。
"""
import datetime


def utcnow() -> datetime.datetime:
    # 不用 datetime.UTC 别名（3.11+）：保持与本地/CI 解释器版本下限 3.10 兼容
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)  # noqa: UP017
