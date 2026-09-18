# 上线 Checklist（从零到生产，半天走完）

> 配套 [DEPLOY.md](../DEPLOY.md) 使用：DEPLOY.md 讲"怎么做"，本文是逐项打勾的执行单，
> 按 0→6 顺序走完即可上线。每步验收标准已标注。

## 0. 选型与购买（10 分钟）

| 项 | 建议 | 说明 |
|---|---|---|
| 服务器 | 轻量应用服务器 2核2G 起（预算够选 2核4G） | 验证期选**香港节点按月付**（免备案、当天可用、随时退）；有付费客户后换国内节点 + ICP 备案，Docker 迁移半天 |
| 域名 | 任意便宜域名（¥20~60/年） | A 记录解析到服务器 IP；走 HTTPS 必须 |
| HTTPS | **仓库自带 Caddy 方案（推荐）**：`deploy/Caddyfile` + `deploy/docker-compose.https.yml` | 自动签发/续期 Let's Encrypt 证书，两条命令启用（见 §4 启动命令）；或 Cloudflare 免费版代理。微信内打开 H5 强烈建议 HTTPS，避免"不安全"警告劝退教员 |

**验收**：`ping 域名` 解析生效，`ssh root@服务器IP` 能登录。

## 1. 第三方 Key 申请（与服务购买并行，当天完成）

| Key | 申请入口 | 用途 | 注意 |
|---|---|---|---|
| `DEEPSEEK_API_KEY` | platform.deepseek.com | AI 订单解析（batch-parse） | 充值 ¥10 可用很久；限流默认 20 次/分钟 |
| `AMAP_API_KEY`（后端） | lbs.amap.com → 创建应用 → **Web 服务** | 订单/常驻地地理编码 | 与前端 Key 不是同一个 |
| `VITE_AMAP_KEY`（前端） | lbs.amap.com → 同一应用 → **Web 端(JS API)** | 教员端地图 | 需在高德控制台配置**域名白名单/安全密钥**，否则地图空白 |

**验收**：三个 Key 都能在控制台看到额度。

## 2. 服务器初始化（15 分钟）

```bash
# 1) 安装 Docker + Compose 插件（以 Ubuntu/Debian 为例）
curl -fsSL https://get.docker.com | sh

# 2) 云控制台安全组/防火墙：放行 22、80、443
# 3) 2G 内存机器建议加 1~2G swap（MySQL + API 同机更稳）
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# 4) 拉代码
git clone https://github.com/lii-lii321/smart_tutor.git && cd smart_tutor
```

**验收**：`docker --version` 正常；`free -h` 能看到 swap。

## 3. 配置逐项清单（15 分钟）

```bash
cp .env.production.example .env.production
cp frontend/.env.production.example frontend/.env.production

# 一键生成 4 个必填密钥（DB 密码×2 / JWT_SECRET / OWNER_ACCESS_CODE），
# 打印的块直接粘贴进 .env.production 即可；--count 3 可生成 3 组备选
python scripts/generate_secrets.py
```

`.env.production`（后端/编排）：

| 变量 | 必填 | 怎么填 |
|---|---|---|
| `DB_PASSWORD` | ✅ | 强随机密码（`openssl rand -hex 16`），仅容器内网使用 |
| `MYSQL_ROOT_PASSWORD` | ✅ | **必须与 `DB_PASSWORD` 不同**（`openssl rand -hex 16`）；compose 启动强制要求 |
| `DB_USER` / `DB_NAME` | — | 默认 `smart_tutor` 不用动 |
| `JWT_SECRET` | ✅ | `openssl rand -hex 32`，**≥32 字符**，泄露等于全员登录态失守 |
| `OWNER_ACCESS_CODE` | ✅ | 老板入口访问码，**禁止使用默认 `boss888`** |
| `JWT_EXPIRE_HOURS` | — | 默认 72 |
| `DEEPSEEK_API_KEY` | ✅ | 第 1 步申请 |
| `AMAP_API_KEY` | ✅ | 第 1 步（Web 服务 Key） |
| `WX_APPID` / `WX_SECRET` | — | 不启用微信登录留空 |
| `SENTRY_DSN` | — | 错误上报（sentry.io 建项目后粘贴）；留空 = 不启用。上线后到后台确认收到事件 |
| `WEB_PORT` | — | 默认 80；**用 Caddy HTTPS 时设 8080**（宿主 80/443 让给 Caddy） |
| `SITE_DOMAIN` | 用 Caddy 时必填 | 你的域名（如 `tutor.example.com`），Caddy 据此自动签发证书 |
| 限流三项 | — | 默认值即可 |

`frontend/.env.production`（构建期注入）：

| 变量 | 必填 | 怎么填 |
|---|---|---|
| `VITE_API_BASE` | — | 默认 `/api/v1` 不用动 |
| `VITE_AMAP_KEY` | ✅ | 第 1 步（Web 端 JS Key） |
| `VITE_AMAP_VERSION` | — | 默认 2.0 |
| `VITE_SENTRY_DSN` | — | 错误上报（Vue 项目 DSN）；留空 = 不启用 |

**验收**：`grep "=$" .env.production` 输出里不应再出现必填项（全部有值）。

## 4. 启动与验收（20 分钟）

```bash
# 1) 构建并启动四容器（MySQL/Redis/API/Nginx）
docker compose --env-file .env.production up -d --build

# 1b) HTTPS（用 Caddy 方案时；跳过则走明文 80）：
#     前置：DNS A 记录已生效 + .env.production 已设 SITE_DOMAIN 与 WEB_PORT=8080
docker compose --env-file .env.production \
  -f docker-compose.yml -f deploy/docker-compose.https.yml up -d

# 2) 首次建表（只跑一次）
docker compose exec api alembic upgrade head

# 3) 上线预检（红线/迁移到位/Redis/第三方 Key/日志目录；退出码 0 = 可上线）
docker compose exec api python scripts/preflight.py

# 4) 健康检查
curl http://127.0.0.1/health        # {"status":"ok",...}（Caddy 方案用 https://域名/health）
```

全链路冒烟（21 项断言，用真实凭证，会自建临时中介并在结束时停用，不留脏数据）：

```bash
# 本机装有 Python + httpx 时，在项目根目录执行：
python scripts/smoke_test.py --base http://127.0.0.1 \
  --tenant-code <你的邀请码> --tenant-password <中介密码> --boss-code <你的访问码>
```

浏览器验收（按顺序）：

1. 打开 `https://域名` → 教员登录页 → 老板入口 → 用 `OWNER_ACCESS_CODE` 登录
2. 创建第一个真实中介（拿到邀请码 + 一次性初始密码）
3. 用中介身份登录 `/admin/login` → 工作台四张统计卡 + **「本月为你」卡片**正常显示
4. 批量导入粘贴一段真实微信文本 → 地图上能看到新单
5. 手机微信里打开 `/teacher/board/<邀请码>` → 橱窗地图正常、投递走通一单

**验收**：冒烟 21 项全 PASS + 上面 5 步全通过。

## 5. 上线后首日（半小时）

- [ ] 通知教员开始投递（首批目标 30~50 人：校园群/兼职群发橱窗链接）
- [ ] 每日自动备份已由 `db-backup` 容器接管（宿主机 `./backups/`，保留 14 天）；
      手工抽查一份最新 SQL 能否 `mysql < file` 空库回放成功
- [ ] `docker compose logs -f api` 扫一眼有无异常堆栈

## 6. 常见坑（出问题先查这里）

- **启动即退出，报"生产环境必须配置 JWT_SECRET"**：没用 `--env-file .env.production` 启动
- **AI 解析 502/超时**：`DEEPSEEK_API_KEY` 未配或欠费；单次粘贴上限 2 万字符
- **地图空白**：`VITE_AMAP_KEY` 用错成 Web 服务 Key，或高德控制台没配域名白名单
- **HTTPS 后接口全挂**：Cloudflare 用 Full 模式；Caddy 方案里反代目标写的是容器端口 `web:80`，不要改成 `localhost:8000`
- **Caddy 起不来/证书签不出**：`SITE_DOMAIN` 未设置、DNS 未生效、或宿主 80/443 被 web 占用（把 `WEB_PORT` 改 8080 后 `up -d` 重建 web 再起 caddy）
- **80 端口被占**：改 `WEB_PORT=8080`，Caddy/Cloudflare 指向新端口
- **时间口径**：库内统一存 UTC，「本月为你」按 UTC 自然月聚合——与北京自然月最多差 8 小时边界，月内看数无感
- **迁移报"重复手机号"**：仅当从旧库搬迁数据时可能出现，见 DEPLOY.md §7
- **改了前端 env 不生效**：前端变量是**构建期注入**，改完必须 `docker compose up -d --build web`

## 7. 密钥轮换操作单（泄露/定期轮换时按此执行）

> 原则：所有轮换都在低峰期做；改 `.env.production` 后 `docker compose --env-file .env.production up -d`
> 即可让后端生效（改前端变量才需要 `--build web`）；新密钥用 `python scripts/generate_secrets.py` 生成。

| 密钥 | 在哪轮换 | 生效方式 | 影响面 |
|---|---|---|---|
| `JWT_SECRET` | 本地生成 → `.env.production` | `up -d` 重建 api/scheduler | **全员登录态立即失效**，需重新登录（投递中的数据不丢） |
| `OWNER_ACCESS_CODE` | 本地生成 → `.env.production`，同步把 `OWNER_TOKEN_VALID_AFTER` 设为当前 UTC 时间 | `up -d` | 旧老板会话全部吊销（时间戳吊销已内置） |
| `DB_PASSWORD` | 1) MySQL 内 `ALTER USER 'smart_tutor'@'%' IDENTIFIED BY '新密码';` 2) 改 `.env.production` 3) `up -d`（api/scheduler/db-backup 都读它） | 分步执行，先改库再改 env | 短暂窗口内 api 会断连重连（pool_pre_ping 自动恢复） |
| `MYSQL_ROOT_PASSWORD` | compose 仅初始化时使用一次；**运行后修改需进容器手改**（`ALTER USER 'root'@'localhost'`）并同步 env | 同上 | root 仅运维用，业务不受影响 |
| `WX_SECRET` | 微信公众平台/开放平台 → 重置 AppSecret | `up -d` | 微信登录在重置后短暂不可用 |
| `DEEPSEEK_API_KEY` | platform.deepseek.com → API Keys | `up -d` | AI 解析暂停至新 Key 生效 |
| `AMAP_API_KEY` | lbs.amap.com → 应用管理 → 重置 Key（前端 VITE key 同理，重置后需 `--build web`） | `up -d` / 前端 `--build web` | 地理编码与地图暂停至新 Key 生效 |
| `SENTRY_DSN` | sentry.io → 项目设置 → Client Keys | `up -d` / 前端 `--build web` | 仅影响错误上报连续性，无业务影响 |

轮换后验证：`docker compose exec api python scripts/preflight.py` 退出码 0；
再走一遍冒烟（§4 的 smoke_test）确认登录/解析/地图三条链路正常。
