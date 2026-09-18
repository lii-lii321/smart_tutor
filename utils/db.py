"""SQLAlchemy 异步执行结果的类型收口小工具。"""
from typing import Any

from sqlalchemy import Result


def rowcount(result: Result[Any]) -> int:
    """UPDATE/DELETE 的受影响行数。

    异步 stub 把 session.execute() 的返回标为 Result，而 rowcount 实际挂在
    运行时返回的 CursorResult 上——在 stubs 层面无法直接访问，此处显式解包，
    避免各路由重复 cast。
    """
    rowcount: int = getattr(result, "rowcount", 0)
    return rowcount
