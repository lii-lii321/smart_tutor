from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import settings
from database import init_db, seed_demo_data
from services.scheduler import expired_order_cleanup_loop, stop_task


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await seed_demo_data()
    import asyncio

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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
from routers.v1.auth import router as auth_router
from routers.v1.orders import router as orders_router
from routers.v1.public import router as public_router
from routers.v1.applications import router as applications_router
from routers.v1.resumes import router as resumes_router
from routers.v1.tenants import router as tenants_router
from routers.v1.financial_records import router as financial_records_router

app.include_router(auth_router)
app.include_router(orders_router)
app.include_router(public_router)
app.include_router(applications_router)
app.include_router(resumes_router)
app.include_router(tenants_router)
app.include_router(financial_records_router)


@app.get("/health")
async def health():
    return {"status": "ok", "version": settings.VERSION}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
