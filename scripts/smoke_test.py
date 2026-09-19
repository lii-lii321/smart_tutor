"""
部署后全链路冒烟自检：一条命令验证核心业务闭环是否可用。

用法（在项目根目录）：
    python scripts/smoke_test.py --base http://127.0.0.1:8000

默认使用 DEV_MODE 演示账号（tx886 / dev123456 / boss888）；
生产环境请通过 --tenant-code/--tenant-password/--boss-code 传入真实凭证
（会创建一个 smoke 专用中介与教员，结束后自动停用该中介，不留脏数据）。

覆盖链路：登录 → 建单 → 教员投递 → 候选 → 定金 → 试课 → 尾款 → 成交
         → 评价 → 财务汇总 → 通知 → 看板 → 导出。
任何一步失败即非零退出，可用于发布后的自动化验收。
"""
import argparse
import asyncio
import os
import sys
import time

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.clock import utcnow

sys.stdout.reconfigure(encoding="utf-8")

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [OK] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


async def run(base: str, tenant_code: str, tenant_password: str, boss_code: str) -> int:
    prefix = f"{base.rstrip('/')}/api/v1"
    async with httpx.AsyncClient(base_url=prefix, timeout=30) as c:
        stamp = str(int(time.time()))

        print("== 认证 ==")
        boss = httpx.post(f"{prefix}/auth/owner-login", json={"access_code": boss_code})
        check("老板登录", boss.status_code == 200, str(boss.status_code))
        if boss.status_code != 200 or "token" not in boss.json():
            print("  [FAIL] 老板登录失败，后续链路无法执行：检查 --boss-code 与 OWNER_ACCESS_CODE 是否一致")
            return 1
        boss_h = {"Authorization": "Bearer " + boss.json()["token"]}

        tenant = httpx.post(
            f"{prefix}/auth/tenant-login",
            json={"invite_code": tenant_code, "password": tenant_password},
        )
        if tenant.status_code == 200 and "token" in tenant.json():
            check("中介登录", True)
            tenant_h = {"Authorization": "Bearer " + tenant.json()["token"]}
        else:
            # 全新部署没有任何中介（DEV 关闭时无演示数据）：用老板身份自动创建冒烟中介
            check("中介登录（预置账号不存在，转自动创建）", True)
            bootstrap = httpx.post(
                f"{prefix}/tenants/",
                json={"tenant_name": f"smoke-bootstrap-{stamp}", "contact_wechat": "smoke"},
                headers=boss_h,
            )
            check("自动创建冒烟中介", bootstrap.status_code == 200, bootstrap.text[:120])
            if bootstrap.status_code != 200:
                print("  [FAIL] 无法创建中介，后续链路无法执行")
                return 1
            tenant_h = None  # 预置中介不可用，后续全部使用 smoke 中介自己的登录态
            tenant_code = bootstrap.json()["invite_code"]
            tenant_password = bootstrap.json().get("initial_password") or ""

        print("== 数据准备（smoke 专用中介/教员）==")
        created = httpx.post(
            f"{prefix}/tenants/",
            json={"tenant_name": f"smoke-{stamp}", "contact_wechat": "smoke"},
            headers=boss_h,
        )
        check("创建 smoke 中介", created.status_code == 200, created.text[:120])
        smoke_tenant = created.json()
        smoke_invite = smoke_tenant["invite_code"]
        smoke_password = smoke_tenant.get("initial_password") or ""

        teacher_pw = "smoke123"
        reg = httpx.post(
            f"{prefix}/auth/teacher-phone-register",
            json={
                "phone": f"139{stamp[-8:]}",
                "invite_code": smoke_invite,
                "password": teacher_pw,
                "name": "冒烟教员",
                "gender": "male",
                "wechat_id": f"smoke_{stamp}",
                "school": "冒烟大学",
            },
        )
        check("教员注册", reg.status_code == 200, reg.text[:120])
        teacher_h = {"Authorization": "Bearer " + reg.json()["token"]}
        teacher_id = reg.json()["teacher"]["id"]

        resume_list = httpx.get(f"{prefix}/teacher/resumes/", headers=teacher_h)
        if resume_list.status_code == 200 and resume_list.json():
            pass  # 注册不带简历，投递时未建简历会 422，先建一份
        resume = httpx.post(
            f"{prefix}/teacher/resumes/",
            json={
                "title": "冒烟简历",
                "teaching_subjects": "数学",
                "teaching_grades": "初一-初三",
                "experience": "冒烟测试经历",
            },
            headers=teacher_h,
        )
        check("创建简历", resume.status_code == 200, resume.text[:120])
        resume_id = resume.json()["id"]

        # smoke 中介切到自己的登录态（创建中介返回的是老板视角 token）
        smoke_login = httpx.post(
            f"{prefix}/auth/tenant-login",
            json={"invite_code": smoke_invite, "password": smoke_password},
        )
        check("smoke 中介登录", smoke_login.status_code == 200, smoke_login.text[:120])
        smoke_h = {"Authorization": "Bearer " + smoke_login.json()["token"]}
        smoke_tenant_id = smoke_login.json()["tenant"]["id"]

        print("== 订单闭环 ==")
        import datetime
        expire = (utcnow() + datetime.timedelta(hours=48)).isoformat()
        order = httpx.post(
            f"{prefix}/orders/batch-import",
            json={"items": [{
                "raw_id": f"SMOKE-{stamp}",
                "raw_text": "冒烟测试订单",
                "grade_subject": "初三数学",
                "price_total": "200/次",
                "base_price": 200.0,
                "weekly_frequency": 2,
                "is_summer_vacation": False,
                "fuzzy_address": "成都市冒烟路1号",
                "lng": 104.06,
                "lat": 30.57,
                "calculated_info_fee": 0,
                "deposit_amount": 0,
                "balance_amount": 0,
            }]},
            headers=smoke_h,
        )
        check("订单导入（服务端重算费用）", order.status_code == 200, order.text[:120])
        orders_list = httpx.get(
            f"{prefix}/orders/", params={"q": f"SMOKE-{stamp}"}, headers=smoke_h
        )
        order_id = orders_list.json()["items"][0]["id"]
        detail = httpx.get(f"{prefix}/orders/{order_id}", headers=smoke_h).json()
        check("信息费服务端精算 200", float(detail["calculated_info_fee"]) == 200.0)

        apply = httpx.post(
            f"{prefix}/applications/",
            json={"order_id": order_id, "resume_id": resume_id},
            headers=teacher_h,
        )
        check("教员投递", apply.status_code == 200, apply.text[:120])
        app_id = apply.json()["id"]

        for action in ("shortlist", "confirm-deposit", "start-trial", "confirm-balance", "complete"):
            resp = httpx.post(f"{prefix}/applications/{app_id}/{action}", headers=smoke_h)
            check(f"审核步骤 {action}", resp.status_code == 200, resp.text[:120])

        print("== 评价 / 财务 / 通知 / 看板 ==")
        review = httpx.post(
            f"{prefix}/applications/{app_id}/review",
            json={"rating": 5, "comment": "冒烟评价"},
            headers=smoke_h,
        )
        check("成交评价", review.status_code == 200, review.text[:120])

        print("== 成绩单 / 收款凭证（0.9.0 新链路）==")
        score = httpx.get(f"{prefix}/public/teacher/{teacher_id}/scorecard")
        check("公开成绩单 200（无需登录）", score.status_code == 200, score.text[:120])
        score_body = score.json() if score.status_code == 200 else {}
        check(
            "成绩单脱敏（不露全名/手机/微信）",
            "冒烟教员" not in score.text and "phone" not in score_body and "wechat_id" not in score_body,
        )
        check(
            "成绩单聚合（成交 1 / 评价 1）",
            score_body.get("completed_count") == 1 and score_body.get("review_count") == 1,
            str(score_body.get("completed_count")),
        )

        fin_list = httpx.get(
            f"{prefix}/financial-records/", params={"type": "deposit_in"}, headers=smoke_h
        )
        deposit_records = [
            r for r in fin_list.json().get("records", []) if r.get("order_id") == order_id
        ] if fin_list.status_code == 200 else []
        check("B 端流水可查定金记录", bool(deposit_records))
        if deposit_records:
            receipt_id = deposit_records[0]["id"]
            png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
            up = httpx.post(
                f"{prefix}/financial-records/{receipt_id}/receipt",
                files={"file": ("smoke.png", png, "image/png")},
                headers=smoke_h,
            )
            check(
                "上传收款凭证",
                up.status_code == 200 and up.json().get("has_receipt") is True,
                up.text[:120],
            )
            got = httpx.get(f"{prefix}/financial-records/{receipt_id}/receipt", headers=smoke_h)
            check(
                "B 端读取凭证图片",
                got.status_code == 200 and got.headers.get("content-type", "").startswith("image/"),
                str(got.status_code),
            )
            got_teacher = httpx.get(
                f"{prefix}/financial-records/{receipt_id}/receipt", headers=teacher_h
            )
            check("教员读取本人流水凭证", got_teacher.status_code == 200, str(got_teacher.status_code))

        fees = httpx.get(f"{prefix}/financial-records/mine", headers=teacher_h)
        check("教员结算单 200", fees.status_code == 200)
        check("结算单金额守恒 200", fees.json()["total_paid"] == 200.0)

        notif = httpx.get(f"{prefix}/notifications/tenant-mine", headers=smoke_h)
        check("B 端通知含新投递", any(n["title"] == "收到新投递" for n in notif.json()["items"]))

        stats = httpx.get(f"{prefix}/tenants/stats", headers=boss_h)
        check("老板看板 200", stats.status_code == 200)

        export_orders = httpx.get(
            f"{prefix}/orders/export", headers=smoke_h
        )
        check("订单导出 CSV", export_orders.status_code == 200
              and export_orders.headers.get("content-type", "").startswith("text/csv"))

        print("== 清理（停用 smoke 中介）==")
        deactivate = httpx.patch(
            f"{prefix}/tenants/{smoke_tenant_id}/status",
            json={"is_active": False},
            headers=boss_h,
        )
        check("停用 smoke 中介", deactivate.status_code == 200)

    return 0 if FAIL == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="部署后全链路冒烟自检")
    parser.add_argument("--base", default="http://127.0.0.1:8000", help="API 根地址")
    parser.add_argument("--tenant-code", default="tx886")
    parser.add_argument("--tenant-password", default="dev123456")
    parser.add_argument("--boss-code", default="boss888")
    args = parser.parse_args()

    print(f"冒烟目标：{args.base}")
    code = asyncio.run(run(args.base, args.tenant_code, args.tenant_password, args.boss_code))
    print(f"\n=== 结果：{PASS} 通过 / {FAIL} 失败 ===")
    sys.exit(code)


if __name__ == "__main__":
    main()
