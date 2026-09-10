# ADR-0002: 家长联系方式脱敏与 address-unlock 解锁卡点

- 状态：已采纳
- 日期：2026-09-06（成文 2026-09-10，追溯既有决策）
- 关联代码：`routers/v1/orders.py`（`_build_order_detail(include_sensitive=)`、
  `/orders/{id}/address-unlock`）、`services/serializers.py::order_fields(sensitive=)`

## 背景

订单含两类敏感数据：家长手机号（`parent_phone`）与真实门牌（`exact_address`），
`raw_text` 原文里也常带手机号。平台一边连接家长与教员，若 C 端可直接拿到联系方式，
中介的撮合价值归零，且家长隐私直接暴露给所有教员。

## 决策

1. **序列化单点脱敏**：`services/serializers.py::order_fields(order, sensitive=)` 是唯一的
   字段映射出口。`sensitive=False`（教员视角）时：`parent_phone`/`exact_address` 输出 None，
   `raw_text` 中手机号强制掩码为 `138****5678` 形态，坐标做粗化（coarse_coordinate）。
   B 端（tenant_admin/super_admin 且租户匹配）才允许 `sensitive=True`。
2. **解锁卡点**：教员获取家长联系方式唯一入口是
   `GET /orders/{id}/address-unlock`，服务端校验：
   该教员在此订单上的投递处于 `trial_in_progress`（即已付定金并开始试课）。
   候选/未投递一律 403。解锁不改变数据可见性，只是按次放行读取。
3. **修复原则**：任何新的订单输出路径（列表、推荐、橱窗）必须走 serializers 单点，
   禁止在视图内手写字段映射（P1-3 已把四处重复收敛为一）。

## 后果

- 正向：隐私泄露面收敛到一个函数 + 一个卡点端点，契约测试
  （`tests/test_serializers.py`、`tests/test_regressions.py::test_order_detail_masks_teacher_view`）锁定行为。
- 代价：中介自己也不经 API 读敏感字段之外的场景（如导出）需要注意
  ——当前 CSV 导出仅 B 端可用且包含家长信息，依赖租户鉴权保护。
- 未决：家长电话/地址的静态加密（AES-GCM）另需 ADR（PLAN P2-7），本文只约束可见性不约束存储。
