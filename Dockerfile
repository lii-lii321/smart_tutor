# 后端 API 镜像
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
# pip 走阿里云镜像源：成都 ECS 直连 PyPI 实测 ~20KB/s（2026-11-01 部署实测，
# cryptography+numpy 按此速度需 15 分钟+且构建期全程停机），阿里云镜像同机房秒级
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

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
