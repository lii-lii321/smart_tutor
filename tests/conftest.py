"""
共享测试基座。

- 模块级注入默认环境变量（必须在任何测试 import config/database 之前生效）；
  存量测试文件在自身模块级直接赋值 os.environ 可正常覆盖。
- 提供按用例隔离的 db / client fixture（每用例独立临时 SQLite + 全新 engine）。
- 提供造数工厂 make_tenant / make_teacher / make_order，吸收各文件重复样板。
"""
import itertools
import os
import sys
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.domain import Order, Teacher, Tenant

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TEACHER_SEQ = itertools.count(1)

_TMP = tempfile.NamedTemporaryFile(suffix="_conftest.db", delete=False)
_TMP.close()
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_TMP.name.replace(os.sep, '/')}")
os.environ.setdefault("DEV_MODE", "true")
os.environ.setdefault("AUTO_CREATE_SCHEMA", "false")
os.environ.setdefault("JWT_SECRET", "conftest-default-secret-0123456789abcdef")
os.environ.setdefault("OWNER_ACCESS_CODE", "conftest-boss-code")

BASE = "http://test"


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def tenant_token(tenant_id: int) -> str:
    from services.auth import create_jwt
    return create_jwt(sub=f"tenant_admin_{tenant_id}", role="tenant_admin", tenant_id=tenant_id)


def teacher_token(teacher_id: int) -> str:
    from services.auth import create_jwt
    return create_jwt(sub=f"teacher_{teacher_id}", role="teacher")


async def make_tenant(session, invite_code: str, *, is_active: bool = True, name: str = "测试中介") -> "Tenant":
    from models.domain import Tenant
    tenant = Tenant(
        tenant_name=name,
        invite_code=invite_code,
        contact_wechat="wx_test",
        password_hash="$2b$12$" + "x" * 53,  # 占位哈希：bcrypt(72字节截断)格式合法即可
        is_active=is_active,
    )
    session.add(tenant)
    await session.flush()
    return tenant


async def make_teacher(session, openid: str, *, phone: str | None = None, name: str = "测试教员") -> "Teacher":
    from models.domain import Gender, Teacher
    teacher = Teacher(
        openid=openid,
        name=name,
        gender=Gender.male,
        phone=phone or f"138{next(_TEACHER_SEQ):08d}",
        wechat_id=f"wx_{openid}",
        school="测试大学",
        is_985_211=True,
    )
    session.add(teacher)
    await session.flush()
    return teacher


async def make_order(session, tenant_id: int, raw_id: str, *, lng: float = 104.065735, lat: float = 30.659462) -> "Order":
    import datetime

    from models.domain import Order, OrderStatus
    order = Order(
        tenant_id=tenant_id,
        raw_id=raw_id,
        raw_text=f"【{raw_id}】测试订单文本",
        grade_subject="初三数学",
        requirements="",
        price_total="200/次",
        base_price=200.0,
        weekly_frequency=2,
        is_summer_vacation=False,
        calculated_info_fee=200.0,
        deposit_amount=100.0,
        balance_amount=100.0,
        fuzzy_address="成都市天府大道",
        lng=lng,
        lat=lat,
        status=OrderStatus.recruiting,
        expired_at=datetime.datetime.utcnow() + datetime.timedelta(hours=72),
    )
    session.add(order)
    await session.flush()
    return order


async def _reset_engine(database_mod, settings, url: str) -> None:
    """更换 DATABASE_URL 并丢弃全局 engine 缓存（Windows 下先释放文件句柄）。"""
    settings.DATABASE_URL = url
    engine = database_mod._engine
    if engine is not None:
        try:
            await engine.dispose()
        except Exception:
            pass
    database_mod._engine = None
    database_mod._async_sessionmaker = None


async def _new_session(tmp_path):
    import database as database_mod
    import models.domain  # noqa: F401  必须先注册模型，否则 create_all 建不出表
    from config import settings
    from database import _get_sessionmaker, init_db

    await _reset_engine(database_mod, settings, f"sqlite+aiosqlite:///{(tmp_path / 'case.db').as_posix()}")
    await init_db()
    sessionmaker = _get_sessionmaker()
    return sessionmaker


async def _dispose_engine() -> None:
    import database as database_mod
    engine = database_mod._engine
    if engine is not None:
        try:
            await engine.dispose()
        except Exception:
            pass
    database_mod._engine = None
    database_mod._async_sessionmaker = None


import httpx  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture()
async def db(tmp_path):
    """每用例独立全新数据库，yield 一个可直接造数的 AsyncSession。"""
    sessionmaker = await _new_session(tmp_path)
    async with sessionmaker() as session:
        yield session
    await _dispose_engine()


@pytest.fixture()
async def client(db):
    """依赖 db fixture 保证建表完成；ASGI 进程内调用，不触发 lifespan。"""
    from main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as c:
        yield c
