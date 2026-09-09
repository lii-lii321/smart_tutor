"""
收尾批次回归测试：金额 Decimal 半进一舍入、薪资单位归一化、
历史分成功率加权、财务筛选与 CSV 导出、导入金额上限。
"""
import asyncio
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_TMP = tempfile.NamedTemporaryFile(suffix="_polish.db", delete=False)
_TMP.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP.name.replace(os.sep, '/')}"
os.environ["DEV_MODE"] = "true"
os.environ["JWT_SECRET"] = "test-secret-for-final-polish-012345678"
os.environ["OWNER_ACCESS_CODE"] = "test-boss-code"

import httpx  # noqa: E402

import database as database_mod  # noqa: E402
from database import _get_sessionmaker, init_db  # noqa: E402
from main import app  # noqa: E402
from models.domain import Gender, Order, OrderStatus, Teacher, TeacherResume, Tenant  # noqa: E402
from services.auth import create_jwt  # noqa: E402
from services.calculator import calculate_info_fee, calculate_refund  # noqa: E402
from services.recommendation import parse_expected_rate  # noqa: E402

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


def tenant_token(tenant_id: int) -> str:
    return create_jwt(sub=f"tenant_admin_{tenant_id}", role="tenant_admin", tenant_id=tenant_id)


def teacher_token(teacher_id: int) -> str:
    return create_jwt(sub=f"teacher_{teacher_id}", role="teacher")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_calculator_decimal_half_up():
    # 133.33 × 1.5 = 199.995：二进制浮点会舍成 199.99，Decimal 半进一应为 200.00
    fee = calculate_info_fee(133.33, 1, False)
    assert float(fee["total_info_fee"]) == 200.0, f"应半进一为 200，实际 {fee['total_info_fee']}"
    assert float(fee["deposit"]) == 100.0
    assert float(fee["balance"]) == 100.0

    refund = calculate_refund(100.0, 60.0, False, False)
    # 100 − 60×0.7 = 58.00
    assert float(refund) == 58.0

    # 原有边界行为不变
    assert float(calculate_refund(300.0, 200.0, True, False)) == 0.0
    try:
        calculate_info_fee(10.0, 1, False)
        assert False, "过低课酬应被拒绝"
    except ValueError:
        pass
    print("[OK] test_calculator_decimal_half_up")


def test_expected_rate_unit_normalization():
    assert parse_expected_rate("180-220/次") == 200.0
    assert parse_expected_rate("200/次") == 200.0
    assert parse_expected_rate("3000/月") == 375.0, "月薪应折算为次薪（÷8）"
    assert parse_expected_rate("50/小时") == 100.0, "时薪应按 2 小时折算（×2）"
    assert parse_expected_rate("时薪 80") == 160.0
    assert parse_expected_rate("面议") is None
    assert parse_expected_rate(None) is None
    print("[OK] test_expected_rate_unit_normalization")


async def _setup() -> dict:
    await init_db()
    sm = _get_sessionmaker()
    async with sm() as s:
        tenant = Tenant(tenant_name="收尾中介", invite_code="polish01", contact_wechat="wx_f")
        teacher = Teacher(
            openid="f_t1", name="收尾教员", gender=Gender.male,
            phone="13800000001", wechat_id="wx_ft", school="测试大学", is_985_211=True,
        )
        s.add_all([tenant, teacher])
        await s.flush()
        resume = TeacherResume(
            teacher_id=teacher.id, title="默认简历",
            teaching_subjects="数学", teaching_grades="初一-初三",
            experience="两年家教经验",
        )
        s.add(resume)
        await s.flush()
        order = Order(
            tenant_id=tenant.id, raw_id="POLISH-001", raw_text="收尾测试订单",
            grade_subject="初三数学", requirements="", price_total="200/次",
            base_price=200.0, weekly_frequency=2, is_summer_vacation=False,
            calculated_info_fee=200.0, deposit_amount=100.0, balance_amount=100.0,
            exact_address="地址A", parent_phone="13800000000",
            fuzzy_address="成都市A", lng=104.06, lat=30.57,
            status=OrderStatus.recruiting,
            expired_at=datetime.datetime.utcnow() + datetime.timedelta(hours=72),
        )
        s.add(order)
        await s.commit()
        return {"tenant_id": tenant.id, "teacher_id": teacher.id, "resume_id": resume.id, "order_id": order.id}


async def _deposit_once(d, client) -> None:
    resp = await client.post(
        f"{BASE}/api/v1/applications/",
        params={"order_id": d["order_id"], "resume_id": d["resume_id"]},
        headers=auth(teacher_token(d["teacher_id"])),
    )
    assert resp.status_code == 200, resp.text
    app_id = resp.json()["id"]
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/shortlist",
        headers=auth(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text
    resp = await client.post(
        f"{BASE}/api/v1/applications/{app_id}/confirm-deposit",
        headers=auth(tenant_token(d["tenant_id"])),
    )
    assert resp.status_code == 200, resp.text


async def _test_financial_filter_and_export():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        await _deposit_once(d, client)

        # 类型筛选：只看退款支出 → 明细为空；
        # 汇总保持期间口径（不随类型收窄），四类金额仍然齐全
        resp = await client.get(
            f"{BASE}/api/v1/financial-records/",
            params={"type": "refund_out"},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200
        assert resp.json()["records"] == []
        assert resp.json()["deposit_in"] == 100.0
        assert resp.json()["net_amount"] == 100.0

        # 类型筛选：只看定金收入
        resp = await client.get(
            f"{BASE}/api/v1/financial-records/",
            params={"type": "deposit_in"},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.json()["deposit_in"] == 100.0
        assert len(resp.json()["records"]) == 1

        # 日期筛选：今天有记录
        # 注意用 UTC 日期：created_at 存 naive UTC，筛选口径是 UTC 自然日；
        # 用本地 date.today() 在 0-8 点（东八区）会因跨午夜误判为"无记录"
        utc_today = datetime.datetime.utcnow().date().isoformat()
        resp = await client.get(
            f"{BASE}/api/v1/financial-records/",
            params={"start_date": utc_today, "end_date": utc_today},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert len(resp.json()["records"]) == 1

        # 无关日期 → 空
        resp = await client.get(
            f"{BASE}/api/v1/financial-records/",
            params={"start_date": "2000-01-01", "end_date": "2000-01-02"},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.json()["records"] == []

        # CSV 导出：类型筛选生效、含 BOM 与中文表头
        resp = await client.get(
            f"{BASE}/api/v1/financial-records/export",
            params={"type": "deposit_in"},
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        body = resp.content.decode("utf-8-sig")
        assert "定金收入" in body
        assert "100.00" in body
        print("[OK] test_financial_filter_and_export")


async def _test_import_amount_cap():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        resp = await client.post(
            f"{BASE}/api/v1/orders/batch-import",
            json={
                "items": [{
                    "raw_id": "CAP-001", "raw_text": "超大金额订单", "grade_subject": "初三数学",
                    "price_total": "100万/次", "base_price": 1000000.0,
                    "weekly_frequency": 1, "is_summer_vacation": False,
                    "fuzzy_address": "成都市", "lng": 104.06, "lat": 30.57,
                    "calculated_info_fee": 0, "deposit_amount": 0, "balance_amount": 0,
                }]
            },
            headers=auth(tenant_token(d["tenant_id"])),
        )
        assert resp.status_code == 422, f"超上限金额应 422: {resp.status_code}"
    print("[OK] test_import_amount_cap")


def test_financial_filter_and_export():
    _fresh_db()
    asyncio.run(_test_financial_filter_and_export())


def test_import_amount_cap():
    _fresh_db()
    asyncio.run(_test_import_amount_cap())


if __name__ == "__main__":
    test_calculator_decimal_half_up()
    test_expected_rate_unit_normalization()
    test_financial_filter_and_export()
    test_import_amount_cap()
    print("\n=== 收尾批次测试全部通过 ===")
    try:
        os.unlink(_TMP.name)
    except OSError:
        pass
