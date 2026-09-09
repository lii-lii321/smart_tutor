"""
财务流水可读性测试：流水与 CSV 导出应携带订单科目/原始单号/教员姓名，
教员结算单应透传 raw_order_id（历史回归：曾因响应模型丢字段导致前端拿不到）。

使用独立的临时 SQLite 库，不触碰 dev.db。
"""
import asyncio
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMP = tempfile.NamedTemporaryFile(suffix="_finlabel.db", delete=False)
_TMP.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP.name.replace(os.sep, '/')}"
os.environ["DEV_MODE"] = "true"
os.environ["JWT_SECRET"] = "test-secret-for-financial-label-tests-012345"
os.environ["OWNER_ACCESS_CODE"] = "test-boss-code"

import httpx  # noqa: E402

import database as database_mod  # noqa: E402
from database import _get_sessionmaker, init_db  # noqa: E402
from main import app  # noqa: E402
from models.domain import (  # noqa: E402
    FinancialRecord,
    FinancialType,
    Gender,
    Order,
    OrderStatus,
    Teacher,
    Tenant,
)

BASE = "http://test"


def _fresh_db() -> None:
    from config import settings
    settings.DATABASE_URL = f"sqlite+aiosqlite:///{_TMP.name.replace(os.sep, '/')}"

    engine = database_mod._engine
    if engine is not None:
        try:
            asyncio.run(engine.dispose())
        except Exception:
            pass
        database_mod._engine = None
        database_mod._async_sessionmaker = None
    try:
        os.unlink(_TMP.name)
    except OSError:
        pass


def _token(sub: str, role: str, tenant_id: int | None = None) -> str:
    from services.auth import create_jwt
    return create_jwt(sub=sub, role=role, tenant_id=tenant_id)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup() -> dict:
    await init_db()
    sm = _get_sessionmaker()
    async with sm() as s:
        tenant = Tenant(tenant_name="流水中介", invite_code="finl001", contact_wechat="wx_f")
        teacher = Teacher(openid="fin_001", name="王老师", gender=Gender.male,
                          phone="13833333333", wechat_id="wx_wang", school="甲大学")
        s.add_all([tenant, teacher])
        await s.flush()

        order = Order(
            tenant_id=tenant.id, raw_id="单24090701", raw_text="测试文本",
            grade_subject="初三数学", price_total="200/次", base_price=200.0,
            weekly_frequency=2, is_summer_vacation=False,
            calculated_info_fee=200.0, deposit_amount=100.0, balance_amount=100.0,
            fuzzy_address="成都市某小区", lng=104.06, lat=30.57,
            status=OrderStatus.trial_in_progress,
            expired_at=datetime.datetime.utcnow() + datetime.timedelta(hours=72),
        )
        s.add(order)
        await s.flush()
        s.add(FinancialRecord(order_id=order.id, tenant_id=tenant.id, teacher_id=teacher.id,
                              amount=100, type=FinancialType.deposit_in, operator_role="tenant_admin"))
        await s.commit()
        return {"tenant_id": tenant.id, "teacher_id": teacher.id}


async def _test_financial_labels():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        tenant_h = auth(_token(f"tenant_admin_{d['tenant_id']}", "tenant_admin", d["tenant_id"]))

        # 中介流水列表：带科目/单号/教员姓名
        resp = await client.get(f"{BASE}/api/v1/financial-records/", headers=tenant_h)
        assert resp.status_code == 200, resp.text
        record = resp.json()["records"][0]
        assert record["order_subject"] == "初三数学"
        assert record["order_raw_id"] == "单24090701"
        assert record["teacher_name"] == "王老师"
        assert record["teacher_school"] == "甲大学"
        assert resp.json()["net_amount"] == 100.0

        # CSV 导出：表头与内容都包含可读字段
        resp = await client.get(f"{BASE}/api/v1/financial-records/export", headers=tenant_h)
        assert resp.status_code == 200
        csv_text = resp.text
        assert "订单科目" in csv_text and "教员姓名" in csv_text and "原始单号" in csv_text
        assert "初三数学" in csv_text and "王老师" in csv_text and "单24090701" in csv_text

        # 教员结算单：raw_order_id 必须真实透传（历史回归）
        teacher_h = auth(_token(f"teacher_{d['teacher_id']}", "teacher"))
        resp = await client.get(f"{BASE}/api/v1/financial-records/mine", headers=teacher_h)
        assert resp.status_code == 200, resp.text
        mine = resp.json()["records"][0]
        assert mine["raw_order_id"] == "单24090701"
        assert mine["order_subject"] == "初三数学"


def test_financial_labels():
    _fresh_db()
    asyncio.run(_test_financial_labels())


if __name__ == "__main__":
    test_financial_labels()
    print("Financial label tests passed.")
