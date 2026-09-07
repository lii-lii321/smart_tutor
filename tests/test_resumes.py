"""
教员简历库回归测试：创建首份自动设默认、设默认互斥、删除默认后最新一份接任、
越权访问 404。简历是投递前置条件（_validate_resume_fit 依赖默认简历），必须防回归。

使用独立的临时 SQLite 库，不触碰 dev.db。
运行方式：
    python tests/test_resumes.py
或：
    pytest tests/test_resumes.py
"""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 必须在导入 app 之前设置测试环境 ──
_TMP = tempfile.NamedTemporaryFile(suffix="_resumes.db", delete=False)
_TMP.close()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP.name.replace(os.sep, '/')}"
os.environ["DEV_MODE"] = "true"
os.environ["JWT_SECRET"] = "test-secret-for-resumes-0123456789"
os.environ["OWNER_ACCESS_CODE"] = "test-boss-code"

import httpx  # noqa: E402

import database as database_mod  # noqa: E402
from main import app  # noqa: E402
from database import init_db, _get_sessionmaker  # noqa: E402
from models.domain import Teacher, Gender  # noqa: E402
from services.auth import create_jwt  # noqa: E402

BASE = "http://test"
RESUMES = f"{BASE}/api/v1/teacher/resumes"


def _fresh_db() -> None:
    engine = database_mod._engine
    if engine is not None:
        try:
            asyncio.run(engine.dispose())
        except Exception:
            pass
        database_mod._engine = None
        database_mod._async_sessionmaker = None
    try:
        os.unlink(_TMP.name)
    except OSError:
        pass


def teacher_token(teacher_id: int) -> str:
    return create_jwt(sub=f"teacher_{teacher_id}", role="teacher")


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _create_teacher(name: str, phone: str) -> int:
    sm = _get_sessionmaker()
    async with sm() as s:
        teacher = Teacher(
            openid=f"resume_{phone}", name=name, gender=Gender.male,
            phone=phone, wechat_id=f"wx_{phone}", school="测试大学", is_985_211=True,
        )
        s.add(teacher)
        await s.flush()
        teacher_id = teacher.id
        await s.commit()
        return teacher_id


def _resume_payload(title: str, is_default: bool = False) -> dict:
    return {
        "title": title,
        "teaching_subjects": "数学",
        "teaching_grades": "初一-初三",
        "experience": "两年家教经验",
        "is_default": is_default,
    }


async def _test_resume_lifecycle():
    await init_db()
    teacher_id = await _create_teacher("简历教员", "13600000001")
    other_teacher_id = await _create_teacher("隔壁教员", "13600000002")
    headers = auth(teacher_token(teacher_id))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE) as client:
        # 首份简历自动成为默认
        resp = await client.post(f"{RESUMES}/", json=_resume_payload("简历A"), headers=headers)
        assert resp.status_code == 200, resp.text
        resume_a = resp.json()
        assert resume_a["is_default"] is True, "第一份简历应自动设为默认"

        # 第二份显式 is_default=True → 与第一份互斥
        resp = await client.post(
            f"{RESUMES}/", json=_resume_payload("简历B", is_default=True), headers=headers
        )
        assert resp.status_code == 200, resp.text
        resume_b = resp.json()
        assert resume_b["is_default"] is True
        resp = await client.get(f"{RESUMES}/", headers=headers)
        defaults = [r for r in resp.json() if r["is_default"]]
        assert len(defaults) == 1 and defaults[0]["id"] == resume_b["id"], "默认简历必须互斥"

        # 设默认接口切换回 A
        resp = await client.post(f"{RESUMES}/{resume_a['id']}/default", headers=headers)
        assert resp.status_code == 200 and resp.json()["is_default"] is True

        # 编辑部分字段
        resp = await client.patch(
            f"{RESUMES}/{resume_a['id']}",
            json={"expected_rate": "200-260/次", "strengths": "擅长错题复盘"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["expected_rate"] == "200-260/次"

        # 越权：他人的简历读写一律 404
        foreign = auth(teacher_token(other_teacher_id))
        resp = await client.get(f"{RESUMES}/", headers=foreign)
        assert resp.status_code == 200 and resp.json() == []
        resp = await client.patch(
            f"{RESUMES}/{resume_a['id']}", json={"title": "抢简历"}, headers=foreign
        )
        assert resp.status_code == 404
        resp = await client.delete(f"{RESUMES}/{resume_a['id']}", headers=foreign)
        assert resp.status_code == 404

        # 删除当前默认 → 最新一份接任默认
        resp = await client.delete(f"{RESUMES}/{resume_a['id']}", headers=headers)
        assert resp.status_code == 200
        resp = await client.get(f"{RESUMES}/", headers=headers)
        remaining = resp.json()
        assert len(remaining) == 1
        assert remaining[0]["id"] == resume_b["id"] and remaining[0]["is_default"] is True, \
            "删除默认简历后应有一份接任默认，否则投递会被 422 堵死"
    print("[OK] resume_lifecycle")


def test_resume_lifecycle():
    _fresh_db()
    asyncio.run(_test_resume_lifecycle())


if __name__ == "__main__":
    test_resume_lifecycle()
    print("\n=== 简历库测试全部通过 ===")
    try:
        os.unlink(_TMP.name)
    except OSError:
        pass
