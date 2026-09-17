"""
地理辅助接口回归（教员常驻地定位）：

- /geo/regeo：坐标 → "城市·区"文本；直辖市 city 字段为空数组时回退 province；
- /geo/nearby-pois：POI 解析、坏坐标行跳过；
- 坐标范围校验与角色限制。

高德 REST 调用统一 mock，不打真实 API。

运行方式：
    pytest tests/test_geo_endpoints.py
"""
import httpx
from conftest import BASE, auth_header, make_teacher, teacher_token, tenant_token


def _patch_amap(monkeypatch, payload: dict) -> dict:
    """把 _amap_get 换成直接返回固定载荷，记录请求参数。"""
    from routers.v1 import geo as geo_router

    captured = {}

    async def fake_get(path: str, params: dict) -> dict:
        captured["path"] = path
        captured["params"] = {k: v for k, v in params.items() if k != "key"}
        return payload

    monkeypatch.setattr(geo_router, "_amap_get", fake_get)
    return captured


async def test_regeo_formats_city_district(client, db, monkeypatch):
    teacher = await make_teacher(db, "geo_teacher_1")
    await db.commit()
    captured = _patch_amap(monkeypatch, {
        "regeocode": {
            "addressComponent": {"city": "成都市", "province": "四川省", "district": "青羊区"},
        }
    })

    r = await client.get(
        f"{BASE}/api/v1/geo/regeo",
        params={"lng": 104.065, "lat": 30.659},
        headers=auth_header(teacher_token(teacher.id)),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"area": "成都·青羊区"}, "城市应去掉'市'后缀并拼区名"
    assert captured["params"]["location"] == "104.065,30.659"


async def test_regeo_municipality_falls_back_to_province(client, db, monkeypatch):
    """直辖市（如北京）高德返回 city=[]，应回退 province 且不去掉整个名字。"""
    teacher = await make_teacher(db, "geo_teacher_2")
    await db.commit()
    _patch_amap(monkeypatch, {
        "regeocode": {
            "addressComponent": {"city": [], "province": "北京市", "district": "海淀区"},
        }
    })

    r = await client.get(
        f"{BASE}/api/v1/geo/regeo",
        params={"lng": 116.3, "lat": 39.9},
        headers=auth_header(teacher_token(teacher.id)),
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"area": "北京·海淀区"}


async def test_nearby_pois_parses_and_skips_bad_rows(client, db, monkeypatch):
    teacher = await make_teacher(db, "geo_teacher_3")
    await db.commit()
    captured = _patch_amap(monkeypatch, {
        "pois": [
            {"name": "xx小区", "address": "武侯区xx路1号", "location": "104.06,30.65",
             "pname": "四川省", "cityname": "成都市", "adname": "武侯区"},
            {"name": "坏坐标行", "address": "", "location": "not-a-coord"},
            {"name": "", "address": "无名", "location": "104.06,30.65"},
            {"name": "无坐标行", "address": "", "location": ""},
        ]
    })

    r = await client.get(
        f"{BASE}/api/v1/geo/nearby-pois",
        params={"lng": 104.065, "lat": 30.659},
        headers=auth_header(teacher_token(teacher.id)),
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1, "坏坐标/无名行应跳过"
    assert items[0]["name"] == "xx小区"
    assert items[0]["lng"] == 104.06 and items[0]["lat"] == 30.65
    assert items[0]["area"] == "成都·武侯区"


async def test_search_pois_composes_area_and_limits_city(client, db, monkeypatch):
    """关键字搜索：area 由省市区拼出（直辖市 cityname 去后缀）；city 参数透传高德。"""
    teacher = await make_teacher(db, "geo_teacher_5")
    await db.commit()
    captured = _patch_amap(monkeypatch, {
        "pois": [
            {"name": "西南石油大学(成都校区)", "address": "新都大道8号", "location": "104.16,30.82",
             "pname": "四川省", "cityname": "成都市", "adname": "新都区"},
        ]
    })

    r = await client.get(
        f"{BASE}/api/v1/geo/search-pois",
        params={"keywords": "西南石油大学"},
        headers=auth_header(teacher_token(teacher.id)),
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["area"] == "成都·新都区"
    assert captured["params"]["keywords"] == "西南石油大学"
    assert captured["params"]["city"] == "成都"
    assert captured["params"]["citylimit"] == "true"

    # 空白关键词拒绝
    r = await client.get(
        f"{BASE}/api/v1/geo/search-pois",
        params={"keywords": "   "},
        headers=auth_header(teacher_token(teacher.id)),
    )
    assert r.status_code == 422


async def test_geo_rejects_out_of_range_coords(client, db):
    teacher = await make_teacher(db, "geo_teacher_4")
    await db.commit()

    r = await client.get(
        f"{BASE}/api/v1/geo/regeo",
        params={"lng": 200.0, "lat": 30.0},
        headers=auth_header(teacher_token(teacher.id)),
    )
    assert r.status_code == 422, "超出中国大陆范围的坐标应拒绝"

    r = await client.get(
        f"{BASE}/api/v1/geo/nearby-pois",
        params={"lng": 104.0, "lat": 30.0, "radius": 99999},
        headers=auth_header(teacher_token(teacher.id)),
    )
    assert r.status_code == 422, "半径超上限应拒绝"


async def test_geo_requires_teacher_role(client, db):
    r = await client.get(f"{BASE}/api/v1/geo/regeo", params={"lng": 104.0, "lat": 30.0})
    assert r.status_code in (401, 403), "未登录不可访问"

    r = await client.get(
        f"{BASE}/api/v1/geo/regeo",
        params={"lng": 104.0, "lat": 30.0},
        headers=auth_header(tenant_token(1)),
    )
    assert r.status_code == 403, "仅教员角色可访问"
