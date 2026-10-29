"""F16 回归：OrderImportItem 字符串字段 max_length 与 orders 列宽对齐，超长值边界层 422。

背景：raw_id/grade_subject/price_total/fuzzy_address 等字段此前无 max_length，
200 字符输入可穿透边界层到 MySQL 触发 1406 DataError（e2e 实测 500；F14 兜底后
为误导性 422「超长字段（家长联系电话或门牌地址）」）。

修复：schemas.OrderImportItem 按 DB 列宽补 max_length（raw_id 50 / grade_subject 50 /
price_total 50 / fuzzy_address 100 / subway_remark 100 / exact_address 255 /
parent_phone 20；Text 列 raw_text 5000 / requirements 2000 宽松上限），超长在
边界层 422 且 loc 指向具体字段，不再触库。
"""
import pytest
from conftest import make_tenant, tenant_token
from httpx import AsyncClient

from models.domain import Order
from models.schemas import OrderImportItem, OrderUpdateRequest


def _max_len(model, field: str) -> int | None:
    for m in model.model_fields[field].metadata:
        if hasattr(m, "max_length"):
            return m.max_length
    return None


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("raw_id", 50),
        ("grade_subject", 50),
        ("price_total", 50),
        ("fuzzy_address", 100),
        ("subway_remark", 100),
        ("exact_address", 255),
        ("parent_phone", 20),
        ("raw_text", 5000),
        ("requirements", 2000),
    ],
)
def test_schema_limits_align_with_db_columns(field: str, expected: int):
    """导入模型各字符串字段 max_length 与 orders 列宽（或 Text 宽松上限）对齐。"""
    assert _max_len(OrderImportItem, field) == expected


def test_update_request_requirements_length_aligned():
    assert _max_len(OrderUpdateRequest, "requirements") == 2000


def _item(raw_id: str, fuzzy: str = "成都市锦江区") -> dict:
    return {
        "raw_id": raw_id,
        "raw_text": "【" + raw_id + "】初三数学 200/次",
        "grade_subject": "初三数学",
        "price_total": "200/次",
        "base_price": 200.0,
        "weekly_frequency": 2,
        "is_summer_vacation": False,
        "fuzzy_address": fuzzy,
        "lng": 104.065735,
        "lat": 30.659462,
        "calculated_info_fee": 400.0,
        "deposit_amount": 100.0,
        "balance_amount": 300.0,
    }


def _overlong_field_loc(resp_json) -> str:
    """FastAPI 422 detail 为校验错误列表，取首个错误的最后一个 loc 键。"""
    return resp_json["detail"][0]["loc"][-1]


async def test_overlong_fields_rejected_at_boundary_with_field_loc(client: AsyncClient, db):
    """raw_id / fuzzy_address 超长 → 422 且 loc 指向具体字段，不再穿透触库。"""
    tenant = await make_tenant(db, "f16t001")
    await db.commit()
    headers = {"Authorization": "Bearer " + tenant_token(tenant.id)}

    r_raw = await client.post(
        "/api/v1/orders/batch-import", json={"items": [_item("L" * 200)]}, headers=headers
    )
    assert r_raw.status_code == 422, r_raw.text
    assert _overlong_field_loc(r_raw.json()) == "raw_id"
    assert "50" in r_raw.json()["detail"][0]["msg"]

    r_fuzzy = await client.post(
        "/api/v1/orders/batch-import",
        json={"items": [_item("F16-FZ", fuzzy="武" * 200)]},
        headers=headers,
    )
    assert r_fuzzy.status_code == 422, r_fuzzy.text
    assert _overlong_field_loc(r_fuzzy.json()) == "fuzzy_address"


async def test_overlong_grade_subject_and_price_total_rejected(client: AsyncClient, db):
    tenant = await make_tenant(db, "f16t002")
    await db.commit()
    headers = {"Authorization": "Bearer " + tenant_token(tenant.id)}

    r_grade = await client.post(
        "/api/v1/orders/batch-import",
        json={"items": [_item("F16-GS", ) | {"grade_subject": "数" * 51}]},
        headers=headers,
    )
    assert r_grade.status_code == 422, r_grade.text
    assert _overlong_field_loc(r_grade.json()) == "grade_subject"

    r_price = await client.post(
        "/api/v1/orders/batch-import",
        json={"items": [_item("F16-PT") | {"price_total": "2" * 51}]},
        headers=headers,
    )
    assert r_price.status_code == 422, r_price.text
    assert _overlong_field_loc(r_price.json()) == "price_total"


async def test_valid_item_still_imports(client: AsyncClient, db):
    """列宽内的合法单不受影响（防边界收紧误伤）。"""
    tenant = await make_tenant(db, "f16t003")
    await db.commit()
    headers = {"Authorization": "Bearer " + tenant_token(tenant.id)}

    resp = await client.post(
        "/api/v1/orders/batch-import",
        json={"items": [_item("F16-OK", fuzzy="武" * 100), _item("F16-OK2", ) | {"raw_id": "R" * 50}]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 2

    first = await db.get(Order, 1)
    assert first is not None and first.raw_id == "F16-OK"
    assert len(first.fuzzy_address) == 100
