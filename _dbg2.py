"""临时：复现冒烟脚本的审核 404。用完即删。"""
import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8")
prefix = "http://127.0.0.1:8000/api/v1"
stamp = str(int(time.time()))
boss = {"Authorization": "Bearer " + httpx.post(prefix + "/auth/owner-login", json={"access_code": "boss888"}).json()["token"]}

created = httpx.post(prefix + "/tenants/", json={"tenant_name": f"dbg-{stamp}", "contact_wechat": "d"}, headers=boss)
smoke_tenant = created.json()
invite = smoke_tenant["invite_code"]
pw = smoke_tenant.get("initial_password") or ""
print("tenant:", smoke_tenant["id"], invite, "pw_len:", len(pw))

login = httpx.post(prefix + "/auth/tenant-login", json={"invite_code": invite, "password": pw})
print("login:", login.status_code, "tid:", login.json().get("tenant", {}).get("id"))
smoke_h = {"Authorization": "Bearer " + login.json()["token"]}

reg = httpx.post(prefix + "/auth/teacher-phone-register", json={
    "phone": f"138{stamp[-8:]}", "invite_code": invite, "password": "smoke123",
    "name": "调试教员", "gender": "male", "wechat_id": "d", "school": "d",
})
print("register:", reg.status_code)
teacher_h = {"Authorization": "Bearer " + reg.json()["token"]}
print("register tenant via response:", reg.json().get("tenant", {}).get("id"))

resume = httpx.post(prefix + "/teacher/resumes/", json={
    "title": "t", "teaching_subjects": "数学", "teaching_grades": "初一-初三", "experience": "e",
}, headers=teacher_h)
resume_id = resume.json()["id"]

import datetime
expire = (datetime.datetime.utcnow() + datetime.timedelta(hours=48)).isoformat()
order = httpx.post(prefix + "/orders/batch-import", json={"items": [{
    "raw_id": f"DBG-{stamp}", "raw_text": "d", "grade_subject": "初三数学", "price_total": "200/次",
    "base_price": 200.0, "weekly_frequency": 2, "is_summer_vacation": False,
    "fuzzy_address": "d", "lng": 104.06, "lat": 30.57,
    "calculated_info_fee": 0, "deposit_amount": 0, "balance_amount": 0,
}]}, headers=smoke_h)
print("import:", order.status_code)
orders = httpx.get(prefix + "/orders/", params={"q": f"DBG-{stamp}"}, headers=smoke_h)
order_id = orders.json()["items"][0]["id"]
print("order:", order_id)

apply = httpx.post(prefix + "/applications/", params={"order_id": order_id, "resume_id": resume_id}, headers=teacher_h)
print("apply:", apply.status_code, apply.text[:260])
app_id = apply.json()["id"]
print("app tenant_id:", apply.json().get("tenant_id"))

sl = httpx.post(prefix + f"/applications/{app_id}/shortlist", headers=smoke_h)
print("shortlist:", sl.status_code, sl.text[:120])
