import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from database import init_db, seed_demo_data
from services.scheduler import expired_order_cleanup_loop, stop_task
from utils.logging_config import setup_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    _init_sentry()
    if settings.DEV_MODE or settings.AUTO_CREATE_SCHEMA:
        await init_db()
        await seed_demo_data()

    # 生产由独立的 scheduler 容器承担调度（DISABLE_SCHEDULER=true），API 进程只服务请求；
    # 本地开发默认 False，保持单进程内嵌调度
    cleanup_task = (
        None if settings.DISABLE_SCHEDULER else asyncio.create_task(expired_order_cleanup_loop())
    )
    yield
    await stop_task(cleanup_task)


def _init_sentry() -> None:
    """错误上报（P1-9）：DSN 未配置时完全 no-op。FastAPI/SQLAlchemy/Redis/HTTPX
    集成在 sentry-sdk 2.x 中随安装自动启用；ERROR 级日志（如审计写失败）会作为事件上报。"""
    if not settings.SENTRY_DSN:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment="development" if settings.DEV_MODE else "production",
        release=f"{settings.PROJECT_NAME}@{settings.VERSION}",
        traces_sample_rate=0.1,
        send_default_pii=False,  # 不随事件发送 IP/Cookie 等个人信息
    )


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
    # 生产环境不对外暴露接口清单
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url=None,
    openapi_url="/openapi.json" if settings.DEBUG else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.ALLOWED_ORIGINS.split(",") if origin.strip()],
    # 认证走 Authorization 头而非 Cookie，无需 credentials；
    # 同时避免误配通配 origin 时反射任意来源
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# 注册路由
from routers.v1.applications import router as applications_router
from routers.v1.audit_logs import router as audit_logs_router
from routers.v1.auth import router as auth_router
from routers.v1.financial_records import router as financial_records_router
from routers.v1.internal_stats import router as internal_stats_router
from routers.v1.notifications import router as notifications_router
from routers.v1.orders import router as orders_router
from routers.v1.public import router as public_router
from routers.v1.recommendations import router as recommendations_router
from routers.v1.resumes import router as resumes_router
from routers.v1.tenants import router as tenants_router

app.include_router(auth_router)
app.include_router(orders_router)
app.include_router(public_router)
app.include_router(applications_router)
app.include_router(resumes_router)
app.include_router(tenants_router)
app.include_router(financial_records_router)
app.include_router(recommendations_router)
app.include_router(notifications_router)
app.include_router(audit_logs_router)
app.include_router(internal_stats_router)


@app.get("/health")
async def health():
    """容器/负载均衡探活：数据库不可用返回 503；Redis 只上报状态不阻断。"""
    from sqlalchemy import text

    from database import _get_sessionmaker
    from services.order_maintenance import get_redis_client

    db_ok = False
    redis_ok = False
    try:
        sessionmaker = _get_sessionmaker()
        async with sessionmaker() as session:
            await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        pass
    try:
        redis = await get_redis_client()
        redis_ok = bool(await redis.ping())
    except Exception:
        pass

    if not db_ok:
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "database": False, "redis": redis_ok},
        )
    return {
        "status": "ok",
        "version": settings.VERSION,
        "database": True,
        "redis": redis_ok,
    }


if __name__ == "__main__":
    import uvicorn
    # 本地调试入口默认只绑定回环地址；生产部署请用 gunicorn/uvicorn 显式指定
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
