import math
import random


def offset_coordinate(
    lng: float, lat: float, min_offset: int = 30, max_offset: int = 80
) -> tuple[float, float]:
    """
    在 [min_offset, max_offset] 米范围内随机偏移坐标。
    用于将真实 GPS 坐标模糊化为小区级别，保护隐私。
    """
    angle = random.uniform(0, 2 * math.pi)
    distance = random.uniform(min_offset, max_offset)

    delta_lat = (distance * math.cos(angle)) / 111_320
    delta_lng = (distance * math.sin(angle)) / (111_320 * math.cos(math.radians(lat)))

    return round(lng + delta_lng, 6), round(lat + delta_lat, 6)


def haversine_distance(
    lng1: float, lat1: float, lng2: float, lat2: float
) -> float:
    """
    计算两点之间的球面距离（米），使用 Haversine 公式。
    """
    R = 6_371_000  # 地球半径（米）

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c
