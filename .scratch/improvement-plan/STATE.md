# 夜间执行状态（NIGHT + 续跑迭代全部完成）

- 夜间会话 2 开始：2026-09-10 晚（NIGHT 计划 6 项全部完成后，经用户确认继续迭代）
- 迭代会话：2026-09-10 深夜（CI 验证 → 双路审查 → 修复/加固 → P2-6/P3/P2-8 → 自查）
- 基线：NIGHT 起点 `1874cf9`；迭代起点 `1193225`

## 勾选清单

### 前两个会话（P0 全量 + P1 后端 + NIGHT 核心，全部完成）
- [x] P0-1~P0-8、P1-3/P1-4/P1-7/P1-8（详见 git log `c5ab60b`..`1bfd54e`）
- [x] NIGHT：P2-2 vitest、P2-4 hypothesis、P1-5 usePagedList、P1-6 三件套、
      P1-2 弹窗拆分、测试迁移 ×3（`0d0bf52`..`2dd2f54`）

### 迭代会话（2026-09-10 深夜）
- [x] CI 前端 job 接入 vitest（`aab9200`）+ push，三 job 绿
- [x] 双路审查：后端 9 项 + 前端 11 项发现（两项 agent 审计）
- [x] 后端修复 ×7：限流真实 IP + wx 登录限流、临期提醒按周期去重、拉黑 403、
      PATCH null 安全化、导出行数上限、GEO 空租户标记、AUTO_CREATE_SCHEMA 护栏
      （`369f31f`..`5d58812`，90 passed）
- [x] 前端修复 ×4：守卫仅 401 登出 + owner 直达、retry 排除 auth + 401 去重、
      Board 地图销毁/竞态、列表加载失败提示（`6ec91da`..`48f862f`，build + 29 用例）
- [x] P2-6 资金审计日志 ×4：表+迁移、五个写路径钩子、超管查询接口、回归测试
      （`59798d9`..`7a1c74b`，94 passed + 迁移 round-trip 本地验证）
- [x] P3 文档：CONTEXT.md + ADR-0001~0004（`c2cbe35`）
- [x] P2-8 CSP Report-Only 观察期（`334192c`）
- [x] OWNER_TOKEN_VALID_AFTER 老板会话全局吊销（`21ee731`）
- [x] compose 镜像命名（`20c80ca`）
- [x] ADR-0005 PII 静态加密草案（待评审，未实施）（`21ed15d`）
- [x] push `21ed15d`，CI 三 job 全绿（run 34503938975）
- [x] 后台自查 agent 复查 aab9200..HEAD：3 项发现全部修复（审计 SAVEPOINT 隔离 `25bc80b`、
      Board 卸载竞态 `7b20289`、提醒周期局限注释 `42da0d7`），日志补录 `cd18a16`
- [x] 最终 push `cd18a16`，CI 三 job 再次全绿（run 34506171975）
- [x] 问题清单文档 OPEN-ISSUES-2026-09-11.md（`8b689fe`）
- [x] §1.1 临期提醒周期持久化（`41c72c1`，96 passed + 迁移 d7e2b4a8f6c1 round-trip）
- [x] §1.3 usePagedList 翻页死端守卫（`b3c7e47`，vitest 30 用例）
- [x] P1-9 Sentry 接入（`219686b`）：前后端 DSN 环境变量化 no-op，本地 .env 已配置真实 DSN；
      顺带修 .gitignore 误伤 `**/.env.*.example` 模板的问题（两个生产样例模板首次入库）
- [x] 最终 push `a3b53dc` CI 绿 + `219686b` 起 CI 绿
- [x] 会话 4（2026-09-12 凌晨，2 小时限时）：第三轮审查 7 项处置（accf591/7713212）、
      §5.1 前端类型统一（3e631d9）、P2-5 /internal/stats（092773b）、
      P2-3 Playwright E2E + workflow_dispatch（f04ae74）、
      **E2E 首跑抓到 P1 bug**：游客逛橱窗被误踢登录页（dfd2c96）、
      init_db 回填 expiry_refreshed_at（b963156）、
      依赖专项：pinia 4.0.3（d02d02c）+ vue-router 5.3.1（01efce3）、
      掩码边界测试（tests/test_masking.py）、SIM105 复判跳过、文档收尾（e52926a 起）

## 当前进行项

（无——全部收尾，等待用户白天验收）

## 最终基线

pytest 95 passed / ruff 全绿 / 前端 vitest 29 用例 + build 过 /
CI 三 job 绿（run 34506171975，MySQL 迁移 round-trip 含 b2f6d8e4c1a9）/ compose config 过。

## 明确不做（留白天，附原因）

1. P1-1 Board.vue 拆分——红线（需真机冒烟，独占会话）
2. P2-1 database.py 收敛——需 MySQL 对账前置
3. P1-9 Sentry——需 DSN 决策
4. P2-7 教员注销流程——动登录/注册语义（手机号 hash 防重复注册），必须有人盯回归；
   其前置 ADR-0005（PII 加密）已产出草案待评审
5. P2-3 Playwright E2E、P2-5 metrics——体量大/需产品决策
6. 前端 api/*.ts 返回类型统一——涉及面广，留专项
