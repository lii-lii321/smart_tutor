# ADR-0004: 全库 naive UTC 时间口径

- 状态：已采纳（迁移 tz-aware 列为远期预案，见"未决"）
- 日期：2026-09-09（成文 2026-09-10）
- 关联代码：`middleware/auth.py`（文件头有踩坑注释）、`database.py`（MySQL 会话
  `SET time_zone='+00:00'`）、`services/order_maintenance.py`（`datetime.datetime.utcnow()`）、
  `routers/v1/financial_records.py`（日期筛选）

## 背景

业务时间戳（订单创建/过期、投递节点、财务流水、通知、审计）最初以 naive `datetime.utcnow()`
写入。跨午夜场景暴露过真实缺陷：财务"今天"筛选在东八区 0:00–8:00 查不到刚发生的流水
（测试用本地 `date.today()`、库存 UTC），该 flaky 已修复为 UTC 口径。

## 决策

1. **存储与比较一律 naive UTC**：所有 `datetime.datetime.utcnow()`、TIMESTAMP 列、
   日期区间筛选（start_date/end_date 解释为 UTC 自然日）。
2. **MySQL 会话时区固定 +00:00**（`database.py` 建连即设置），保证 `CURRENT_TIMESTAMP`
   这类库端默认值与应用写入的 utcnow 同口径（audit_logs/notifications 的 created_at 依赖它）。
3. **展示层本地化**：前端 `utils/format.ts` 用本地时区渲染（`YYYY-MM-DD HH:mm`），
   后端 API 不做时区转换、不返回偏移量。
4. **测试同口径**：测试里构造时间一律 `utcnow()`/UTC 日期，禁止 `date.today()`
   （跨午夜 CI 会 flaky——已发生一次，见 PLAN.md 执行日志 2026-09-09）。
5. ruff 已 ignore DTZ 规则：naive datetime 是约定而非疏漏。

## 后果

- 正向：无时区转换 Bug 面；库端/应用端时间一致；跨容器部署不依赖宿主时区。
- 代价：面向中国用户的"自然日"语义与 UTC 日相差 8 小时——财务日筛选、
  "近 7 天"等口径实际按 UTC 日切。当前业务量下可接受。
- 未决：若产品要求本地自然日口径，路径是：先写迁移预案把列升级为 tz-aware（timestamptz /
  DATETIME+显式转换），再在边界层统一转东八区；需要全量回归资金流水，**不在夜间执行**。
