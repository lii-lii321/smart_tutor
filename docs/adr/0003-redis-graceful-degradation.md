# ADR-0003: Redis 一律可降级——缓存与限流的静默退化策略

- 状态：已采纳
- 日期：2026-09-06（成文 2026-09-10，追溯既有决策）
- 关联代码：`services/order_maintenance.py::get_redis_client`、`middleware/rate_limit.py`、
  `services/geo.py::ensure_geo_cache`、`routers/v1/public.py`、`routers/v1/orders.py::_sync_order_geo`

## 背景

Redis 承担三类职责：登录/解析频率限制、橱窗（agent board）30s 响应缓存、订单坐标 GEO 索引。
部署为单实例容器且**不设密码**（内网隔离，启用密码需牵连所有环境的 REDIS_URL，已评估排除）。
Redis 宕机不应打断主业务。

## 决策

1. **可用性分级**：MySQL 是硬依赖（不可用即 503，见 `/health`）；Redis 是软依赖——
   任何 Redis 调用失败都必须走降级路径，不允许向用户抛 5xx。
2. **降级行为逐项定义**：
   - 限流：Redis 不可用时退化为进程内滑动窗口（多 worker 下只保护单进程，注明局限）；
   - 橱窗缓存：读未命中→直接查库；写路径失效钩子（`invalidate_board_cache`）失败→
     最多展示 30s 旧数据，由 TTL 兜底；
   - GEO 索引：惰性重建（key 不存在→从 MySQL 全量重建）。空租户写 120s 短 TTL 的
     独立标记 key（`*:empty`），避免"key 永不存在→每请求全量查库"；
   - 失败一律 `logger.warning/exception` 留痕，不静默吞掉。
3. **禁止**：在业务事务里做跨 Redis 的强一致假设（无分布式事务）；
   不得因为缓存写入失败而回滚数据库写入。

## 后果

- 正向：Redis 从"必挂依赖"降级为"性能加速器"；单点故障半径只剩性能，不再是可用性。
- 代价：降级瞬间的库压力会突增（缓存击穿无互斥，靠 30s TTL + 低流量规模消化）；
  进程内限流兜底在 `--workers 2` 下阈值实际翻倍，可接受。
- 审计补充：审计日志（`services/audit.py`）写库失败同样"日志留痕不阻断"，与本文精神一致。
