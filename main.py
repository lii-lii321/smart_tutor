import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from database import init_db, seed_demo_data
from services.scheduler import expired_order_cleanup_loop, stop_task


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.DEV_MODE or settings.AUTO_CREATE_SCHEMA:
        await init_db()
        await seed_demo_data()

    cleanup_task = asyncio.create_task(expired_order_cleanup_loop())
    yield
    await stop_task(cleanup_task)


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
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
from routers.v1.auth import router as auth_router
from routers.v1.orders import router as orders_router
from routers.v1.public import router as public_router
from routers.v1.applications import router as applications_router
from routers.v1.resumes import router as resumes_router
from routers.v1.tenants import router as tenants_router
from routers.v1.financial_records import router as financial_records_router
from routers.v1.recommendations import router as recommendations_router
from routers.v1.notifications import router as notifications_router

app.include_router(auth_router)
app.include_router(orders_router)
app.include_router(public_router)
app.include_router(applications_router)
app.include_router(resumes_router)
app.include_router(tenants_router)
app.include_router(financial_records_router)
app.include_router(recommendations_router)
app.include_router(notifications_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.VERSION}


if __name__ == "__main__":
    import uvicorn
    # 本地调试入口默认只绑定回环地址；生产部署请用 gunicorn/uvicorn 显式指定
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
