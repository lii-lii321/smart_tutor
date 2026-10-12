"""
Embedding 服务：OpenAI 兼容 /embeddings 接口薄封装（默认硅基流动 BAAI/bge-m3）。

DeepSeek 公开 API 没有 embedding 端点，向量能力属独立供应商；统一走本模块，
换供应商只改 EMBEDDING_* 配置。向量统一 L2 归一化后返回：下游余弦相似度
退化为点积，存储只需 float32 BLOB。
"""

import logging

import httpx
import numpy as np
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

# 单请求批量上限留裕量：切片 ≤500 字，批量 16 段远低于 bge-m3 的 8192 token 上限
_EMBED_BATCH_SIZE = 16


class EmbeddingUnavailableError(RuntimeError):
    """Embedding 服务不可用（未配置/网络失败）：调用方降级为诚实提示，不重试烧钱。"""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type((httpx.HTTPError,)),
)
async def _embed_batch(texts: list[str]) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{settings.EMBEDDING_BASE_URL.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {settings.EMBEDDING_API_KEY}"},
            json={"model": settings.EMBEDDING_MODEL, "input": texts},
        )
    resp.raise_for_status()
    data = resp.json()["data"]
    # 按 index 还原输入顺序：部分供应商不保证 data 有序
    data.sort(key=lambda item: item["index"])
    return [item["embedding"] for item in data]


def l2_normalize(arr: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(arr))
    return arr / norm if norm > 0 else arr


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量向量化并 L2 归一化；未配置/调用失败抛 EmbeddingUnavailableError（调用方降级）。"""
    if not (settings.EMBEDDING_API_KEY or "").strip():
        raise EmbeddingUnavailableError("未配置 Embedding 服务（EMBEDDING_API_KEY）")
    if not texts:
        return []

    vectors: list[list[float]] = []
    try:
        for start in range(0, len(texts), _EMBED_BATCH_SIZE):
            batch = texts[start : start + _EMBED_BATCH_SIZE]
            vectors.extend(await _embed_batch(batch))
    except httpx.HTTPError as exc:
        logger.warning("Embedding 调用失败：%s", type(exc).__name__)
        raise EmbeddingUnavailableError("Embedding 服务暂时不可用") from exc

    return [l2_normalize(np.asarray(vec, dtype=np.float32)).tolist() for vec in vectors]
