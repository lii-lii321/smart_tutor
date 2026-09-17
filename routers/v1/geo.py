"""
地理辅助接口：教员常驻地的逆地理编码与附近可选地点。

走高德 REST（Web服务 Key），不经浏览器 JSAPI——JSAPI 的服务调用需要单独的
Web端 Key + 安全密钥，而 REST 用现有 AMAP_API_KEY 即可用（实测 10000/OK）。
"""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from config import settings
from middleware.auth import TokenPayload, require_role

router = APIRouter(prefix="/api/v1/geo", tags=["地理辅助"])


def _validate_coords(lng: float, lat: float) -> None:
    # 中国大陆经纬度粗校验，防把接口当任意坐标代理用
    if not (73 < lng < 136 and 3 < lat < 54):
        raise HTTPException(status_code=422, detail="坐标超出支持范围")


async def _amap_get(path: str, params: dict) -> dict:
    if not settings.AMAP_API_KEY:
        raise HTTPException(status_code=503, detail="地图服务未配置")
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"https://restapi.amap.com{path}",
                params={**params, "key": settings.AMAP_API_KEY},
            )
            resp.raise_for_status()
            data = resp.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="地图服务暂不可用") from exc
    if data.get("status") != "1":
        raise HTTPException(status_code=502, detail="地图服务暂不可用")
    return data


def _city_text(comp: dict) -> str:
    """直辖市/直辖市外的 city 字段可能是字符串、空串或空数组，统一回退 province。"""
    city = comp.get("city")
    if not isinstance(city, str) or not city:
        city = comp.get("province") or ""
    return str(city).removesuffix("市")


@router.get("/regeo")
async def reverse_geocode(
    lng: float = Query(...),
    lat: float = Query(...),
    _payload: TokenPayload = Depends(require_role("teacher")),
):
    """坐标 → "城市·区"粒度文本（常驻地自动回填用，不暴露精确住址）。"""
    _validate_coords(lng, lat)
    data = await _amap_get("/v3/geocode/regeo", {"location": f"{lng},{lat}"})
    comp = (data.get("regeocode") or {}).get("addressComponent") or {}
    city = _city_text(comp)
    district = comp.get("district") if isinstance(comp.get("district"), str) else ""
    return {"area": f"{city}·{district}" if district else city}


def _poi_area(poi: dict) -> str:
    """POI 的省市区 → "城市·区"文本（城市去"市"后缀，直辖市回退省名）。"""
    city = poi.get("cityname")
    if not isinstance(city, str) or not city:
        city = poi.get("pname")
    if not isinstance(city, str):
        city = ""
    district = poi.get("adname") if isinstance(poi.get("adname"), str) else ""
    city_text = city.removesuffix("市")
    return f"{city_text}·{district}" if district else city_text


@router.get("/nearby-pois")
async def nearby_pois(
    lng: float = Query(...),
    lat: float = Query(...),
    radius: int = Query(1500, ge=100, le=5000),
    _payload: TokenPayload = Depends(require_role("teacher")),
):
    """坐标附近的可选地点（住宅/学校/商务等 POI），供教员点选更精确的常驻地。"""
    _validate_coords(lng, lat)
    data = await _amap_get(
        "/v3/place/around",
        {"location": f"{lng},{lat}", "radius": radius, "offset": 8, "page": 1, "sortrule": "distance"},
    )
    items: list[dict] = []
    for poi in data.get("pois") or []:
        try:
            p_lng, p_lat = (float(x) for x in str(poi.get("location") or "").split(","))
        except ValueError:
            continue
        name = str(poi.get("name") or "").strip()
        if not name:
            continue
        items.append({
            "name": name,
            "address": str(poi.get("address") or ""),
            "area": _poi_area(poi),
            "lng": p_lng,
            "lat": p_lat,
        })
    return {"items": items}


@router.get("/search-pois")
async def search_pois(
    keywords: str = Query(..., min_length=1, max_length=50),
    city: str = Query("成都", max_length=20),
    _payload: TokenPayload = Depends(require_role("teacher")),
):
    """按关键字搜地点（全国不限城市受限池，city 用于提高相关性）。
    桌面浏览器只有 IP 粗定位（误差可达数十公里），关键字搜索才是准确的选点方式。"""
    keyword = keywords.strip()
    if not keyword:
        raise HTTPException(status_code=422, detail="请输入搜索关键词")
    data = await _amap_get(
        "/v3/place/text",
        {"keywords": keyword, "city": city, "citylimit": "true", "offset": 8, "page": 1},
    )
    items: list[dict] = []
    for poi in data.get("pois") or []:
        try:
            p_lng, p_lat = (float(x) for x in str(poi.get("location") or "").split(","))
        except ValueError:
            continue
        name = str(poi.get("name") or "").strip()
        if not name:
            continue
        items.append({
            "name": name,
            "address": str(poi.get("address") or ""),
            "area": _poi_area(poi),
            "lng": p_lng,
            "lat": p_lat,
        })
    return {"items": items}
