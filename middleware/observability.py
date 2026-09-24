"""
请求级可观测性：request-id 贯穿 + 请求行/慢请求日志。

- 每个请求分配 request-id（优先透传 nginx/上游注入的 X-Request-ID），
  写入响应头并放入 contextvar，logging Filter 让所有应用日志自动携带，
  出问题按 id 串起一个请求的全部日志。
- 每请求一行结构化摘要（method path status 耗时），慢请求（超过
  SLOW_REQUEST_MS）升 WARNING——线上"用户说看不到单子"时先看这里。
- 健康探针 /health 不记请求行，避免探活刷屏。
"""
import contextvars
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from config import settings

logger = logging.getLogger(__name__)

# 请求上下文：logging Filter 与业务代码均可读取当前 request-id
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdLoggingFilter(logging.Filter):
    """把当前 request-id 注入每条日志记录（无请求上下文时显示 "-"）。"""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000
            response.headers["X-Request-ID"] = request_id
            if request.url.path != "/health":
                self._log_request(request, response.status_code, duration_ms)
            return response
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            # 未处理异常：HTTPException 不会走到这里；500 级异常带上下文留痕
            logger.exception(
                "request failed %s %s %.0fms request_id=%s",
                request.method,
                request.url.path,
                duration_ms,
                request_id,
            )
            raise
        finally:
            request_id_var.reset(token)

    @staticmethod
    def _log_request(request: Request, status_code: int, duration_ms: float) -> None:
        payload = (
            f"{request.method} {request.url.path} {status_code} {duration_ms:.0f}ms"
            f" rid={request_id_var.get()}"
        )
        if duration_ms >= settings.SLOW_REQUEST_MS:
            logger.warning("slow request %s", payload)
        else:
            logger.info("request %s", payload)
