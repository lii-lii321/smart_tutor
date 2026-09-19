"""
收款凭证（转账截图）存储：半线上化的对账增强。

- 落服务器本地盘 RECEIPT_DIR（默认 ./data/receipts，compose 挂卷持久化）；
- 只收图片（png/jpeg/webp），≤5MB——凭证是人工核对的附件，不是对象存储业务；
- 文件名随机（secrets），不透传用户原名（防路径注入与个人信息泄露）；
- 读取走鉴权端点（本租户 B 端 / 教员本人 / 超管），不暴露静态路径。
"""
import logging
import secrets
from pathlib import Path

from fastapi import HTTPException, UploadFile

from config import settings

logger = logging.getLogger(__name__)

# 5MB：手机截图普遍 0.5~3MB，留余量
MAX_RECEIPT_SIZE = 5 * 1024 * 1024
# 允许的图片类型（按魔数校验，不信任扩展名与前端 MIME）
_ALLOWED_MAGIC = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpg",
}
_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}


def receipt_dir() -> Path:
    path = Path(settings.RECEIPT_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _magic_extension(data: bytes) -> str | None:
    for magic, ext in _ALLOWED_MAGIC.items():
        if data.startswith(magic):
            return ext
    # webp：RIFF....WEBP
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


async def save_receipt(file: UploadFile) -> str:
    """校验并保存凭证，返回相对路径（供 receipt_path 列与读取端点用）。"""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="凭证文件为空")
    if len(data) > MAX_RECEIPT_SIZE:
        raise HTTPException(status_code=422, detail="凭证文件不能超过 5MB")

    ext = _magic_extension(data)
    if ext is None:
        raise HTTPException(status_code=422, detail="仅支持 png/jpg/webp 图片")
    # 扩展名白名单双保险（魔数已识别，这里只防奇怪的组合）
    original_ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if original_ext and original_ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail="仅支持 png/jpg/webp 图片")

    name = f"{secrets.token_hex(12)}.{ext}"
    target = receipt_dir() / name
    try:
        target.write_bytes(data)
    except OSError as exc:
        logger.exception("failed to save receipt")
        raise HTTPException(status_code=500, detail="凭证保存失败，请稍后重试") from exc
    return name


def receipt_file(path: str) -> Path:
    """按存储名取文件路径；防目录穿越（名字由 save_receipt 生成，这里兜底校验）。"""
    if "/" in path or "\\" in path or ".." in path or not path:
        raise HTTPException(status_code=404, detail="凭证不存在")
    target = receipt_dir() / path
    if not target.is_file():
        raise HTTPException(status_code=404, detail="凭证不存在")
    return target
