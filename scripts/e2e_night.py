"""
夜测：生产环境端到端交互测试（对 http://47.108.14.88:8080 实跑）。

覆盖：健康检查 / 老板与中介账号 / AI 批量解析与导入 / 订单增改归档重发 /
教员注册登录（含重复与无效邀请码边界）/ 橱窗脱敏 / 投递→候选→定金→尾款→
试课→地址解锁→成交 全链（含费率快照抗改价）/ 重复确认守卫 / 试课失败退费
（新公式 50%）/ 没收 / 教员取消退款 / 归档重发 / 批量状态 / 教员 transit 越权 /
财务台账与订单级过滤 / 导出 CSV 三件 / AI 找单（B/C 端）/ 教员 AI 问答 /
相似订单 / 订阅偏好回写 / 通知 / 跨中介隔离。

设计约束：顺序执行（2G 机器不做并发压测）、幂等可重跑（账号复用、订单
raw_id 带运行时间戳）、密钥不写入源码（OWNER_ACCESS_CODE 运行时从
.env.production 读取，测试密码由拼接构造）。
"""
from __future__ import annotations

import datetime
import io
import sys
import time

import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://47.108.14.88:8080"
API = f"{BASE}/api/v1"
INVITE = "nit2026"
TENANT_PASSWORD = "Nit" + "2026abc"
TEACHER_A_PHONE = "13857000001"
TEACHER_B_PHONE = "13857000002"
TEACHER_PASSWORD = "Nit" + "pass123"
RUN_TAG = datetime.datetime.now().strftime("%H%M%S")

OWNER_ACCESS_CODE = ""
for line in open(r"D:\My_Project\smart_tutor\.env.production", encoding="utf-8"):
    if line.startswith("OWNER_ACCESS_CODE="):
        OWNER_ACCESS_CODE = line.split("=", 1)[1].strip()
if not OWNER_ACCESS_CODE:
    raise SystemExit("OWNER_ACCESS_CODE 未从 .env.production 读到")

RESULTS: list[tuple[str, str, str]] = []


def record(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, "PASS" if ok else "FAIL", detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def warn(name: str, detail: str) -> None:
    RESULTS.append((name, "WARN", detail))
    print(f"[WARN] {name} — {detail}")


class Client:
    def __init__(self) -> None:
        self.http = httpx.Client(timeout=90)

    def req(self, method: str, path: str, token: str | None = None, **kwargs) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return self.http.request(method, f"{API}{path}", headers=headers, **kwargs)

    def get(self, path: str, token: str | None = None, **kw) -> httpx.Response:
        return self.req("GET", path, token, **kw)

    def post(self, path: str, token: str | None = None, **kw) -> httpx.Response:
        return self.req("POST", path, token, **kw)

    def put(self, path: str, token: str | None = None, **kw) -> httpx.Response:
        return self.req("PUT", path, token, **kw)

    def patch(self, path: str, token: str | None = None, **kw) -> httpx.Response:
        return self.req("PATCH", path, token, **kw)

    def delete(self, path: str, token: str | None = None, **kw) -> httpx.Response:
        return self.req("DELETE", path, token, **kw)


c = Client()
boss_token: str | None = None
tenant_token: str | None = None
teacher_a: str | None = None
teacher_b: str | None = None


def fee_for(base: float, weekly: int) -> dict:
    rate = 1.5 if weekly <= 1 else (1.0 if weekly == 2 else 0.8)
    total = round(base * weekly * rate, 2)
    return {"total": total, "deposit": 100.0, "balance": round(total - 100.0, 2)}


# ── 1. 健康检查 ──
def t_health() -> None:
    r = c.http.get(f"{BASE}/health")
    body = r.json()
    record("健康检查 /health", r.status_code == 200 and body.get("database") and body.get("redis"), str(body))


# ── 2. 老板登录 ──
def t_owner() -> None:
    global boss_token
    r = c.post("/auth/owner-login", json={"access_code": "wrong-code"})
    record("老板登录·错误访问码被拒", r.status_code == 403, f"HTTP {r.status_code}")
    r = c.post("/auth/owner-login", json={"access_code": OWNER_ACCESS_CODE})
    ok = r.status_code == 200 and r.json().get("role") == "super_admin"
    boss_token = r.json().get("token") if ok else None
    record("老板登录·正确访问码", ok, f"HTTP {r.status_code}")


# ── 3. 测试中介（存在则复用） ──
def t_tenant_setup() -> None:
    global tenant_token
    r = c.post("/tenants/", token=boss_token, json={
        "tenant_name": "夜测中介", "contact_wechat": "wx_nit_test",
        "invite_code": INVITE, "password": TENANT_PASSWORD,
    })
    if r.status_code == 409:
        record("创建测试中介", True, "已存在（复用）")
    else:
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        # 后端契约返回 200（tenants.py create_tenant 未声明 status_code=201；F01：此前误断言 201）
        record("创建测试中介", r.status_code == 200 and body.get("invite_code") == INVITE,
               f"HTTP {r.status_code} {str(body)[:120]}")

    r = c.post("/auth/tenant-login", json={"invite_code": INVITE, "password": "Wrong" + "123"})
    record("中介登录·错误密码被拒", r.status_code in (400, 401, 403), f"HTTP {r.status_code}")
    r = c.post("/auth/tenant-login", json={"invite_code": INVITE, "password": TENANT_PASSWORD})
    ok = r.status_code == 200
    tenant_token = r.json().get("token") if ok else None
    record("中介登录", ok, f"HTTP {r.status_code}")


# ── 4. AI 批量解析 + 导入三单 ──
def t_parse_and_import() -> list[int]:
    text = (
        "【NIT-001】五年级，女 数学\n"
        "课酬：120/次\n"
        "频次：每周5次\n"
        "地址：成都市武侯区桐梓林北路2号\n"
        "家长电话：13800001111\n"
        "要求：女，有耐心\n\n"
        "【NIT-002】初三 数学\n"
        "课酬：200/次 每周2次\n"
        "地址：成都市锦江区东大街下东大街段216号\n\n"
        "【NIT-003】高一 英语 150/次 一周一次\n"
        "地址：成都市青羊区光华村街55号\n"
    )
    order_ids: list[int] = []
    parsed_items: list[dict] | None = None
    # 契约字段为 raw_text（BatchParseRequest，schemas.py:315）；城市提示由服务端从租户 city 取，
    # 请求体不收 city_hint（F02：此前传 text 导致契约 422 降级手工构造项）
    r = c.post("/orders/batch-parse", token=tenant_token, json={"raw_text": text})
    if r.status_code == 200:
        items = r.json().get("items", [])
        record("AI 批量解析", len(items) >= 3, f"解析出 {len(items)} 单")
        parsed_items = items
    else:
        warn("AI 批量解析", f"HTTP {r.status_code} {r.text[:150]}（改用手工构造项继续导入测试）")

    if not parsed_items:
        f1, f2, f3 = fee_for(120, 5), fee_for(200, 2), fee_for(150, 1)
        parsed_items = [
            {"raw_id": "NIT-001", "raw_text": "五年级数学120/次每周5次", "grade_subject": "五年级 数学",
             "price_total": "120/次", "base_price": 120, "weekly_frequency": 5,
             "fuzzy_address": "成都市武侯区桐梓林北路", "exact_address": "桐梓林北路2号",
             "parent_phone": "13800001111", "lng": 104.0715, "lat": 30.6305,
             "calculated_info_fee": f1["total"], "deposit_amount": f1["deposit"], "balance_amount": f1["balance"]},
            {"raw_id": "NIT-002", "raw_text": "初三数学200/次每周2次", "grade_subject": "初三 数学",
             "price_total": "200/次", "base_price": 200, "weekly_frequency": 2,
             "fuzzy_address": "成都市锦江区东大街", "lng": 104.0817, "lat": 30.6570,
             "calculated_info_fee": f2["total"], "deposit_amount": f2["deposit"], "balance_amount": f2["balance"]},
            {"raw_id": "NIT-003", "raw_text": "高一英语150/次一周一次", "grade_subject": "高一 英语",
             "price_total": "150/次", "base_price": 150, "weekly_frequency": 1,
             "fuzzy_address": "成都市青羊区光华村街", "lng": 104.0300, "lat": 30.6630,
             "calculated_info_fee": f3["total"], "deposit_amount": f3["deposit"], "balance_amount": f3["balance"]},
        ]

    for item in parsed_items:
        item.setdefault("raw_id", f"NIT-{RUN_TAG}-X")
        item["raw_id"] = str(item["raw_id"]).replace("NIT-", f"NIT{RUN_TAG}-") if str(item["raw_id"]).startswith("NIT-") else item["raw_id"]
        if not str(item.get("raw_id", "")).startswith("NIT"):
            item["raw_id"] = f"NIT{RUN_TAG}-{item['raw_id']}"
        item.setdefault("lng", 104.065)
        item.setdefault("lat", 30.659)
        item.setdefault("calculated_info_fee", 0)
        item.setdefault("deposit_amount", 0)
        item.setdefault("balance_amount", 0)

    r = c.post("/orders/batch-import", token=tenant_token, json={"items": parsed_items})
    ok = r.status_code == 200 and r.json().get("imported", 0) >= 3
    record("批量导入三单", ok, f"HTTP {r.status_code} imported={r.json().get('imported') if r.headers.get('content-type','').startswith('application/json') else r.text[:120]}")

    r = c.get("/orders/", token=tenant_token, params={"page_size": 50, "q": f"NIT{RUN_TAG}"})
    items = r.json().get("items", []) if r.status_code == 200 else []
    by_raw = {o["raw_id"]: o for o in items}
    for raw_id in (f"NIT{RUN_TAG}-001", f"NIT{RUN_TAG}-002", f"NIT{RUN_TAG}-003"):
        if raw_id in by_raw:
            order_ids.append(by_raw[raw_id]["id"])
    record("订单列表可检索三单", len(order_ids) == 3, f"ids={order_ids}")

    if order_ids:
        r = c.get(f"/orders/{order_ids[0]}", token=tenant_token)
        d = r.json()
        f1 = fee_for(120, 5)
        fee_ok = abs(d["calculated_info_fee"] - f1["total"]) < 0.01 and abs(d["balance_amount"] - f1["balance"]) < 0.01
        record("新公式落库校验（120×5→480=100+380）", fee_ok,
               f"fee={d['calculated_info_fee']} deposit={d['deposit_amount']} balance={d['balance_amount']}")
        r = c.get(f"/orders/{order_ids[1]}", token=tenant_token)
        d2 = r.json()
        f2 = fee_for(200, 2)
        record("新公式校验（200×2→400）", abs(d2["calculated_info_fee"] - f2["total"]) < 0.01,
               f"fee={d2['calculated_info_fee']}")
    return order_ids


# ── 5. 订单编辑 / 归档 / 重发 / 批量 / 越权 ──
def t_order_admin(order_ids: list[int]) -> None:
    if not order_ids:
        warn("订单管理类测试", "无可用的订单 id，跳过")
        return
    oid3 = order_ids[2]
    r = c.patch(f"/orders/{oid3}", token=tenant_token, json={"base_price": 160})
    f3 = fee_for(160, 1)
    record("编辑订单改价重算（150→160×1.5=240）",
           r.status_code == 200 and abs(r.json()["calculated_info_fee"] - f3["total"]) < 0.01,
           f"HTTP {r.status_code} fee={r.json().get('calculated_info_fee') if r.status_code == 200 else r.text[:100]}")
    r = c.patch(f"/orders/{oid3}", token=tenant_token, json={"base_price": 150})
    record("改回 150", r.status_code == 200)

    r = c.post(f"/orders/{oid3}/archive", token=tenant_token)
    record("归档订单", r.status_code == 200 and r.json()["status"] == "archived", f"HTTP {r.status_code}")
    r = c.post(f"/orders/{oid3}/republish", token=tenant_token)
    record("重新发布", r.status_code == 200 and r.json()["status"] == "recruiting", f"HTTP {r.status_code}")

    r = c.post("/orders/transit", token=teacher_a,
               json={"target_status": "archived"}) if False else c.post(
        f"/orders/{order_ids[0]}/transit", token=teacher_a, json={"target_status": "archived"})
    record("教员调 transit 被拒", r.status_code in (401, 403, 404), f"HTTP {r.status_code}")

    r = c.post("/orders/batch-status", token=tenant_token,
               json={"ids": [oid3], "target_status": "archived"})
    ok1 = r.status_code == 200
    r = c.post("/orders/batch-status", token=tenant_token,
               json={"ids": [oid3], "target_status": "recruiting"})
    record("批量归档+批量重开", ok1 and r.status_code == 200, f"HTTP {r.status_code}")


# ── 6. 教员注册 / 登录 / 边界 ──
def t_teacher_auth() -> None:
    global teacher_a, teacher_b
    reg = {"invite_code": INVITE, "name": "夜测教员A", "gender": "male",
           "phone": TEACHER_A_PHONE, "password": TEACHER_PASSWORD,
           "wechat_id": "wx_nit_a", "school": "夜测大学"}
    r = c.post("/auth/teacher-phone-register", json=reg)
    ok1 = r.status_code == 200
    if ok1:
        teacher_a = r.json()["token"]
    else:
        r2 = c.post("/auth/teacher-phone-login",
                    json={"phone": TEACHER_A_PHONE, "password": TEACHER_PASSWORD, "invite_code": INVITE})
        teacher_a = r2.json().get("token") if r2.status_code == 200 else None
        ok1 = teacher_a is not None
    record("教员A注册（或复用）", ok1, f"HTTP {r.status_code}")

    r = c.post("/auth/teacher-phone-register", json=reg)
    record("重复注册被拒（409）", r.status_code == 409, f"HTTP {r.status_code} {r.json().get('detail', '')[:60]}")

    reg_b = dict(reg, phone=TEACHER_B_PHONE, name="夜测教员B", wechat_id="wx_nit_b")
    r = c.post("/auth/teacher-phone-register", json=reg_b)
    if r.status_code == 200:
        teacher_b = r.json()["token"]
    else:
        r2 = c.post("/auth/teacher-phone-login",
                    json={"phone": TEACHER_B_PHONE, "password": TEACHER_PASSWORD, "invite_code": INVITE})
        teacher_b = r2.json().get("token") if r2.status_code == 200 else None
    record("教员B注册（或复用）", teacher_b is not None, f"HTTP {r.status_code}")

    r = c.post("/auth/teacher-phone-register", json=dict(reg, phone="13857000003", invite_code="no_such"))
    record("无效邀请码注册被拒（404）", r.status_code == 404, f"HTTP {r.status_code}")


# ── 7. 橱窗脱敏 ──
def t_board(order_ids: list[int]) -> None:
    r = c.http.get(f"{API}/public/agent/{INVITE}/board")
    items = r.json().get("items", []) if r.status_code == 200 else []
    ours = [o for o in items if str(o.get("raw_id", "")).startswith(f"NIT{RUN_TAG}")]
    leak = [o for o in ours if o.get("parent_phone") or o.get("exact_address")]
    record("公共橱窗返回且未登录可看", r.status_code == 200 and len(ours) >= 3, f"夜测单可见 {len(ours)}")
    record("橱窗脱敏（无家长电话/真实门牌）", not leak, f"泄露字段={leak[:1]}")


# ── 8. 资金全链：成交 + 快照抗改价 ──
def t_full_funnel(order_ids: list[int]) -> None:
    if not (order_ids and teacher_a):
        warn("成交全链", "前置缺失，跳过")
        return
    oid = order_ids[0]
    r = c.post("/applications/", token=teacher_a, json={"order_id": oid})
    app_id = r.json().get("id") if r.status_code == 200 else None
    record("教员A投递", r.status_code == 200 and app_id, f"HTTP {r.status_code}")

    r = c.get(f"/applications/order/{oid}", token=tenant_token)
    apps = r.json() if r.status_code == 200 else []
    record("中介查本单投递列表", r.status_code == 200 and len(apps) >= 1, f"{len(apps)} 条")

    r = c.post(f"/applications/{app_id}/start-trial", token=tenant_token)
    record("未付定金不可开试课（400）", r.status_code == 400, f"HTTP {r.status_code}")

    r = c.post(f"/applications/{app_id}/shortlist", token=tenant_token)
    record("加入候选", r.status_code == 200, f"HTTP {r.status_code}")
    r = c.post(f"/applications/{app_id}/confirm-deposit", token=tenant_token)
    record("确认定金", r.status_code == 200, f"HTTP {r.status_code}")
    r = c.post(f"/applications/{app_id}/confirm-deposit", token=tenant_token)
    record("重复确认定金被拒（400）", r.status_code == 400, f"HTTP {r.status_code}")

    # 快照抗改价：定金后把课酬改到 130，尾款必须仍按快照 380 收
    c.patch(f"/orders/{oid}", token=tenant_token, json={"base_price": 130})
    r = c.post(f"/applications/{app_id}/confirm-balance", token=tenant_token)
    record("确认尾款（按快照 380）", r.status_code == 200, f"HTTP {r.status_code}")
    r = c.post(f"/applications/{app_id}/confirm-balance", token=tenant_token)
    record("重复确认尾款被拒（400）", r.status_code == 400, f"HTTP {r.status_code}")

    balances = r = c.get("/financial-records/", token=tenant_token, params={"order_id": oid, "type": "balance_in"})
    bal_amounts = [rec["amount"] for rec in balances.json().get("records", [])] if balances.status_code == 200 else []
    record("台账尾款按快照 380（改价不追溯）", any(abs(a - 380.0) < 0.01 for a in bal_amounts), f"{bal_amounts}")

    r = c.post(f"/applications/{app_id}/start-trial", token=tenant_token)
    record("开试课", r.status_code == 200, f"HTTP {r.status_code}")
    r = c.get(f"/orders/{oid}/address-unlock", token=teacher_a)
    unlock_ok = r.status_code == 200 and r.json().get("parent_phone") == "13800001111"
    record("试课中解锁家长联系方式", unlock_ok, f"HTTP {r.status_code} {r.text[:80]}")

    r = c.post(f"/applications/{app_id}/complete", token=tenant_token)
    record("确认成交", r.status_code == 200, f"HTTP {r.status_code}")
    r = c.get(f"/orders/{oid}", token=tenant_token)
    record("订单状态=已完成", r.status_code == 200 and r.json()["status"] == "completed")

    r = c.get("/financial-records/", token=tenant_token, params={"order_id": oid})
    s = r.json() if r.status_code == 200 else {}
    record("订单级台账汇总（100+380）",
           abs(s.get("deposit_in", 0) - 100.0) < 0.01 and abs(s.get("balance_in", 0) - 380.0) < 0.01
           and abs(s.get("net_amount", 0) - 480.0) < 0.01,
           f"deposit_in={s.get('deposit_in')} balance_in={s.get('balance_in')} net={s.get('net_amount')}")


# ── 9. 试课失败退费（新公式 50%） ──
def t_trial_failed(order_ids: list[int]) -> None:
    if not (len(order_ids) > 1 and teacher_b):
        warn("试课失败退费", "前置缺失，跳过")
        return
    oid = order_ids[1]
    r = c.post("/applications/", token=teacher_b, json={"order_id": oid})
    app_id = r.json().get("id")
    c.post(f"/applications/{app_id}/shortlist", token=tenant_token)
    c.post(f"/applications/{app_id}/confirm-deposit", token=tenant_token)
    c.post(f"/applications/{app_id}/confirm-balance", token=tenant_token)
    c.post(f"/applications/{app_id}/start-trial", token=tenant_token)

    r = c.post(f"/applications/{app_id}/trial-failed", token=tenant_token,
               json={"trial_paid_by_parent": 100})
    record("试课失败→已退款", r.status_code == 200 and r.json()["status"] == "refunded", f"HTTP {r.status_code}")
    r = c.get("/financial-records/", token=tenant_token, params={"order_id": oid, "type": "refund_out"})
    refunds = [rec["amount"] for rec in r.json().get("records", [])] if r.status_code == 200 else []
    record("退费=信息费400−试课酬100×50%=350", any(abs(a - 350.0) < 0.01 for a in refunds), f"{refunds}")
    r = c.get(f"/orders/{oid}", token=tenant_token)
    record("失败后订单重回招聘中", r.status_code == 200 and r.json()["status"] == "recruiting")


# ── 10. 没收 ──
def t_forfeit(order_ids: list[int]) -> None:
    if not (len(order_ids) > 1 and teacher_b):
        warn("没收流程", "前置缺失，跳过")
        return
    oid = order_ids[1]
    r = c.post("/applications/", token=teacher_b, json={"order_id": oid})
    app_id = r.json().get("id")
    c.post(f"/applications/{app_id}/shortlist", token=tenant_token)
    c.post(f"/applications/{app_id}/confirm-deposit", token=tenant_token)
    r = c.post(f"/applications/{app_id}/forfeit", token=tenant_token)
    record("没收→forfeited 终态", r.status_code == 200 and r.json()["status"] == "forfeited", f"HTTP {r.status_code}")
    r = c.get("/financial-records/", token=tenant_token, params={"order_id": oid, "type": "forfeit"})
    forfeits = [rec["amount"] for rec in r.json().get("records", [])] if r.status_code == 200 else []
    record("没收流水=定金 100", any(abs(a - 100.0) < 0.01 for a in forfeits), f"{forfeits}")


# ── 11. 教员取消（已付定金）退款 ──
def t_teacher_cancel(order_ids: list[int]) -> None:
    if not (len(order_ids) > 2 and teacher_a):
        warn("教员取消退款", "前置缺失，跳过")
        return
    oid = order_ids[2]
    r = c.post("/applications/", token=teacher_a, json={"order_id": oid})
    app_id = r.json().get("id")
    c.post(f"/applications/{app_id}/shortlist", token=tenant_token)
    c.post(f"/applications/{app_id}/confirm-deposit", token=tenant_token)
    r = c.post(f"/applications/{app_id}/cancel", token=teacher_a)
    record("教员取消→已退款", r.status_code == 200 and r.json()["status"] == "refunded", f"HTTP {r.status_code}")
    r = c.get("/financial-records/", token=tenant_token, params={"order_id": oid, "type": "refund_out"})
    refunds = [rec["amount"] for rec in r.json().get("records", [])] if r.status_code == 200 else []
    record("取消退款=定金 100", any(abs(a - 100.0) < 0.01 for a in refunds), f"{refunds}")


# ── 12. AI 找单（B/C 端）+ 教员 AI 问答 + 相似订单 ──
def t_ai(order_ids: list[int]) -> None:
    r = c.post("/ai/find-orders", token=tenant_token, json={"query": f"编号 {RUN_TAG} 的数学订单"})
    if r.status_code == 200:
        items = r.json().get("items", [])
        hit = any(str(o.get("raw_id", "")).startswith(f"NIT{RUN_TAG}") for o in items)
        record("B 端 AI 找单", True, f"matched={r.json().get('total_matched')} 含夜测单={hit}")
        if not hit:
            warn("B 端 AI 找单命中夜测单", "返回 200 但结果未包含夜测单（LLM 解析波动，人工复核）")
    else:
        warn("B 端 AI 找单", f"HTTP {r.status_code} {r.text[:120]}")

    r = c.post("/ai/teacher/find-orders", token=teacher_a, json={"query": "数学 单次课酬不低于100"})
    record("C 端 AI 找单", r.status_code == 200, f"HTTP {r.status_code} matched={r.json().get('total_matched') if r.status_code == 200 else r.text[:100]}")

    # 教员 AI 问答：先给夜测中介种一篇规则文档
    doc = ("夜测中介信息费规则：信息费=周课时费×频次倍率（1次1.5倍，2次1.0倍，3次及以上0.8倍），"
           "定金固定100元。举例：单次120元每周5次，信息费为600×0.8=480元。")
    r = c.post("/ai/knowledge/documents", token=tenant_token,
               json={"title": f"夜测规则{RUN_TAG}", "content": doc, "source_type": "paste"})
    record("中介上传知识文档", r.status_code == 201 and r.json().get("status") == "ready",
           f"HTTP {r.status_code} {r.text[:100]}")

    r = c.post("/ai/teacher/assistant", token=teacher_a,
               json={"question": "单次120元每周5次的单子信息费多少？", "invite_code": INVITE})
    if r.status_code == 200:
        body = r.json()
        hit = "480" in body.get("answer", "")
        record("教员 AI 问答（引用当前中介知识库）", body.get("citations") and len(body["answer"]) > 10,
               f"citations={len(body.get('citations', []))} 含480={hit}")
        if not hit:
            warn("教员 AI 问答数字", "回答未含 480（LLM 表述波动，人工复核回答原文）")
    else:
        warn("教员 AI 问答", f"HTTP {r.status_code} {r.text[:120]}")

    if order_ids:
        r = c.get(f"/ai/orders/{order_ids[0]}/similar", token=tenant_token)
        record("相似订单（语义检索）", r.status_code == 200 and isinstance(r.json().get("items"), list),
               f"HTTP {r.status_code} items={len(r.json().get('items', [])) if r.status_code == 200 else r.text[:80]}")


# ── 13. 订阅 / 通知 / 导出 / 隔离 ──
def t_misc(order_ids: list[int]) -> None:
    r = c.put("/subscriptions/mine", token=teacher_a,
              json={"enabled": True, "subjects": ["数学"], "grades": ["初中"], "min_base_price": 100})
    ok1 = r.status_code == 200 and r.json().get("subjects") == ["数学"]
    r = c.get("/subscriptions/mine", token=teacher_a)
    roundtrip = r.status_code == 200 and r.json().get("min_base_price") == 100
    record("订阅偏好保存与回读", ok1 and roundtrip, f"save={r.status_code}")

    # 契约路径为 /notifications/mine?limit=N（notifications.py:24，仅支持 limit，无分页参数；
    # F12：此前调 /notifications/ 根路径必 404）
    r = c.get("/notifications/mine", token=teacher_a, params={"limit": 50})
    notif_body = r.json() if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/json") else {}
    record("教员通知列表",
           r.status_code == 200 and "unread_count" in notif_body and isinstance(notif_body.get("items"), list),
           f"HTTP {r.status_code} unread={notif_body.get('unread_count')}")
    r = c.get("/notifications/tenant-unread-count", token=tenant_token)
    record("中介未读数", r.status_code == 200, f"HTTP {r.status_code}")

    r = c.get("/financial-records/export", token=tenant_token)
    record("财务流水导出 CSV", r.status_code == 200 and "text/csv" in r.headers.get("content-type", ""),
           f"HTTP {r.status_code}")
    r = c.get("/orders/export", token=tenant_token)
    record("订单导出 CSV", r.status_code == 200 and "text/csv" in r.headers.get("content-type", ""),
           f"HTTP {r.status_code}")
    r = c.get("/tenants/my-teachers/export", token=tenant_token)
    record("教员名单导出 CSV", r.status_code == 200 and "text/csv" in r.headers.get("content-type", ""),
           f"HTTP {r.status_code}")

    # 跨中介隔离：另一个真实测试中介不得看到夜测订单。
    # F13：不再依赖外部种子账号（此前硬编码一个生产不存在的邀请码+密码，登录失败即整段跳过），
    # 改用 owner token 自建对照中介——邀请码带运行标签保证幂等（同秒重跑 409 复用）。
    other_invite = f"nitx{RUN_TAG}"
    r = c.post("/tenants/", token=boss_token, json={
        "tenant_name": "夜测对照中介", "contact_wechat": "wx_nit_other",
        "invite_code": other_invite, "password": TENANT_PASSWORD,
    })
    if r.status_code not in (200, 409):
        warn("跨中介隔离", f"对照中介创建失败：HTTP {r.status_code} {r.text[:120]}")
        return
    r = c.post("/auth/tenant-login", json={"invite_code": other_invite, "password": TENANT_PASSWORD})
    if r.status_code == 200:
        other = r.json()["token"]
        if order_ids:
            r = c.get(f"/orders/{order_ids[0]}", token=other)
            record("跨中介隔离（他中介看单 404）", r.status_code == 404, f"HTTP {r.status_code}")
            r = c.get(f"/applications/order/{order_ids[0]}", token=other)
            record("跨中介隔离（投递列表 404）", r.status_code == 404, f"HTTP {r.status_code}")
    else:
        warn("跨中介隔离", f"对照中介 {other_invite} 登录失败：HTTP {r.status_code}")


def main() -> None:
    started = time.monotonic()
    t_health()
    t_owner()
    t_tenant_setup()
    order_ids = t_parse_and_import()
    t_order_admin(order_ids)
    t_teacher_auth()
    t_board(order_ids)
    t_full_funnel(order_ids)
    t_trial_failed(order_ids)
    t_forfeit(order_ids)
    t_teacher_cancel(order_ids)
    t_ai(order_ids)
    t_misc(order_ids)

    elapsed = int(time.monotonic() - started)
    passed = sum(1 for _, s, _ in RESULTS if s == "PASS")
    failed = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    warns = sum(1 for _, s, _ in RESULTS if s == "WARN")
    print(f"\n===== 夜测汇总：{passed} PASS / {failed} FAIL / {warns} WARN，用时 {elapsed}s =====")

    lines = [
        "# 夜测报告（2026-10-27 晚，生产环境 47.108.14.88:8080 实跑）",
        "",
        f"汇总：**{passed} PASS / {failed} FAIL / {warns} WARN**，用时 {elapsed}s。",
        "测试数据：中介「夜测中介」(nit2026)、教员 13857000001/2，订单 NIT{时间戳}-001~003。",
        "",
        "| # | 场景 | 结果 | 详情 |",
        "|---|---|---|---|",
    ]
    for i, (name, status, detail) in enumerate(RESULTS, 1):
        lines.append(f"| {i} | {name} | {status} | {detail[:160]} |")
    open(r"D:\My_Project\smart_tutor\.scratch\night-e2e\REPORT.md", "w", encoding="utf-8").write("\n".join(lines))
    print("报告已写入 .scratch/night-e2e/REPORT.md")


if __name__ == "__main__":
    main()
