"""
DEV_MODE 专用：为 tx886 批量生成 100 笔均匀分布的演示订单。

- 学科均匀（语数英理化生政史地 + 素质类），年级覆盖小学/初中/高中
- 课酬 100-400/次，周频次 1-4 次随机
- 发布时间撒在近 60 天；到期时间随生命周期自然分化：
  * 72h 内发布 → 招聘中（到期时间各异，含临期单）
  * 更早发布   → 70% 模拟重新发布（仍在招聘、到期时间重置），30% 已归档
- 坐标按成都各区分布 + 抖动，地图点位铺开

幂等：检测到 BATCH- 前缀订单时跳过。
运行方式：python scripts/seed_orders_bulk.py [数量，默认100]
"""
import asyncio
import datetime
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DEV_MODE", "true")

from sqlalchemy import func, select  # noqa: E402

from config import settings  # noqa: E402
from database import _get_sessionmaker, init_db  # noqa: E402
from models.domain import Order, OrderStatus, Tenant  # noqa: E402
from services.calculator import calculate_info_fee  # noqa: E402

NOW = datetime.datetime.utcnow()
random.seed(20260908)  # 固定种子：可复现的均匀分布

SUBJECTS = ["数学", "语文", "英语", "物理", "化学", "生物", "政治", "地理", "历史"]
GRADES = ["三年级", "五年级", "初一", "初二", "初三", "高一", "高二", "高三"]
ELECTIVES = ["少儿编程", "钢琴", "书法"]
DISTRICTS = [
    ("锦江区", 104.081, 30.657), ("青羊区", 104.062, 30.673), ("武侯区", 104.043, 30.642),
    ("金牛区", 104.051, 30.691), ("成华区", 104.101, 30.659), ("高新区", 104.065, 30.544),
    ("天府新区", 104.071, 30.486), ("双流区", 103.923, 30.574), ("龙泉驿区", 104.274, 30.556),
    ("郫都区", 103.900, 30.795), ("温江区", 103.856, 30.682), ("新都区", 104.159, 30.824),
]
ESTATES = ["桐梓林片区", "春熙路片区", "光华村片区", "抚琴片区", "建设路片区", "天府三街",
           "华阳街道", "东升街道", "龙泉街道", "犀浦街道", "金沙片区", "狮子山片区",
           "万年场片区", "麓湖片区", "外双楠", "九眼桥片区", "茶店子", "八里小区"]
REQUIREMENTS = [
    "一本以上在校生，有耐心", "985/211 优先，能长期带", "女教员优先，性格开朗",
    "有提分经验，擅长梳理考点", "研究生优先，周末可上门", "经验丰富，能查漏补缺",
    "川大/电子科大教员优先", "讲解细致，作业跟进及时", "",
]


async def main() -> None:
    if not settings.DEV_MODE:
        print("仅限 DEV_MODE 环境运行，拒绝执行。")
        return

    total = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    await init_db()
    sm = _get_sessionmaker()
    async with sm() as s:
        exists = await s.scalar(
            select(func.count()).select_from(Order).where(Order.raw_id.like("BATCH-%"))
        )
        if exists:
            print(f"已存在 {exists} 笔 BATCH- 订单，跳过（脚本幂等）。")
            return

        tenant = (await s.execute(select(Tenant).where(Tenant.invite_code == "tx886"))).scalar_one()

        combos = []
        for i in range(total):
            if i % 11 == 10:  # 每 11 笔插 1 笔素质类，保持学科大致均匀
                subject = ELECTIVES[(i // 11) % len(ELECTIVES)]
                grade = random.choice(["三年级", "五年级", "初一"])
            else:
                subject = SUBJECTS[i % len(SUBJECTS)]
                grade = random.choice(GRADES)
            combos.append((grade, subject))

        stats = {"recruiting": 0, "archived": 0}
        for i, (grade, subject) in enumerate(combos, start=1):
            district, dlng, dlat = random.choice(DISTRICTS)
            estate = random.choice(ESTATES)
            base = random.choice([120, 150, 160, 180, 200, 220, 240, 260, 280, 300, 320, 350])
            freq = random.choice([1, 2, 2, 3, 3, 4])
            fee = calculate_info_fee(base, freq, False)
            age_days = random.uniform(0, 60)

            if age_days <= 3:
                status = OrderStatus.recruiting
                expired_at = NOW + datetime.timedelta(hours=random.uniform(4, 72))
                created_at = NOW - datetime.timedelta(hours=random.uniform(1, age_days * 24 if age_days > 0 else 24))
            else:
                created_at = NOW - datetime.timedelta(days=age_days)
                if random.random() < 0.7:  # 老单重新发布，仍招聘
                    status = OrderStatus.recruiting
                    expired_at = NOW + datetime.timedelta(hours=random.uniform(6, 72))
                else:  # 生命周期走完，已归档
                    status = OrderStatus.archived
                    expired_at = created_at + datetime.timedelta(hours=72)
            stats["recruiting" if status == OrderStatus.recruiting else "archived"] += 1

            s.add(Order(
                tenant_id=tenant.id,
                raw_id=f"BATCH-{i:04d}",
                raw_text=f"{grade}{subject} {base}/次 每周{freq}次 成都市{district}{estate}（批量演示数据）",
                grade_subject=f"{grade}{subject}",
                requirements=random.choice(REQUIREMENTS),
                price_total=f"{base}/次",
                base_price=float(base),
                weekly_frequency=freq,
                calculated_info_fee=fee["total_info_fee"],
                deposit_amount=fee["deposit"],
                balance_amount=fee["balance"],
                fuzzy_address=f"成都市{district}{estate}",
                lng=round(dlng + random.uniform(-0.012, 0.012), 6),
                lat=round(dlat + random.uniform(-0.012, 0.012), 6),
                status=status,
                expired_at=expired_at,
                created_at=created_at,
            ))

        await s.commit()

        by_subject = {}
        for grade, subject in combos:
            by_subject[subject] = by_subject.get(subject, 0) + 1
        print(f"播种完成：{total} 笔 BATCH- 订单")
        print("  状态：", stats)
        print("  学科分布：", dict(sorted(by_subject.items(), key=lambda kv: -kv[1])))


if __name__ == "__main__":
    asyncio.run(main())
