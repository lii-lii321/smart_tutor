# 上线 Checklist（从零到生产，半天走完）

> 配套 [DEPLOY.md](../DEPLOY.md) 使用：DEPLOY.md 讲"怎么做"，本文是逐项打勾的执行单，
> 按 0→6 顺序走完即可上线。每步验收标准已标注。

## 0. 选型与购买（10 分钟）

| 项 | 建议 | 说明 |
|---|---|---|
| 服务器 | 轻量应用服务器 2核2G 起（预算够选 2核4G） | 验证期选**香港节点按月付**（免备案、当天可用、随时退）；有付费客户后换国内节点 + ICP 备案，Docker 迁移半天 |
| 域名 | 任意便宜域名（¥20~60/年） | A 记录解析到服务器 IP；走 HTTPS 必须 |
| HTTPS | 服务器装 Caddy 反代（推荐）或 Cloudflare 免费版代理 | 微信内打开 H5 强烈建议 HTTPS，避免"不安全"警告劝退教员 |

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
```

`.env.production`（后端/编排）：

| 变量 | 必填 | 怎么填 |
|---|---|---|
| `DB_PASSWORD` | ✅ | 强随机密码（`openssl rand -hex 16`），仅容器内网使用 |
| `DB_USER` / `DB_NAME` | — | 默认 `smart_tutor` 不用动 |
| `JWT_SECRET` | ✅ | `openssl rand -hex 32`，**≥32 字符**，泄露等于全员登录态失守 |
| `OWNER_ACCESS_CODE` | ✅ | 老板入口访问码，**禁止使用默认 `boss888`** |
| `JWT_EXPIRE_HOURS` | — | 默认 72 |
| `DEEPSEEK_API_KEY` | ✅ | 第 1 步申请 |
| `AMAP_API_KEY` | ✅ | 第 1 步（Web 服务 Key） |
| `WX_APPID` / `WX_SECRET` | — | 不启用微信登录留空 |
| `WEB_PORT` | — | 默认 80；被占用改 8080（Caddy 反代指向它） |
| 限流三项 | — | 默认值即可 |

`frontend/.env.production`（构建期注入）：

| 变量 | 必填 | 怎么填 |
|---|---|---|
| `VITE_API_BASE` | — | 默认 `/api/v1` 不用动 |
| `VITE_AMAP_KEY` | ✅ | 第 1 步（Web 端 JS Key） |
| `VITE_AMAP_VERSION` | — | 默认 2.0 |

**验收**：`grep "=$" .env.production` 输出里不应再出现必填项（全部有值）。

## 4. 启动与验收（20 分钟）

```bash
# 1) 构建并启动四容器（MySQL/Redis/API/Nginx）
docker compose --env-file .env.production up -d --build

# 2) 首次建表（只跑一次）
docker compose exec api alembic upgrade head

# 3) 健康检查
curl http://127.0.0.1/health        # {"status":"ok",...}
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
- [ ] `docker compose exec db sh -c 'mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" smart_tutor' > backup_$(date +%F).sql` 手工备份一次，确认文件可用
- [ ] 加每日备份 cron（见 DEPLOY.md §4）
- [ ] `docker compose logs -f api` 扫一眼有无异常堆栈

## 6. 常见坑（出问题先查这里）

- **启动即退出，报"生产环境必须配置 JWT_SECRET"**：没用 `--env-file .env.production` 启动
- **AI 解析 502/超时**：`DEEPSEEK_API_KEY` 未配或欠费；单次粘贴上限 2 万字符
- **地图空白**：`VITE_AMAP_KEY` 用错成 Web 服务 Key，或高德控制台没配域名白名单
- **HTTPS 后接口全挂**：Cloudflare 用 Full 模式；Caddy 反代指向 `WEB_PORT` 而不是 8000
- **80 端口被占**：改 `WEB_PORT=8080`，Caddy/Cloudflare 指向新端口
- **时间口径**：库内统一存 UTC，「本月为你」按 UTC 自然月聚合——与北京自然月最多差 8 小时边界，月内看数无感
- **迁移报"重复手机号"**：仅当从旧库搬迁数据时可能出现，见 DEPLOY.md §7
- **改了前端 env 不生效**：前端变量是**构建期注入**，改完必须 `docker compose up -d --build web`
