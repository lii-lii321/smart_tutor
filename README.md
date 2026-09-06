# 智派家教 · Smart Tutor

多租户家教订单匹配平台：中介发布订单 → 教员橱窗浏览/投递 → 中介审核带教（定金/试课/尾款）→ 成交评价。支持 AI 解析微信聊天批量导入订单、地理编码地图看单、教员信用画像与推荐排序。

> 技术栈：FastAPI（异步）+ SQLAlchemy 2 + Pydantic v2 · Vue 3 + Vite + TS + Vant · MySQL / SQLite · Redis · JWT · Alembic · Docker

## 功能总览

**三端角色**

| 角色 | 入口 | 能力 |
|---|---|---|
| 教员（C 端 H5） | `/teacher/board/{邀请码}` | 手机号+密码登录；橱窗地图找单、个性化推荐、投递、取消/退定金、家长联系方式解锁、通知、我的费用、收到的评价 |
| 中介（B 端后台） | `/admin/login` | 邀请码+密码登录；AI 批量导入订单、投递审核全流程、订单管理、财务流水（筛选/导出）、教员管理（信用画像/拉黑）、B 端通知 |
| 平台老板 | 教员登录页 → 老板入口 | 访问码登录；中介/邀请码管理（一次性初始密码、重置）、教员全局封禁、经营看板（漏斗/中介排行） |

**业务闭环**

- 订单生命周期：招聘中 → 试课中 → 已完成 / 已归档，投递流程驱动并全量走状态机守卫 + 行锁
- 资金链路（线下收款模式）：定金 → 尾款 → 退款/没收，每笔流水登记操作人，净收入公式保证台账守恒；重开有已收款投递的订单会被强制先完成资金处置
- 信用体系：教员档案聚合成交数/违约数/评价均分，进投递列表展示与推荐排序；中介级黑名单（只限本租户）+ 平台级封禁
- 通知：教员（投递流转/评价）+ 中介（新投递/订单临期），带未读角标

## 快速开始（本地开发）

```bash
# 后端（Python 3.11+）
pip install -r requirements-dev.txt
# .env 中设置 DEV_MODE=true 后启动，自动建表并播种演示数据
uvicorn main:app --reload --port 8000

# 前端（Node 20+）
cd frontend
npm install
npm run dev   # http://127.0.0.1:5173
```

演示账号（DEV_MODE 播种，密码均为 `dev123456`）：

| 角色 | 凭证 |
|---|---|
| 中介 | 邀请码 `tx886` |
| 教员 | 手机号 `13900000001`（王/陈/刘老师为 `…002/003/004`） |
| 平台老板 | 访问码 `boss888`（生产必须改） |

## 生产部署

见 [DEPLOY.md](DEPLOY.md)。概要：`docker compose --env-file .env.production up -d --build` → `alembic upgrade head`；MySQL 8.4 + Redis 7 + API + Nginx 四容器，HTTPS 建议走 Cloudflare 或 Caddy。

## 测试与 CI

```bash
python -m pytest tests/ -q   # 58 个用例：认证/资金守卫/状态机/通知/评价/看板/限流
```

GitHub Actions 在 push/PR 时自动执行后端测试与前端类型检查+构建（[.github/workflows/ci.yml](.github/workflows/ci.yml)）。

## 目录结构

```
routers/v1/    # API：auth / orders / applications / financial_records
               #      / recommendations / notifications / tenants / resumes
services/      # 业务：calculator（Decimal 精算）/ recommendation / parser（AI）
               #      / geo / order_maintenance（归档+临期提醒）/ scheduler
models/        # ORM 与 Pydantic schemas
middleware/    # JWT 守卫（租户停用实时回查、token 立即失效）+ Redis 限流
alembic/       # 迁移链（生产建表唯一途径；本地 DEV 自动补丁）
frontend/      # Vue3 H5：views/teacher（教员端）views/admin（中介+老板端）
scripts/       # SQLite→MySQL 数据搬迁
```

## 安全要点

- 凭证：教员/中介密码 bcrypt；邀请码+密码双因子；访问码常量时间比较；认证端点限流（Redis，故障降级进程内）
- 隐私：C 端与公开橱窗坐标降精度至小区级；订单原文手机号/微信号/QQ 脱敏；家长联系方式仅试课后解锁
- 失效：中介停用/教员封禁实时回查；改密后已签发 JWT 立即作废（token_valid_after）
- 财务：金额 Decimal 半进一舍入；退款封顶实收；零退款强制补记没收流水

## 更多文档

- [DEPLOY.md](DEPLOY.md) — 生产部署与运维
- [CHANGELOG.md](CHANGELOG.md) — 版本记录
- [AGENTS.md](AGENTS.md) — 仓库协作约定
