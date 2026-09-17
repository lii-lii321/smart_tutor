# 部署指南（Docker Compose）

> 首次上线建议按 [docs/DEPLOY_CHECKLIST.md](docs/DEPLOY_CHECKLIST.md) 的执行单逐项打勾，半天可走完。

## 0. 前置要求

- 一台 Linux 服务器（2C4G 起步），安装 Docker + Docker Compose 插件
- 一个域名（可选，走 HTTPS 时需要）
- 第三方 Key：DeepSeek、高德（后端地理编码 + 前端地图各一份配额）

## 1. 获取代码与配置

```bash
git clone https://github.com/lii-lii321/smart_tutor.git
cd smart_tutor
```

```bash
# 后端/编排配置
cp .env.production.example .env.production
openssl rand -hex 32   # 生成 JWT_SECRET

# 前端构建配置（高德前端 Key）
cp frontend/.env.production.example frontend/.env.production
```

逐项填写 `.env.production` 与 `frontend/.env.production`。
生产环境严禁开启 `DEV_MODE` / `AUTO_CREATE_SCHEMA`（compose 已强制关闭）。

## 2. 启动

```bash
docker compose --env-file .env.production up -d --build
```

首次启动 MySQL 后需要执行一次数据库迁移建表：

```bash
docker compose exec api alembic upgrade head
```

验证：

```bash
curl http://<服务器IP>/health   # {"status":"ok",...}
```

浏览器打开 `http://<服务器IP>/`，用 `.env.production` 里配置的
`OWNER_ACCESS_CODE` 登录老板入口，创建第一个中介。

## 3. 从测试库搬迁数据（可选）

本地 SQLite 演示数据迁入生产 MySQL：

```bash
# 本机执行：源库 dev.db → 目标库（.env.production 的 DATABASE_URL）
docker compose exec api python scripts/migrate_sqlite_to_mysql.py
```

## 4. 日常运维

```bash
docker compose logs -f api          # 看后端日志
docker compose restart api          # 重启后端

# 数据库备份：compose 内置 db-backup 服务每日自动备份到宿主机 ./backups（保留 14 天，BACKUP_RETENTION_DAYS 可调）。
# 发版前仍按 4.1 手动备份一次；恢复时选最新一份：
docker compose exec db sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" smart_tutor' > backup_$(date +%F).sql

# 恢复（最后手段，见 4.2 数据回滚）
cat backup_2026-09-06.sql | docker compose exec -T db sh -c 'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" smart_tutor'
```

### 4.1 发版标准序列

```bash
# 1) 发布前手动备份一次（回滚的生命线）
docker compose exec db sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" smart_tutor' > backup_before_release_$(date +%F-%H%M).sql

# 2) 构建并替换容器
docker compose up -d --build api web

# 3) 新版本带数据库迁移时执行（已执行过则幂等，重复运行安全）
docker compose exec api alembic upgrade head

# 4) 上线预检（红线/迁移到位/Redis/第三方 Key/日志目录，只读体检）
docker compose exec api python scripts/preflight.py

# 5) 验证
curl -fsS http://127.0.0.1/health && docker compose logs --tail=50 api
```

要点：
- 本仓库的迁移全部是加列/加表/加索引/扩展枚举（只增不删），旧代码读新 schema 兼容，
  因此第 2、3 步的顺序颠倒不会造成停机；但两步应连续执行，中间不要停顿太久。
- `alembic check` 可在发布前本地验证模型与迁移是否漂移（CI 也会自动执行）。

### 4.2 回滚

按出问题的层面选择，通常只需要其中一步：

**代码回滚（最常用）**：切回上一个发布版本重建容器，schema 不动
（迁移只增不删，旧代码兼容新 schema）：

```bash
git checkout <上一个发布 tag 或 commit>
docker compose up -d --build api web
```

**迁移回滚**：仅当新迁移本身有问题时才需要，会丢新列的数据：

```bash
docker compose exec api alembic downgrade -1   # 回退一个版本
```

**数据回滚（最后手段，丢失备份点之后的全部业务数据）**：

```bash
cat backup_before_release_2026-09-13-1800.sql | docker compose exec -T db sh -c \
  'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" smart_tutor'
```

回滚后务必检查 `/health`、抽查一笔订单与财务流水，并查看 scheduler 容器日志。

## 5. HTTPS（上线前置条件，不是可选项）

登录态走 Authorization 头，教员手机号、家长住址电话、老板初始密码都经此传输——
裸 HTTP 上线等于这些 PII 全部明文过公网（token 72 小时有效，截获即可重放）。
未配好 HTTPS 之前不要对外放开流量。

最简方案：Cloudflare 免费版代理域名，SSL 模式必须选 **Full**
（Flexible 模式下 CF→源站仍是明文 HTTP，等于没加密，禁止使用）；或服务器上加 Caddy 反代（自动签证书）：

```
your.domain {
    reverse_proxy localhost:80
}
```

## 6. 架构说明

```
浏览器 ──HTTP──> web(nginx: 静态资源 + /api 反代)
                      │
                      ├──> api(uvicorn × 2 workers)
                      │      ├── MySQL 8（业务数据，volume 持久化）
                      │      └── Redis 7（GEO 缓存 + 分布式限流）
```

限流已走 Redis，多 worker / 多实例下计数共享；
Redis 故障时 API 自动降级（限流退化为进程内、GEO 退化为直查 MySQL）。

## 7. 常见问题

- **启动报"生产环境必须配置 JWT_SECRET"**：`.env.production` 未生效，
  确认用了 `--env-file .env.production`。
- **AI 解析 502/超时**：检查 `DEEPSEEK_API_KEY`；解析单次上限 2 万字符。
- **地图空白**：前端 `frontend/.env.production` 的 `VITE_AMAP_KEY` 未配置
  或该 Key 未绑定域名白名单。
- **迁移报错"重复手机号"**：历史数据存在同号账号，先执行
  `SELECT phone, COUNT(*) FROM teachers GROUP BY phone HAVING COUNT(*)>1;`
  合并或改号后再 `alembic upgrade head`。
