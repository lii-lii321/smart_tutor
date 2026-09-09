"""
中介工作台「本月为你」ROI 聚合端点测试。

使用独立的临时 SQLite 库，不触碰 dev.db。
覆盖：当月口径过滤（上月订单不计）、成交口径（尾款时间）、资金净额口径（没收不重复计）、
租户隔离、老板全平台汇总、角色权限。

运行方式：
    python tests/test_roi_summary.py
或（安装 pytest 后）：
    pytest tests/test_roi_summary.py
"""
import asyncio
import datetime
import os
import sys
import tempfile

# 确保项目根目录可导入（与 test_smoke.py 一致）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 必须在导入 app 之前设置测试环境 ──
_TMP = tempfile.NamedTemporaryFile(suffix="_roi.db", delete=False)
_TMP.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP.name.replace(os.sep, '/')}"
os.environ["DEV_MODE"] = "true"
os.environ["JWT_SECRET"] = "test-secret-for-roi-summary-tests-0123456789"
os.environ["OWNER_ACCESS_CODE"] = "test-boss-code"

import httpx  # noqa: E402

import database as database_mod  # noqa: E402
from database import _get_sessionmaker, init_db  # noqa: E402
from main import app  # noqa: E402
from models.domain import (  # noqa: E402
    Application,
    ApplicationStatus,
    FinancialRecord,
    FinancialType,
    Gender,
    Order,
    OrderStatus,
    Teacher,
    TeacherResume,
    Tenant,
)

BASE = "http://test"


def _fresh_db() -> None:
    """每个测试使用全新的临时库：释放旧引擎并删除库文件。"""
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
    from services.auth import create_jwt
    return create_jwt(sub=f"tenant_admin_{tenant_id}", role="tenant_admin", tenant_id=tenant_id)


def boss_token() -> str:
    from services.auth import create_jwt
    return create_jwt(sub="super_admin_1", role="super_admin")


def teacher_token(teacher_id: int) -> str:
    from services.auth import create_jwt
    return create_jwt(sub=f"teacher_{teacher_id}", role="teacher")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _setup() -> dict:
    await init_db()
    sm = _get_sessionmaker()
    async with sm() as s:
        t1 = Tenant(tenant_name="ROI中介A", invite_code="roia001", contact_wechat="wx_a")
        t2 = Tenant(tenant_name="ROI中介B", invite_code="roib002", contact_wechat="wx_b")
        s.add_all([t1, t2])
        await s.flush()

        th1 = Teacher(openid="roi_001", name="教员一", gender=Gender.male,
                      phone="13811111111", wechat_id="wx_t1", school="甲大学")
        th2 = Teacher(openid="roi_002", name="教员二", gender=Gender.female,
                      phone="13822222222", wechat_id="wx_t2", school="乙大学")
        s.add_all([th1, th2])
        await s.flush()
        s.add(TeacherResume(teacher_id=th1.id, title="默认简历",
                            teaching_subjects="数学", teaching_grades="初一-初三",
                            experience="两年家教经验"))
        await s.flush()

        now = datetime.datetime.utcnow()
        last_month = now - datetime.timedelta(days=40)

        def _order(tenant_id, raw_id):
            return Order(
                tenant_id=tenant_id, raw_id=raw_id, raw_text=f"文本{raw_id}",
                grade_subject="初三数学", price_total="200/次", base_price=200.0,
                weekly_frequency=2, is_summer_vacation=False,
                calculated_info_fee=200.0, deposit_amount=100.0, balance_amount=100.0,
                fuzzy_address="成都市某小区", lng=104.06, lat=30.57,
                status=OrderStatus.recruiting,
                expired_at=now + datetime.timedelta(hours=72),
            )

        o1 = _order(t1.id, "ROI-001")
        o_old = _order(t1.id, "ROI-OLD")
        o_old.created_at = last_month  # 上月录单：验证当月口径过滤
        o2 = _order(t2.id, "ROI-002")
        s.add_all([o1, o_old, o2])
        await s.flush()

        a1 = Application(order_id=o1.id, teacher_id=th1.id, tenant_id=t1.id,
                         status=ApplicationStatus.pending)
        a2 = Application(order_id=o1.id, teacher_id=th2.id, tenant_id=t1.id,
                         status=ApplicationStatus.balance_paid, balance_paid_at=now)
        a3 = Application(order_id=o2.id, teacher_id=th1.id, tenant_id=t2.id,
                         status=ApplicationStatus.pending)
        s.add_all([a1, a2, a3])
        await s.flush()

        def _fin(tenant_id, order_id, ftype, amount):
            return FinancialRecord(order_id=order_id, tenant_id=tenant_id,
                                   teacher_id=th1.id, amount=amount, type=ftype)

        s.add_all([
            _fin(t1.id, o1.id, FinancialType.deposit_in, 100),
            _fin(t1.id, o1.id, FinancialType.balance_in, 100),
            _fin(t1.id, o1.id, FinancialType.refund_out, 30),
            _fin(t1.id, o1.id, FinancialType.forfeit, 100),  # 没收：不重复计入净额
            _fin(t2.id, o2.id, FinancialType.deposit_in, 999),
        ])
        await s.commit()

        return {
            "tenant1_id": t1.id, "tenant2_id": t2.id,
            "teacher1_id": th1.id, "teacher2_id": th2.id,
        }


async def _fetch(client, token):
    resp = await client.get(f"{BASE}/api/v1/tenants/me/roi-summary", headers=auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _test_roi_summary():
    d = await _setup()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # ── 中介 A：只看自己的当月数据 ──
        roi = await _fetch(client, tenant_token(d["tenant1_id"]))
        assert roi["month"] == datetime.datetime.utcnow().strftime("%Y-%m")
        assert roi["orders_imported"] == 1, "上月的 o_old 不应计入当月录单"
        assert roi["applications_received"] == 2
        assert roi["deals_completed"] == 1, "成交口径 = 本月支付尾款"
        assert roi["deposit_in"] == 100.0
        assert roi["balance_in"] == 100.0
        assert roi["refund_out"] == 30.0
        assert roi["forfeit"] == 100.0
        assert roi["net_amount"] == 170.0, "净额 = 定金 + 尾款 − 退款，没收不重复计入"
        assert roi["teacher_pool"] == 2, "教员库 = 与本租户发生过投递的去重教员"

        # ── 中介 B：租户隔离 ──
        roi_b = await _fetch(client, tenant_token(d["tenant2_id"]))
        assert roi_b["orders_imported"] == 1
        assert roi_b["applications_received"] == 1
        assert roi_b["deals_completed"] == 0
        assert roi_b["net_amount"] == 999.0
        assert roi_b["teacher_pool"] == 1

        # ── 老板：全平台汇总 ──
        roi_boss = await _fetch(client, boss_token())
        assert roi_boss["orders_imported"] == 2, "老板视角聚合全平台当月录单"
        assert roi_boss["net_amount"] == 1169.0
        assert roi_boss["teacher_pool"] == 2

        # ── 教员角色无权访问 ──
        resp = await client.get(
            f"{BASE}/api/v1/tenants/me/roi-summary",
            headers=auth(teacher_token(d["teacher1_id"])),
        )
        assert resp.status_code == 403


def test_roi_summary():
    _fresh_db()
    asyncio.run(_test_roi_summary())


if __name__ == "__main__":
    test_roi_summary()
    print("ROI summary tests passed.")
