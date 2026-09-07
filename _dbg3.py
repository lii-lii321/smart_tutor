"""临时：深挖 shortlist 404。用完即删。"""
import sys
import time

import httpx

sys.stdout.reconfigure(encoding="utf-8")
prefix = "http://127.0.0.1:8000/api/v1"
stamp = str(int(time.time()))
boss = {"Authorization": "Bearer " + httpx.post(prefix + "/auth/owner-login", json={"access_code": "boss888"}).json()["token"]}

created = httpx.post(prefix + "/tenants/", json={"tenant_name": f"dbg2-{stamp}", "contact_wechat": "d"}, headers=boss)
smoke_tenant = created.json()
invite = smoke_tenant["invite_code"]
pw = smoke_tenant.get("initial_password") or ""

login = httpx.post(prefix + "/auth/tenant-login", json={"invite_code": invite, "password": pw})
smoke_h = {"Authorization": "Bearer " + login.json()["token"]}
me = httpx.get(prefix + "/auth/me/profile", headers=smoke_h).json()
print("me:", me)

reg = httpx.post(prefix + "/auth/teacher-phone-register", json={
    "phone": f"137{stamp[-8:]}", "invite_code": invite, "password": "smoke123",
    "name": "调试2", "gender": "male", "wechat_id": "d", "school": "d",
})
teacher_h = {"Authorization": "Bearer " + reg.json()["token"]}
resume = httpx.post(prefix + "/teacher/resumes/", json={
    "title": "t", "teaching_subjects": "数学", "teaching_grades": "初一-初三", "experience": "e",
}, headers=teacher_h)

import datetime
expire = (datetime.datetime.utcnow() + datetime.timedelta(hours=48)).isoformat()
order = httpx.post(prefix + "/orders/batch-import", json={"items": [{
    "raw_id": f"DBG3-{stamp}", "raw_text": "d", "grade_subject": "初三数学", "price_total": "200/次",
    "base_price": 200.0, "weekly_frequency": 2, "is_summer_vacation": False,
    "fuzzy_address": "d", "lng": 104.06, "lat": 30.57,
    "calculated_info_fee": 0, "deposit_amount": 0, "balance_amount": 0,
}]}, headers=smoke_h)
orders = httpx.get(prefix + "/orders/", params={"q": f"DBG3-{stamp}"}, headers=smoke_h)
order_id = orders.json()["items"][0]["id"]
print("order:", order_id)

apply = httpx.post(prefix + "/applications/", params={"order_id": order_id, "resume_id": resume.json()["id"]}, headers=teacher_h)
app_id = apply.json()["id"]
print("app:", app_id, "tenant:", apply.json().get("tenant_id"))

listing = httpx.get(prefix + f"/applications/order/{order_id}", headers=smoke_h)
print("list apps:", listing.status_code, "count:", len(listing.json()) if listing.status_code == 200 else listing.text[:100])

sl = httpx.post(prefix + f"/applications/{app_id}/shortlist", headers=smoke_h)
print("shortlist:", sl.status_code, sl.text[:150])

# 用教员 token 试（应 404/403，对照）
sl2 = httpx.post(prefix + f"/applications/{app_id}/shortlist", headers=teacher_h)
print("shortlist as teacher:", sl2.status_code)
