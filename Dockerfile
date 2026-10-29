# 后端 API 镜像
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 非 root 运行。凭证目录需预建并赋属主：named volume 首次挂载空卷时会拷贝
# 镜像内该路径的内容与属主，不预建则卷属主为 root，app 用户写入被拒
# （2026-09 彩排实测：RECEIPT_DIR 全部 Permission denied）
RUN useradd --system --no-create-home app \
    && mkdir -p /app/data/receipts \
    && chown -R app:app /app
USER app

EXPOSE 8000

# 生产不建议 --reload；2G 目标机（99元/年 e实例）单 worker：双 worker 各占 ~250M，
# 挤占 MySQL 内存预算，试点流量异步单进程足够（并发扩展靠升配/副本）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
