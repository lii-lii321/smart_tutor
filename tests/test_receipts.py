"""
收款凭证（半线上化对账）：上传鉴权/文件校验/读取权限矩阵/响应标记。

文件落 RECEIPT_DIR（tmp_path 隔离），图片用真实魔数构造（png/jpg/webp 头）。
"""
import io as _io

from conftest import (
    auth_header,
    make_order,
    make_teacher,
    make_tenant,
    teacher_token,
    tenant_token,
)

from models.domain import FinancialRecord, FinancialType

BASE = "http://test"


def boss_token() -> str:
    from services.auth import create_jwt
    return create_jwt(sub="super_admin_1", role="super_admin")


def _png_bytes(size: int = 100) -> bytes:
    """构造合法 PNG 头的最小文件（服务端按魔数识别，不解析内容）。"""
    # PNG 签名 + 最小 IHDR 骨架，服务端只做魔数与大小校验
    header = b"\x89PNG\r\n\x1a\n" + b"\x00" * max(0, size - 8)
    return header


def _receipt_filename() -> str:
    return ("test_receipt.png", _io.BytesIO(_png_bytes()), "image/png")


async def _seed_record(db, tenant, teacher, *, with_receipt: str | None = None) -> FinancialRecord:
    order = await make_order(db, tenant.id, f"RC-{teacher.id}-{abs(hash(teacher)) % 10000}")
    record = FinancialRecord(
        order_id=order.id,
        tenant_id=tenant.id,
        teacher_id=teacher.id,
        amount=100,
        type=FinancialType.deposit_in,
        operator_role="tenant_admin",
        receipt_path=with_receipt,
    )
    db.add(record)
    await db.flush()
    return record


async def test_upload_and_read_receipt_roundtrip(client, db, monkeypatch, tmp_path):
    monkeypatch.setattr("services.receipts.settings.RECEIPT_DIR", str(tmp_path))
    tenant = await make_tenant(db, "rc001a")
    teacher = await make_teacher(db, "rc_teacher_a")
    record = await _seed_record(db, tenant, teacher)
    await db.commit()
    headers = auth_header(tenant_token(tenant.id))

    resp = await client.post(
        f"{BASE}/api/v1/financial-records/{record.id}/receipt",
        files={"file": _receipt_filename()},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["has_receipt"] is True
    # 响应不透出存储路径，只透出 has_receipt（防御字段误加）
    assert resp.json().get("receipt_path") is None

    # 读取：本租户 OK
    resp = await client.get(
        f"{BASE}/api/v1/financial-records/{record.id}/receipt", headers=headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("image/png")

    # 教员本人可读
    resp = await client.get(
        f"{BASE}/api/v1/financial-records/{record.id}/receipt",
        headers=auth_header(teacher_token(teacher.id)),
    )
    assert resp.status_code == 200

    # 其他租户 404（不泄露存在性）
    other = await make_tenant(db, "rc001b")
    await db.commit()
    resp = await client.get(
        f"{BASE}/api/v1/financial-records/{record.id}/receipt",
        headers=auth_header(tenant_token(other.id)),
    )
    assert resp.status_code == 404

    # 无关教员 404
    stranger = await make_teacher(db, "rc_teacher_stranger")
    await db.commit()
    resp = await client.get(
        f"{BASE}/api/v1/financial-records/{record.id}/receipt",
        headers=auth_header(teacher_token(stranger.id)),
    )
    assert resp.status_code == 404

    # 超管可读
    resp = await client.get(
        f"{BASE}/api/v1/financial-records/{record.id}/receipt", headers=auth_header(boss_token())
    )
    assert resp.status_code == 200


async def test_upload_rejects_non_image_and_oversize(client, db, monkeypatch, tmp_path):
    monkeypatch.setattr("services.receipts.settings.RECEIPT_DIR", str(tmp_path))
    tenant = await make_tenant(db, "rc002a")
    teacher = await make_teacher(db, "rc_teacher_b")
    record = await _seed_record(db, tenant, teacher)
    await db.commit()
    headers = auth_header(tenant_token(tenant.id))

    # 非图片魔数
    resp = await client.post(
        f"{BASE}/api/v1/financial-records/{record.id}/receipt",
        files={"file": ("evil.png", _io.BytesIO(b"<script>alert(1)</script>"), "image/png")},
        headers=headers,
    )
    assert resp.status_code == 422
    assert "仅支持" in resp.json()["detail"]

    # 超过 5MB
    big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (5 * 1024 * 1024 + 1)
    resp = await client.post(
        f"{BASE}/api/v1/financial-records/{record.id}/receipt",
        files={"file": ("big.png", _io.BytesIO(big), "image/png")},
        headers=headers,
    )
    assert resp.status_code == 422

    # 空文件
    resp = await client.post(
        f"{BASE}/api/v1/financial-records/{record.id}/receipt",
        files={"file": ("empty.png", _io.BytesIO(b""), "image/png")},
        headers=headers,
    )
    assert resp.status_code == 422


async def test_cross_tenant_upload_blocked(client, db, monkeypatch, tmp_path):
    monkeypatch.setattr("services.receipts.settings.RECEIPT_DIR", str(tmp_path))
    tenant = await make_tenant(db, "rc003a")
    teacher = await make_teacher(db, "rc_teacher_c")
    record = await _seed_record(db, tenant, teacher)
    other = await make_tenant(db, "rc003b")
    await db.commit()

    resp = await client.post(
        f"{BASE}/api/v1/financial-records/{record.id}/receipt",
        files={"file": _receipt_filename()},
        headers=auth_header(tenant_token(other.id)),
    )
    assert resp.status_code == 404

    # 路径穿越防护：手工造一个含路径分隔符的 receipt_path 后读取必须 404
    record.receipt_path = "../evil.png"
    await db.commit()
    resp = await client.get(
        f"{BASE}/api/v1/financial-records/{record.id}/receipt",
        headers=auth_header(tenant_token(tenant.id)),
    )
    assert resp.status_code == 404


async def test_mine_record_marks_has_receipt_false(client, db):
    """教员费用列表的 has_receipt 缺省 False：无凭证不误报。"""
    tenant = await make_tenant(db, "rc004a")
    teacher = await make_teacher(db, "rc_teacher_d")
    await _seed_record(db, tenant, teacher)
    await db.commit()

    resp = await client.get(
        f"{BASE}/api/v1/financial-records/mine",
        headers=auth_header(teacher_token(teacher.id)),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["records"], "应至少有一条流水"
    assert all(r["has_receipt"] is False for r in body["records"])
