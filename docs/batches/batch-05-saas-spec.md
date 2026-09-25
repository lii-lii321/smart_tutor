# Batch 05 — SaaS 化基础：Tenant / 权限 / 品牌 / 部署（施工规格书·存档）

> 存档说明：本文件由外部评审 AI 于 2026-09-25 交付（原稿 Desktop《Batch 05.docx》），
> 按《Batch 04 反馈》要求**暂缓开工**——先完成 Pilot（1-2 个真实中介试用一周），
> 收集反馈并执行 Pilot Feedback Batch 之后再按本规格分 05A-05E 五个子批施工。
> 本文件内容为原规格的忠实转换，未做增删改判。

目标版本：从"能运行的中介工作台"升级为"可以交付给不同家教中介独立使用的 SaaS 产品"。

核心原则：Batch 05 不做大规模视觉重构，不重写业务域，不碰核心订单算法，不引入支付。
本批次只解决一个问题：**如果明天有第二家、第三家家教中介来使用，这套系统能不能安全、独立、稳定地服务他们？**

## 一、最终目标

现有系统已具备：AI 批量录单 → Order → 教员推荐 → 教员投递 → 中介审核 → 试课 → 成交 → 财务。

Batch 05 后需要进一步变成：

```
Platform Owner
├── Tenant A（Admin / Staff / Orders / Teachers / Applications / Finance）
├── Tenant B（Admin / Staff / ...）
└── Tenant C
```

租户隔离必须成为真正的系统边界，而不是前端筛选。

## 二、范围（5 个模块）

- **P0** Tenant 基础模型
- **P0** 权限模型
- **P1** Tenant 工作空间
- **P1** 品牌与基础配置
- **P1** 部署与环境隔离

暂时不做：支付、微信支付、订阅计费、自动续费、SaaS 套餐、白标商城、多级代理、CRM、数据大屏、AI 自动运营、AI 异常预测、深度 BI——全部留到后续 Batch。

## 三、第一原则：不要破坏现有业务域

禁止因为 SaaS 化重写 Order/Application/Recommendation/Finance/AI Import。正确方式：

```
现有 Domain → Tenant Context → 权限过滤 → 现有业务
```

## 四、P0：Tenant 数据模型

先检查现有 Tenant / tenant_id 及 User/Tenant/Order/Application/Teacher/FinancialRecord/Notification 关联方式。**已经存在就不要重复创建。**

## 五、Tenant 隔离原则

所有 B 端数据必须：当前登录用户 → current tenant → tenant_id → 业务数据。
禁止前端传 tenant_id 作为安全依据（`GET /api/orders?tenant_id=2` 不能成为权限判断）。
后端必须从 JWT / current_user 确定 current_tenant_id 再查询 `Order.tenant_id == current_tenant_id`。

## 六、租户越权测试（必须新增）

Tenant A（order/teacher/application/finance A）vs Tenant B（…B）：A 登录不能读 B 全部资源，反之亦然。

## 七-十一、P0：权限体系

固定四角色（不要突然引入几十个）：

- **Platform Owner**：平台级管理（租户/用户/系统配置/平台健康）；可查看租户列表/状态/用户数/订单数；**不应默认进入某个 Tenant 的业务操作上下文**
- **Tenant Admin**：订单/教员/投递/审核/试课/成交/财务/AI 录单/租户配置/成员管理
- **Tenant Staff**：订单查看/录入/AI 录单/教员查看/投递审核/订单跟进；**限制**租户配置、成员管理、高级财务操作、平台设置
- **Teacher**：仅自己的资料/推荐订单/投递/申请状态/消息；绝对不能进 Tenant Admin/Staff 页面、其他教师资料、其他租户订单

## 十二-十三、前端权限统一

- 新增 `frontend/src/constants/permissions.ts`：orders.view / orders.create / orders.edit / orders.archive / applications.view / applications.review / teachers.view / finance.view / finance.manage / tenant.members.manage / tenant.settings.manage
- 新增 `frontend/src/utils/permission.ts`：hasPermission() / canAccessRoute() / canPerformAction()
- **前端权限只是 UI 层，真正权限必须由 Backend 决定**
- 禁止 `if (role === 'admin')` 大量散落

## 十四-十五、路由权限与失败行为

- 路由 meta：requiresAuth / permissions / roles（/admin/dashboard|orders|import|applications|teachers|finance|settings|members）
- 403 不能白屏：403 → 权限提示（"当前账号暂无此操作权限"）→ 返回上一页/工作台

## 十六-十八、P1：Tenant Workbench / Header / Switcher

- Workbench 不重做，只补：当前租户身份/当前用户身份/当前角色
- Header 克制：`[Logo] 成都XX家教 中介工作台`，右侧用户头像/姓名/角色；不要大型 SaaS 导航栏
- Tenant Switcher：普通用户单租户不显示；Owner 经租户管理进入租户工作区，必须明确"当前上下文 = Tenant A"防误操作

## 十九-二十三、P1：成员管理（/admin/members）

- 只解决"这个中介团队有哪些人在使用系统"；字段：姓名/手机号/角色/状态/最近登录/操作
- 操作：邀请成员/修改角色/停用/重新启用；不做组织架构/部门/岗位体系/复杂审批
- 邀请第一版：手机号/账号 + 临时邀请状态；不做 Email Invitation/Magic Link/SSO/OAuth；优先复用现有认证体系
- 停用后不能登录，但历史订单/投递/财务/操作记录不能删除

## 二十四-三十一、P1：Tenant Settings 与品牌（/admin/settings）

- 三区：基础资料（机构名称/联系人/电话/城市）、业务配置、品牌配置（Logo/机构名称/品牌色）
- 品牌色：预设色（Navy/Blue/Green/Purple）+ 高级 HEX 输入，**必须可读性检查**（禁止白字黄底）
- 架构：design-tokens.css 新增 `--tenant-brand` / `--tenant-brand-hover`；业务 UI 消费变量，禁止 `:style="{ color: tenant.color }"` 散落
- 品牌色只影响：Primary Button / Active Navigation / Links / Selected state / 部分重点状态；**不能影响 success/warning/danger**（成功永远绿、警告黄、错误红）
- Logo：PNG/JPG/SVG，大小限制，上传预览保存；无 Logo 用机构名称首字 fallback
- Teacher 端品牌：不泄露给不相关租户；是否展示机构名称沿用现有业务规则，**不自行扩大信息披露**；Tenant Branding ≠ 全站品牌污染

## 三十二-三十五、Platform Owner 页面与租户状态

- /owner/tenants 第一版只需 Tenant List：租户名称/状态/管理员/订单数量/成员数量/创建时间
- 不做 GMV/DAU/MAU/LTV/CAC/Retention/Funnel（数据量不足）
- Tenant 状态最少：active / suspended（已有状态模型则复用）
- suspended：Admin/Staff 不能进业务系统；Teacher 是否受影响必须检查现有业务模型后决定，不能直接阻断教师侧；历史订单/申请/成交不能丢失

## 三十六-四十一、P1：部署环境与日志

- dev/production 边界整理；检查 API URL/JWT secret/Database URL/Redis/AI key/AMap key 有无硬编码（禁止 `const apiKey = "xxx"`）
- Frontend：.env.development/.env.production（VITE_API_BASE_URL/VITE_APP_NAME）；DeepSeek Key/JWT Secret/DB 密码**绝不放 frontend**
- Backend：DATABASE_URL/REDIS_URL/JWT_SECRET/AI_API_KEY/AMAP_KEY 区分 required/optional
- 生产启动配置校验：缺 JWT_SECRET/DATABASE_URL 应启动失败而非运行后报错
- 结构化日志第一版：request/user/tenant/route/status/duration/error；不记录 password/JWT/AI secret/完整敏感信息

## 四十二-四十四、审计日志

- 后端已有 AuditLog（Batch 0.9 体系）——按现状核对覆盖面，SaaS 化要求至少：user_id/tenant_id/action/resource_type/resource_id/created_at
- 第一版动作：登录/登出/创建订单/修改订单/归档/重新发布/审核教员/修改成员角色/停用成员/修改 Tenant Settings/修改品牌配置；不需要记录所有 GET
- 页面：Tenant Admin /admin/audit（时间/用户/动作/对象/结果）

## 四十五、错误处理统一（继续）

401 登录失效重新登录 / 403 无权限 / 404 不存在或已删除 / 409 状态已变化请刷新 / 422 提交信息有误 / 500 稍后重试。

## 四十七、绝对禁止

❌ fake tenant / fake user / fake member count / fake audit log / fake subscription / fake billing / fake SaaS metrics。所有页面必须真实 API 或明确 empty state。

## 四十八-四十九、迁移与向后兼容

- 新增 Tenant/AuditLog/TenantSettings 必须 Alembic migration；禁止启动自动 create_all、禁止手改数据库
- 向后兼容：旧数据迁移后必须继续工作；历史数据缺 tenant_id 时推荐**创建 default tenant + 历史数据全部归属**，而不是 tenant_id=NULL 到处兼容

## 五十-五十一、目录建议

前端：components/business/tenant/（TenantSwitcher/TenantBrand/MemberTable/TenantSettingsForm/AuditLogTable）、constants/permissions.ts、utils/permission.ts、adapters/tenant.ts、views/admin/{Members,Settings,AuditLog}.vue、views/owner/Tenants.vue。**沿用现有组织方式，不为架构洁癖大规模迁移。**
后端：优先遵循现有结构（tenant/ 或 admin/），不为 Batch 05 重构整个 FastAPI 项目。

## 五十二-五十四、Tenant Context

- 后端统一 get_current_tenant()（或等价机制）；业务接口统一 current_user + current_tenant
- 禁止几十个 endpoint 重复 `if user.tenant_id: ...`
- Repository 查询原则：get_order(order_id, tenant_id)，而不是查出来再 if 判断（更容易避免越权）

## 五十五-五十八、批量/AI/财务/通知边界

- 批量接口（import/create/archive）不能绕过 Tenant：当前 tenant → 所有输入 → 统一校验
- AI Import：当前 Tenant → Orders，不能出现无 tenant 的订单
- Finance：严格绑定 tenant（经 application/order 间接确定可暂时复用，最终必须 Tenant A 不能查 B 财务）
- Notification：检查 Tenant/Teacher 通知，避免 A 的通知发给 B 的用户

## 五十九-六十、测试矩阵

- 后端：Auth（Admin/Staff/Teacher/Owner login）× Tenant isolation（A→A ✓，A→B ❌，B→A ❌）× Role × Resource（Order/Application/Teacher/Finance/Notification/Audit）
- 前端 Vitest：permission.test.ts / tenant.test.ts / workbench.test.ts——hasPermission()（admin→finance.view=true；staff→tenant.settings.manage=false；teacher→admin.dashboard=false）

## 六十一、E2E 手工验证

- Scenario A：Tenant A Admin 全流程（Workbench→Orders→Order Workspace→AI Import→Finance）
- Scenario B：Tenant B Admin 重复流程，确认 A 看不到 B
- Scenario C：Tenant Staff 能处理订单、不能管理成员/品牌
- Scenario D：Teacher 页面正常、Admin 页面不可进入

## 六十二-六十三、响应式与 AdminTabbar

375/390/768/1024/1280/1440 重点页面（Workbench/Orders/Order Workspace/Members/Settings/Audit）。AdminTabbar 不删除：768-1023 floating bottom nav / Desktop 76px sidebar / Mobile single column。

## 六十四-六十六、设计与空状态

继续 Navy+Slate+Warm Paper；禁止紫色 SaaS Dashboard/AI 渐变/玻璃拟态/大面积渐变/过多阴影/营销 Landing 风格。Settings 页面：标题+说明+分区表单，不是巨大 Dashboard 卡片。空状态：成员（"还没有团队成员，邀请第一位成员开始协作"）、审计（"暂无操作记录"）、Logo（机构名称默认标识）。

## 六十七-六十八、技术栈纪律

❌ Element Plus / Ant Design Vue / Naive UI。继续 Vue3+TS+Vant+Tailwind+现有 App* 组件；不重写 AppCard/AppButton/design-tokens。

## 六十九-七十一、Batch 04/05 关系与 Billing

- Batch 04 = Business Workflow（中介怎么工作）；Batch 05 = SaaS Boundary（不同中介怎么安全使用同一系统），不混做
- Batch 05 明确不做：Subscription/Billing/Payment/Invoice/Auto renewal——现在要验证的是"一个中介能不能持续使用"，不是"怎么向他收费"

## 七十二-七十三、完成标准与验收汇报

最终形态：Platform → Tenant A/B（Admin/Staff/Data 完全隔离）+ Owner；数据完全隔离、权限明确、品牌可配置、审计可追溯、部署可生产化。

汇报必须含：①修改文件列表 ②新增文件 ③删除文件 ④Backend changes ⑤Database migrations ⑥Tenant isolation implementation ⑦Permission matrix ⑧Audit implementation ⑨Brand implementation ⑩Environment changes ⑪Test results ⑫Manual E2E results ⑬Remaining limitations ⑭Commit hash

## 七十四-七十六、门禁与 Git 纪律

- 五门全过：typecheck/lint/build/test/pytest（沿用项目现有命令）
- **不建巨型 commit**，严格顺序：05A Tenant 数据边界 → 测试 → 05B Permission → 测试 → 05C Members → 测试 → 05D Settings/Branding → 测试 → 05E Audit/Production hardening → 完整回归

## 七十七、完成后的产品形态

"面向家教中介机构的多租户智能订单工作台 SaaS"。最不能妥协的是 **Tenant Isolation**——卖给多个中介后，这部分做错的代价远大于按钮样式/Dashboard/AI 功能。

> 执行前提（重申）：Pilot（1-2 个真实中介试用）反馈收集完成后，按 Pilot Feedback 修正真正影响使用的问题，再进入 05A。
