"""
DEV_MODE 专用：为当前库补充一批成体系的演示数据。

覆盖场景：
- 8 名新教员（覆盖各院校/科目/常驻地，含坐标供地图展示）
- tx886 下 9 笔新订单：招聘中 / 试课中 / 已成交×2 / 已退款 / 定金没收(forfeited) / 归档 等
- jj2026 下 2 笔订单（用于测试租户隔离）
- 与订单状态严格自洽的投递、资金流水（定金/尾款/退款/没收）、成交评价与站内通知

幂等：检测到已存在 TEST- 前缀订单时直接跳过，不产生重复数据。
运行方式：python scripts/seed_test_data.py（仅限 DEV_MODE）
"""
import asyncio
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DEV_MODE", "true")

from sqlalchemy import select, func  # noqa: E402

import database as database_mod  # noqa: E402
from config import settings  # noqa: E402
from database import init_db, _get_sessionmaker  # noqa: E402
from models.domain import (  # noqa: E402
    Application, ApplicationStatus, FinancialRecord, FinancialType,
    Gender, Notification, Order, OrderReview, OrderStatus, Teacher,
    TeacherResume, Tenant,
)
from services.calculator import calculate_info_fee  # noqa: E402
from services.auth import hash_password  # noqa: E402

NOW = datetime.datetime.utcnow()


def ago(hours: float) -> datetime.datetime:
    return NOW - datetime.timedelta(hours=hours)


async def main() -> None:
    if not settings.DEV_MODE:
        print("仅限 DEV_MODE 环境运行，拒绝执行。")
        return

    await init_db()
    sm = _get_sessionmaker()
    async with sm() as s:
        exists = await s.scalar(
            select(func.count()).select_from(Order).where(Order.raw_id.like("TEST-%"))
        )
        if exists:
            print(f"已存在 {exists} 笔 TEST- 演示订单，跳过（脚本幂等）。如需重造请先清理数据。")
            return

        tenant = (await s.execute(select(Tenant).where(Tenant.invite_code == "tx886"))).scalar_one()
        tenant_b = (await s.execute(select(Tenant).where(Tenant.invite_code == "jj2026"))).scalar_one()
        pwd = hash_password("dev123456")

        # ── 新教员 ──
        new_teachers = [
            ("seed_t01", "罗老师", Gender.female, "13700010001", "luo_math", "四川大学", "数学学院", "研二",
             True, False, False, True, 104.081, 30.630, "成都·武侯区川大附近", "初中数学、高中数学", "初一-高三"),
            ("seed_t02", "周老师", Gender.male, "13700010002", "zhou_physics", "西南交通大学", "物理学院", "博一",
             True, True, False, True, 103.922, 30.756, "成都·犀浦大学城", "高中物理、初中物理", "初三-高三"),
            ("seed_t03", "郑老师", Gender.female, "13700010003", "zheng_eng", "四川师范大学", "外国语学院", "大四",
             False, False, False, False, 104.096, 30.631, "成都·锦江区狮子山", "初中英语、小学英语", "小四-初三"),
            ("seed_t04", "吴老师", Gender.male, "13700010004", "wu_chem", "成都理工大学", "化学学院", "研一",
             False, True, False, False, 104.149, 30.678, "成都·成华区理工校区的", "高中化学", "高一-高三"),
            ("seed_t05", "何老师", Gender.male, "13700010005", "he_cs", "电子科技大学", "计算机学院", "研二",
             True, True, False, True, 104.070, 30.538, "成都·高新区麓湖", "少儿编程、信息学奥赛", "小四-初三"),
            ("seed_t06", "秦老师", Gender.female, "13700010006", "qin_chinese", "四川大学", "文新学院", "研三",
             True, False, False, True, 104.002, 30.668, "成都·青羊区金沙", "初中语文、高中语文", "初一-高三"),
            ("seed_t07", "孙老师", Gender.female, "13700010007", "sun_piano", "四川音乐学院", "钢琴系", "大四",
             False, False, False, False, 104.041, 30.684, "成都·金牛区抚琴", "钢琴启蒙、少儿钢琴", "幼儿-初中"),
            ("seed_t08", "谢老师", Gender.male, "13700010008", "xie_math", "西南民族大学", "数学学院", "大四",
             False, False, False, False, 104.044, 30.577, "成都·武侯区桐梓林", "小学数学、初中数学", "小三-初三"),
        ]
        teacher_by_openid = {}
        for openid, name, gender, phone, wx, school, major, grade, f985, f211, f_double, combined, lng, lat, area, subjects, grades in new_teachers:
            teacher = Teacher(
                openid=openid, name=name, gender=gender, phone=phone, wechat_id=wx,
                school=school, major=major, grade=grade,
                is_985_211=combined or f985 or f211, is_985=f985, is_211=f211,
                is_double_first_class=combined or f_double,
                highlights="讲解耐心，提分经验丰富",
                password_hash=pwd, lng=lng, lat=lat, home_area=area,
            )
            s.add(teacher)
            await s.flush()
            s.add(TeacherResume(
                teacher_id=teacher.id, title=f"{name}默认简历",
                teaching_subjects=subjects, teaching_grades=grades,
                experience="一对一辅导经验丰富，熟悉考点与错题复盘。",
                strengths="条理清晰，善于因材施教", availability="周中晚上与周末全天",
                expected_rate="180-280/次", is_default=True,
            ))
            teacher_by_openid[teacher.name[0]] = teacher

        # 已有演示教员（用于打通与老数据的联动）
        known = {t.name: t for t in (await s.execute(select(Teacher).where(Teacher.phone.like("139000000%")))).scalars()}

        def T(surname: str) -> Teacher:
            return teacher_by_openid.get(surname) or known[f"{surname}老师"]

        async def make_order(raw_id, subject, price_total, base_price, freq, address, lng, lat,
                             status=OrderStatus.recruiting, created_hours_ago=24.0,
                             requirements="一本以上在校生，有耐心", tenant_id=None):
            fee = calculate_info_fee(base_price, freq, False)
            order = Order(
                tenant_id=tenant_id or tenant.id, raw_id=raw_id, raw_text=f"{subject} {price_total} {address}（演示数据）",
                grade_subject=subject, requirements=requirements, price_total=price_total,
                base_price=base_price, weekly_frequency=freq,
                calculated_info_fee=fee["total_info_fee"], deposit_amount=fee["deposit"],
                balance_amount=fee["balance"], fuzzy_address=address, lng=lng, lat=lat,
                status=status,
                expired_at=NOW + datetime.timedelta(hours=72),
                created_at=ago(created_hours_ago),
            )
            s.add(order)
            await s.flush()
            return order, fee

        async def apply_teacher(order, teacher: Teacher, status: ApplicationStatus, applied_hours_ago):
            resume_id = (await s.execute(
                select(TeacherResume.id).where(TeacherResume.teacher_id == teacher.id)
                .order_by(TeacherResume.is_default.desc()).limit(1)
            )).scalar_one()
            app = Application(
                order_id=order.id, teacher_id=teacher.id, tenant_id=order.tenant_id,
                resume_id=resume_id, status=status, applied_at=ago(applied_hours_ago),
            )
            if status in (ApplicationStatus.shortlisted, ApplicationStatus.trial_in_progress,
                          ApplicationStatus.deposit_paid, ApplicationStatus.completed):
                app.shortlisted_at = ago(max(applied_hours_ago - 2, 0.1))
            if status in (ApplicationStatus.trial_in_progress, ApplicationStatus.completed):
                app.deposit_paid_at = ago(max(applied_hours_ago - 4, 0.1))
            if status == ApplicationStatus.completed:
                app.balance_paid_at = ago(max(applied_hours_ago - 6, 0.1))
            s.add(app)
            await s.flush()
            return app

        def money(order, teacher: Teacher, ftype: FinancialType, amount, remark, hours_ago):
            s.add(FinancialRecord(
                order_id=order.id, tenant_id=order.tenant_id, teacher_id=teacher.id,
                amount=amount, type=ftype, remark=remark, operator_role="tenant_admin",
                created_at=ago(hours_ago),
            ))

        # ── tx886：招聘中 ×3 ──
        o, _ = await make_order("TEST-2601", "高三数学", "300/次", 300, 2, "成都市锦江区春熙路片区", 104.081, 30.657, created_hours_ago=30)
        await apply_teacher(o, T("罗"), ApplicationStatus.shortlisted, 26)
        await apply_teacher(o, T("谢"), ApplicationStatus.pending, 8)
        o, _ = await make_order("TEST-2602", "初二英语", "180/次", 180, 3, "成都市武侯区桐梓林片区", 104.072, 30.614, created_hours_ago=20)
        await apply_teacher(o, T("郑"), ApplicationStatus.pending, 6)
        o, _ = await make_order("TEST-2603", "少儿编程", "260/次", 260, 1, "成都市高新区麓湖片区", 104.070, 30.538, created_hours_ago=12)
        await apply_teacher(o, T("何"), ApplicationStatus.pending, 3)
        db_note_deposit = "线下确认定金"

        # ── 试课中：定金已收 ──
        o, fee = await make_order("TEST-2604", "高一物理", "280/次", 280, 2, "成都市成华区建设路片区", 104.106, 30.678, created_hours_ago=60)
        app = await apply_teacher(o, T("周"), ApplicationStatus.trial_in_progress, 50)
        o.selected_teacher_id = app.teacher_id
        o.status = OrderStatus.trial_in_progress
        o.expired_at = NOW + datetime.timedelta(hours=48)
        money(o, T("周"), FinancialType.deposit_in, float(fee["deposit"]), db_note_deposit, 46)

        # ── 已成交 ×2（含评价） ──
        o, fee = await make_order("TEST-2605", "小学语文", "200/次", 200, 2, "成都市青羊区光华村片区", 104.031, 30.664, created_hours_ago=160)
        app = await apply_teacher(o, T("秦"), ApplicationStatus.completed, 150)
        o.selected_teacher_id = app.teacher_id
        o.status = OrderStatus.completed
        money(o, T("秦"), FinancialType.deposit_in, float(fee["deposit"]), db_note_deposit, 146)
        money(o, T("秦"), FinancialType.balance_in, float(fee["balance"]), "线下确认尾款", 130)
        s.add(OrderReview(order_id=o.id, application_id=app.id, tenant_id=o.tenant_id,
                          teacher_id=app.teacher_id, rating=5, comment="很负责，孩子成绩明显提升。"))

        o, fee = await make_order("TEST-2606", "初三数学", "240/次", 240, 2, "成都市金牛区抚琴片区", 104.041, 30.684, created_hours_ago=140)
        app = await apply_teacher(o, T("罗"), ApplicationStatus.completed, 130)
        o.selected_teacher_id = app.teacher_id
        o.status = OrderStatus.completed
        money(o, T("罗"), FinancialType.deposit_in, float(fee["deposit"]), db_note_deposit, 126)
        money(o, T("罗"), FinancialType.balance_in, float(fee["balance"]), "线下确认尾款", 100)
        s.add(OrderReview(order_id=o.id, application_id=app.id, tenant_id=o.tenant_id,
                          teacher_id=app.teacher_id, rating=4, comment="整体不错，时间偶尔迟到。"))
        # 落选者：他人成交后被自动关闭
        await apply_teacher(o, T("郑"), ApplicationStatus.rejected, 128)

        # ── 已退款（教员试课前取消） ──
        o, fee = await make_order("TEST-2607", "初二数学", "220/次", 220, 2, "成都市武侯区桐梓林片区", 104.072, 30.614, created_hours_ago=100)
        app = await apply_teacher(o, T("孙"), ApplicationStatus.refunded, 96)
        app.deposit_paid_at = ago(94)
        app.refunded_at = ago(80)
        money(o, T("孙"), FinancialType.deposit_in, float(fee["deposit"]), db_note_deposit, 94)
        money(o, T("孙"), FinancialType.refund_out, float(fee["deposit"]), "教员取消投递，退还定金", 80)

        # ── 定金没收（违约终态，验证新的 forfeited 状态） ──
        o, fee = await make_order("TEST-2608", "高中化学", "260/次", 260, 2, "成都市成华区万年场片区", 104.113, 30.663, created_hours_ago=90)
        app = await apply_teacher(o, T("吴"), ApplicationStatus.forfeited, 86)
        app.deposit_paid_at = ago(84)
        money(o, T("吴"), FinancialType.deposit_in, float(fee["deposit"]), db_note_deposit, 84)
        money(o, T("吴"), FinancialType.forfeit, float(fee["deposit"]), "教员违约，没收信息费", 60)

        # ── 已归档 ──
        o, _ = await make_order("TEST-2609", "高三物理", "320/次", 320, 2, "成都市锦江区狮子山片区", 104.096, 30.631,
                                status=OrderStatus.archived, created_hours_ago=200)
        await apply_teacher(o, T("周"), ApplicationStatus.rejected, 190)

        # ── jj2026：租户隔离样本 ──
        o, fee = await make_order("TEST-J01", "初中语文", "200/次", 200, 2, "成都市锦江区春熙路片区", 104.081, 30.657,
                                  created_hours_ago=26, tenant_id=tenant_b.id)
        await apply_teacher(o, T("秦"), ApplicationStatus.pending, 10)
        o, fee = await make_order("TEST-J02", "高一英语", "220/次", 220, 2, "成都市青羊区金沙片区", 104.002, 30.668,
                                  status=OrderStatus.completed, created_hours_ago=120, tenant_id=tenant_b.id)
        app = await apply_teacher(o, T("郑"), ApplicationStatus.completed, 110)
        o.selected_teacher_id = app.teacher_id
        o.status = OrderStatus.completed
        money(o, T("郑"), FinancialType.deposit_in, float(fee["deposit"]), db_note_deposit, 106)
        money(o, T("郑"), FinancialType.balance_in, float(fee["balance"]), "线下确认尾款", 90)

        # ── 站内通知：给中介留 2 条未读，方便测角标 ──
        s.add(Notification(
            tenant_id=tenant.id, title="收到新投递",
            content="「少儿编程」收到教员 何老师 的新投递，请及时审核。",
            order_id=o.id,
        ))
        s.add(Notification(
            tenant_id=tenant.id, title="订单即将过期",
            content="「初二英语」订单将于 48 小时内过期，请尽快处理。",
        ))

        await s.commit()

        # ── 汇总输出 ──
        order_rows = (await s.execute(select(Order.status, func.count()).group_by(Order.status))).all()
        app_rows = (await s.execute(select(Application.status, func.count()).group_by(Application.status))).all()
        money_rows = (await s.execute(select(FinancialRecord.type, func.count(), func.sum(FinancialRecord.amount)).group_by(FinancialRecord.type))).all()
        print("演示数据播种完成：")
        print("  订单：", {k.value: int(n) for k, n in order_rows})
        print("  投递：", {k.value: int(n) for k, n in app_rows})
        print("  流水：", {t.value: (int(n), float(total or 0)) for t, n, total in money_rows})


if __name__ == "__main__":
    asyncio.run(main())
