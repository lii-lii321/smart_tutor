# 轻薄版橱窗（Lite）：独立免登录看单入口

## Context

产品方向再砍一刀：教员端只需要一个"图形化看单窗口"——地图+列表浏览、筛选、点开看详情、一键复制中介微信线下联系。投递/资金/登录全部不要，现有老版本一行行为不动。三个已定决策：**独立入口**（同仓同部署，不碰老页面）、**转化=复制中介微信**、**完全免登录**（偏好存 localStorage）。

探索结论：积木八成现成——`useAMap`/`utils/amap.ts`（地图全生命周期）、`useBoardFilters`（学段/学科/城市筛选+三种排序，纯逻辑零副作用）、`clipboard.ts`（含 HTTP execCommand 回退，适配裸 IP 部署）、`ui/*` 组件、design tokens、`publicApi.getBoard`（免登录脱敏地图数据）。后端唯一缺口：公开订单详情端点（board 只有 Marker 轻字段，且 `order_detail_payload` 对 `requirements` 不掩码，不能直接复用到免登录场景）。

## 后端（3 处修改 + 1 新文件）

### 1. `services/serializers.py` — 新增 `order_public_detail_payload(order, contact_wechat)`
白名单模式（沿用 `order_board_payload` 的"始终脱敏"注释约定），输出：`id / grade_subject / price_total / **money_fields / weekly_frequency / fuzzy_address / subway_remark / 粗化lng,lat / created_at / requirements(过 mask_contact_info) / raw_text(过 mask_contact_info) / contact_wechat`。**不含** raw_id / status / expired_at / exact_address / parent_phone。复用现成的 `money_fields`、`teacher_brief_fields`（坐标粗化）、`mask_contact_info`。

### 2. `models/schemas.py` — 新增 `PublicOrderDetail(BaseModel)`
字段与 payload 白名单一一对应，放在 OrderBrief/AgentBoardResponse 附近。

### 3. `routers/v1/public.py` — 新增端点（增量，不动 board）
`GET /api/v1/public/agent/{invite_code}/orders/{order_id}` → `PublicOrderDetail`。
- 租户：`invite_code` 查找 + `is_active`，404 文案同 board（"中介不存在或邀请码无效"）
- 订单：`tenant_id == tenant.id AND status == recruiting AND expired_at > utcnow()`，否则 404（"订单不存在或已下架"）
- 自动继承 router 级 `check_public_rate_limit`（120/min/IP）+ nginx `public_api` 限流
- v1 不加 Redis 缓存：主键单查很便宜，且订单级 key 不在现有 `invalidate_board_cache(tenant_ids)` 失效钩子覆盖内——宁可不缓存也不引入脏读风险

### 4. `tests/test_public_order_detail.py` — 新建（仿 test_teacher_scorecard.py 结构）
conftest 工厂造数（`make_tenant`/`make_order`，订单对象上直接补 requirements/parent_phone 测试数据），用例：
- 免登录 200：`raw_text` 中手机号已打码、requirements 中手机号已打码、响应 JSON **不含** `parent_phone/exact_address/raw_id/status` 键（负向断言，同 test_router_shapes 风格）、坐标已粗化、`contact_wechat` 在
- 404 矩阵：错邀请码 / 停用中介 / 归档单 / 过期单 / 他租户订单 id

## 前端（独立目录，全部新增）

### 新文件
```
frontend/lite.html                          # 复制 index.html 骨架（viewport-fit=cover、theme-color、vant 主色兜底内联样式），title「智派家教·极速看单」，入口 /src/lite/main.ts
frontend/src/lite/main.ts                   # createApp(LiteApp) + import "@/styles/main.css"；无 pinia、无 router
frontend/src/lite/api.ts                    # import client from "@/api/client"，getBoard + getPublicOrderDetail + 手写 TS 类型（不动共享 api 文件）
frontend/src/lite/composables/useLiteBoard.ts  # 薄胶水：publicApi 拉取、useBoardFilters 实例、距离装饰、localStorage 持久化
frontend/src/lite/LiteApp.vue               # 单页根：顶栏（中介名+地图/列表切换）→ 工具栏（筛选按钮+排序）→ 地图/列表 → 详情弹层
frontend/src/lite/components/LiteOrderCard.vue      # 列表卡片：科目/课酬/频次/模糊地址+地铁备注/信息费
frontend/src/lite/components/LiteFilterSheet.vue    # 筛选底部弹层：学段/学科/城市/排序 chips（逻辑全来自 useBoardFilters）
frontend/src/lite/components/LiteOrderSheet.vue     # 详情弹层：掩码原文+要求文本块、费用三分（信息费/定金/尾款）、CTA「复制中介微信」(copyContact)
frontend/tests/liteBoard.spec.ts            # vitest：距离装饰纯函数 + localStorage 读写容错（坏 JSON 重置）
```

### 关键实现点
- **邀请码解析**：`location.pathname` 的 `/lite/{code}`（生产）> query `?inv=` > hash（开发态用 `lite.html#/code`，因 vite dev 的 SPA fallback 会把 /lite/x 落回旧 index.html）> 复用 `resolveInviteCode()` 兜底链
- **距离排序**：免登录无 `distance_km`，lite 用 `useBoardFilters` 导出的 `haversineKm` 给每单装饰距离（参照点：浏览器定位 `locateUser()` → 选中城市中心 → null 沉底）；排序复用 `sortOrders` 现成逻辑。默认排序「最新发布」，定位成功后自动切「距离优先」
- **降级路径**：board 拉取失败→AppEmpty+重试；空单→空态；地理定位拒绝→距离列隐藏；localStorage 坏 JSON→重置默认
- **硬边界**：lite 只调 `/public/*` 两个端点，绝不触发 client.ts 的 401 登录跳转（游客态红线）

### 仅有的 2 处配置修改（增量）
- `frontend/vite.config.ts`：`build.rollupOptions` 加 `input: { main, lite }`（MPA 唯一必改点；manualChunks/plugins/tailwind content 对 src/lite 自动生效）
- `deploy/nginx.conf`：加一条增量 location：`location /lite { try_files $uri /lite.html; }`（旧 SPA 路由不受影响）

### 测试增量
- `frontend/e2e/smoke.spec.ts` 加 1 个 lite 冒烟用例（增量，不动旧用例）：`goto("/lite.html#/tx886")` → 断言页面标题/地图容器/列表卡片渲染
- 中介分发链接形态：`{origin}/lite/{inviteCode}`（后台 Settings 加 lite 链接按钮属老文件改动，**本版不做**，作为后续可选项）

## 明确不做（本版范围外）
登录/订阅推送/AI 推荐（推荐降级为距离+筛选规则排序）、投递入口、老版本任何页面或行为变更、独立部署/子域名。

## 验证

1. 后端：`pytest tests/test_public_order_detail.py` → 全量 pytest（基线 334+新增）→ ruff → mypy（0 错基线）
2. 前端：`npm run build`（vue-tsc 同时检查两个入口）→ lint → check:tokens → vitest
3. e2e：`npm run test:e2e`（11 旧 + 1 新 lite 冒烟）
4. 本地手动：起 dev 服务，`http://localhost:5173/lite.html#/tx886` 走一遍 地图↔列表切换、筛选、详情、复制微信（HTTP 回退路径）
5. 部署：沿用 tar+scp+build 发版序列（2G 机先停 api/scheduler），上线后验证 `http://47.108.14.88:8080/lite/nit2026` 与夜测回归