# 后端 API 镜像
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 非 root 运行：应用无本地写盘需求（生产连 MySQL/Redis）
RUN useradd --system --no-create-home app \
    && chown -R app:app /app
USER app

EXPOSE 8000

# 生产不建议 --reload；并发由容器副本数扩展
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
