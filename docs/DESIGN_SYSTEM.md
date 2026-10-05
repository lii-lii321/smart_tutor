# Smart Tutor 设计系统（Design System v1 文档化）

> 定位：本文档**不引入新视觉方向**。Smart Tutor 已有一套经过实机验收的 UI 2.0 体系（白纸 + 墨黑胶囊 + 明黄记忆点，2026-10-02 全量落地），唯一视觉来源是 `frontend/src/styles/design-tokens.css`。本文档做三件事：
> 1. 把现有体系**文档化**成可查阅的规范（含组件规格与用法规则）；
> 2. 补齐现有体系缺失的地基（字阶 token、触控目标、focus 全局化、校验规范）；
> 3. 立治理规则，防止多页面开发把系统拆散。
>
> 上游依据：`docs/ui-2.0-handoff.md`（UI 2.0 执行说明书）、`docs/adr/0006`（设计系统 Token 架构）、`docs/UI_UX_AUDIT.md`（现状审计）。
> 实施项在 `docs/UI_UX_IMPLEMENTATION_PLAN.md` 中排期，本文档描述的是**目标态规范**。

---

## 0. 产品基调（设计决策的元规则）

**B 端走 Convention Track（成熟工具型 SaaS 语言），C 端走事务型工具 + 品牌记忆点。**

| 拨盘 | 设定 | 依据 |
|---|---|---|
| Energy（静↔吵） | 静。动效只做反馈，不做表演 | 财务/撮合是严肃场景 |
| Finish（糙↔精） | 精但克制。圆角/阴影只用 token 档位 | UI 2.0 已验收 |
| Density（疏↔密） | **密（7-9/10）**。高信息密度 + 低认知负担 | B 端表格 7 列、审核页分栏已是此形态 |
| Weight（轻↔重） | 中。墨黑胶囊承载动作重量，明黄只点缀 | brand-800 位=墨黑是拍板决策 |
| Seriousness（玩↔庄） | 庄。emoji 仅限空态插画位，正文禁用 | 现有 AppEmpty 惯例 |

**反 AI 通用脸红线**（30 秒扫描项，任何新页面自查）：
无紫黑底、无紫蓝渐变按钮/文字、无玻璃拟态与发光描边、无 backdrop-blur（黑闪硬规矩）、无全屏黑遮罩、无装饰性 KPI 大数字/图表大屏、无假数据（demo 必须像真单：非整数金额、真实城市/学科）。AI 紫只准出现在 AI 功能语境（`--st-ai` 族），禁做全局主色。

**每屏一个焦点**：每个页面/弹层只允许一个视觉锚点（工作台=行动队列首行、财务=净收入数、导入=输入区）。次级信息一律 muted，不与锚点竞争。

---

## 1. 色彩（Color Tokens）

单一来源 `design-tokens.css`，Tailwind 语义类经 `-rgb` 三元组消费（保透明度修饰符）。**改 hex 必须成对改 `-rgb`；新增变量必须建伴生 `-rgb`**（check-tokens 护栏拦截裸写 Tailwind 内置色）。

### 1.1 核心三色

| Token | 值 | 语义 | 硬规则 |
|---|---|---|---|
| `ink` | `#1c1c1e` | **动作色**：主 CTA、激活态、深色块 | 白字压 ink 17:1 |
| `accent` | `#ffd02f` | **品牌记忆点**：Logo/推荐位/强调卡/待办 badge | **永不做白字底**；文字用 `accent-ink`（压 accent-soft 5.8:1）；面积 ≤10%/屏 |
| `link` | `#4262ff` | 链接、次级强调、浅色 tint 承载（ghost hover/选中底/步骤条） | 压白底 4.8:1（AA） |

brand-50~700 浅蓝阶是 tint 承载位（选中底、步骤条、标签底）；**brand-800/900 已让位给墨黑**（主 CTA 语义），不要再用 brand-800 表达「蓝色品牌」。

### 1.2 表面与文字

| 用途 | Token |
|---|---|
| 页面底 | `page`（= paper `#f7f8fa` 冷白纸灰；warm `#f3eee8` 为存量点缀保留） |
| 卡片面 / 弱化面 | `surface` / `surface-soft` |
| 文字 主/次/弱/禁用 | `text-primary` / `text-secondary` / `text-muted` / `text-disabled` |
| 描边 常规/强调 | `border-default` / `border-strong` |

### 1.3 状态色（statusTone 体系，全项目唯一口径）

4 色族（success/warning/danger/info）× 4 档，**程度差异用档位表达，禁止为新状态单开色相**。配色唯一出口 `constants/statusTone.ts`，任何视图不得手写状态色。

| 档位 | 用途 | 搭配 |
|---|---|---|
| soft | chip 浅底 | deep 文字 |
| mid | chip 中底（推进中） | deep 文字 |
| DEFAULT | 图标/进度填充/色块 | **禁做文字色、禁配白字**（对比不足，token 注释已实测） |
| deep | chip 文字 / 实心徽标底 | 实心底配白字 |

**实心白字纪律**：仅 `success-deep` / `danger` / 各 deep 档；`accent` 与 `warning` 一律浅底深字。
**财务三色口径**：收入 `+`绿 / 退款 `−`红 / 没收琥珀不计净额——一律带符号或前缀，不单靠颜色。

### 1.4 AI 紫

`--st-ai` `#8b7cf6` 族：仅限 AI 解析/智能推荐/AI 状态（导入步指示、解析中脉冲、分诊标签）。置信度一律定性表达（高置信/中置信/AI 补全），**绝不显示数值百分比**。

---

## 2. 字体排印（Typography）—— 本系统最需要补的地基

**现状**：无 font-size token，228 处 `text-[Npx]` 任意值、最小 9px（审计 VH-1/A11Y-2）。

### 2.1 字阶 token（目标态，新增到 design-tokens.css 并映射 Tailwind fontSize）

| Token | 值/行高 | Tailwind 类 | 用途 |
|---|---|---|---|
| `--st-text-caption` | 11px / 16 | `text-caption` | 徽标、时间戳、表格表头（**全站字号下限**） |
| `--st-text-body-sm` | 12px / 18 | `text-body-sm` | 辅助信息、卡片元数据 |
| `--st-text-body` | 14px / 22 | `text-body` | 正文默认 |
| `--st-text-emphasis` | 16px / 24 | `text-emphasis` | 卡片标题、重点字段 |
| `--st-text-title` | 18px / 26 | `text-title` | 区块标题、订单卡时薪（账本基线位） |
| `--st-text-headline` | 20px / 28 | `text-headline` | 页面标题（H5 NavBar 之下）/账本日金额 |
| `--st-text-display` | 24px+ / 32 | `text-display` | 每屏唯一锚点大数（财务净收入 32px 属此级） |

规则：
- 一屏内字阶 ≤4 级（不含 display）；**9px/10px 立即灭绝，11px 是底线**。
- 金额、计数、时间列一律 `tabular-nums`；大数配小单位（数值大字号+单位 body-sm）。
- 字重四档：400 正文 / 500 标签与 chip / 600 副标题按钮 / 700 页面标题与锚点数。禁用 >700 与 <400。
- 账本/财务页维持 18/20px 基线（既有拍板），对应 title/headline 位。
- 迁移策略：新增 token 后，**改到哪个页面才替换哪个页面的任意值**，不做一次性全库替换（避免无意义大 diff）；但 9/10px 与新页面必须立即用 token。

### 2.2 中文字排印注意

行长：正文容器移动端全宽、桌面 ≤720px（工作台 max-w-3xl 即此意图）；行高禁 <1.4（正文）；标题行高 1.2 左右。

---

## 3. 间距与栅格

- 4/8px 栅格；常用档：4 / 8 / 12 / 16 / 20 / 24 / 32。
- **卡内边距 < 卡片间距**（防「卡片融成一坨」）；列表项间距 ≥8px。
- 容器：H5 内容 `max-w-2xl` 居中；admin 工作台 `max-w-3xl`；宽表（订单/财务/审核分栏）自适应至 `--st-content-max-width: 1440px`；AdminShell 侧栏 `--st-sidebar-width: 240px`。
- 页面纵向节奏：NavBar → 页头（标题+副文案）→ 首区块，区块间距 16-24px，禁为「高级感」放大留白。

---

## 4. 圆角、阴影与容器

### 4.1 圆角（Tailwind 全局覆写已消费 token）

| Token | 值 | 用途 |
|---|---|---|
| `radius-sm` | 6px | 小件（chip 内嵌块） |
| `radius-md` | 12px（rounded-xl） | 输入框、小卡 |
| `radius-lg` | 16px（rounded-2xl） | 标准卡（`.st-card` 默认） |
| `radius-xl` | 28px（rounded-3xl） | 强调卡/品牌时刻，仅点缀 |
| 胶囊 | rounded-full | **所有按钮**、chips、分段器、tabbar 激活块 |

嵌套圆角公式：内圆角 = 外圆角 − 内边距（16px 卡内放 12px 输入框）。圆角卡禁彩色顶边条。

### 4.2 阴影与容器四选一

| Token | 值 | 用途 |
|---|---|---|
| `shadow-sm`（boxShadow.card） | `0 1px 2px + 0 8px 24px @0.035` | 卡片默认 |
| `shadow-md` | `0 4px 12px @0.06` | 悬浮胶囊 tabbar 之下的过渡层 |
| `shadow-lg`（elevated） | `0 12px 30px @0.1` | 浮层（下拉、抽屉） |

**容器四选一，绝不叠加**：阴影（默认）/ 1px 描边（数据密集表）/ 无容器 / 背景色位移。同一元素禁 border+shadow+背景+徽章齐上。

---

## 5. 组件规范

> 基础件在 `components/ui/`，跨页视觉基类在 `styles/components.css`（`.st-card` / `.st-chip` / `.st-focus` / `.st-spinner`）。业务组件禁发请求（`components/business/README.md` 架构约定）。**扩展现有组件，禁止另起炉灶**——尤其 Order/Timeline/Recommendation/Financial/Todo/Status/Batch 域。

### 5.1 Button（AppButton，6 variant × 3 size，全胶囊）

| Variant | 形态 | 层级 |
|---|---|---|
| `primary` | 墨黑底白字 | **Primary**：每屏至多 1 个主 CTA |
| `accent` | 明黄底 ink 字 | Primary 的品牌时刻变体（立即投递/一键匹配），不与 primary 同屏竞争 |
| `secondary` | 白底描边 | **Secondary**：并列次动作 |
| `ghost` / `text` | 透明/文字 | **Tertiary**：入口、行内操作 |
| `danger` | 红底白字 | 破坏性动作（须配 appConfirm 确认） |

尺寸：sm 32px（桌面紧凑表格内）/ md 40px（默认）/ lg 48px（H5 主 CTA）。
**触控目标规则（新增）**：移动端可点目标 ≥44×44px；确实放不下 44px 的行内次级按钮 ≥32px 且与相邻目标间距 ≥8px（间距可计入热区，用 padding 扩热区而非 margin）；`py-1` 这类 26-28px 裸按钮禁止新增。
交互态：hover/active/disabled/loading/focus 已内建（`.st-focus` + `st-spinner` + disabled:opacity-40）；按钮文案 = 动词 + 宾语（「去审核投递」「导出 CSV」），禁「确定/提交/OK」；破坏性按钮点名对象（「归档此订单」）。

### 5.2 Input / Select / Form

- 载体：Vant field（`--van-*` 已映射 token），高 ≥40px（移动 ≥44px）。
- **校验规范（新增，Login.vue 为仓内范本）**：
  1. 必填字段可见标记（星标或「必填」chip）；AI 导入类分诊场景可用分诊标签替代星标；
  2. blur 时校验，不打断输入；提交时全量校验并**自动聚焦第一个非法字段**；
  3. 错误显示在字段下方（`:error-message`），禁只弹 toast；
  4. 错误文案 = 哪个字段 + 为什么 + 怎么改（「课酬低于最低定金 ¥100，请调整课酬或清空价格改为待定价」是范本）；
  5. 提交中按钮 loading + 防重（`useAsyncAction`）。
- 裸数字经纬度输入这类「机器字段」不得直接暴露给人填（审计 FM-2）。

### 5.3 Table（B 端桌面）

- 表头：caption 字号 + text-muted + 不换行；行垂直 padding ≥12px（整行 ≥44px）；分隔线或斑马纹二选一，不同时用。
- 数字列右对齐 + tabular-nums；金额列用财务三色口径；文本列左对齐截断（truncate + min-w-0，禁硬编码列宽魔法数）。
- 行内操作 ghost/text 按钮，批量模式下禁用（现有 `:disabled="batchMode"` 惯例）。
- 移动端一律退化为卡片（现有 OrdersList 双形态为范本），表格不横滚。

### 5.4 Card

- 基底 `.st-card`（16px 圆角 + shadow-sm + 1px border）；可点卡加 `.st-card--interactive`（active 缩放 0.99、hover 升阴影）。
- 卡内禁套卡（层级用分隔线或 surface-soft 分区表达）；卡内边距 12-16px（移动）。
- 订单卡铁律：时薪/金额是第一眼信息（title 位 18px 前置），元数据 body-sm 灰字在后。

### 5.5 Badge / Status

- 三层：`.st-chip`（形态基准 11px）→ `AppBadge`（七 tone 通用）→ `AppStatusBadge`（订单状态，读 statusTone）。
- **状态 = 色 + 文字**，永不只靠颜色；进度语义用档位（soft→mid→solid，投递定金/尾款/成交是范本）。
- 新状态接入：只改 `constants/statusTone.ts`，色相只能落在现有 4 族。
- 看板列头、地图标记等非 chip 场景也须复用同款色与文字（不允许色点-only）。

### 5.6 Modal / Confirm / Drawer / Tooltip

- **确认弹层唯一口径 `appConfirm()`（App.vue 全局挂载）**：底部弹层、按钮上下堆叠（物理防并排误触）、危险红底、遮罩必淡入。禁再引入 `showConfirmDialog` 或自写确认 UI。
- 内容型弹层用 Vant popup（圆角随 token）；右侧抽屉/底部抽屉按 Vant 惯例；禁 backdrop-blur。
- **Tooltip 规则（新增）**：触屏可达路径上的关键信息禁止 hover-only（审计 IH-2）；hover 提示只允许承载增强信息；桌面 hover 提示须有 Esc/点击外关闭。
- 弹层文案：标题点明对象 + 正文说后果 + 按钮动词化（「归档后订单将不在橱窗展示」范本）。

### 5.7 Toast / Feedback

- 载体 Vant toast，**皮肤全局唯一**（顶部深色胶囊；main.css 中的白底胶囊规则为换肤遗留，须二选一清理）。
- 时长 3-5s；成功 toast 带计数（「已更新 3 条订单」）；**可逆操作的结果 toast 是放置「撤销」的位置（远期，见 OB）**。
- 错误 toast 不承载唯一错误信息（配合字段下错误/页面错误态），文案走三段式。

### 5.8 Empty State

- 唯一口径 `AppEmpty`（图标+标题+描述+action slot）；**空态 = 现状简述 + 价值一句 + 行动按钮**（「还没有订单。粘贴微信文本，AI 自动解析成可上架订单 → 去批量录单」是范本）。禁「暂无数据」裸文案；禁各页手写空态。

### 5.9 Loading（反馈阶梯）

| 延迟 | 反馈 |
|---|---|
| <400ms | 不需要任何指示 |
| 400ms-1s | 按钮内 `st-spinner` 或行内 spinner |
| 1-10s | **骨架屏**（与最终内容同构，现有 OrdersList/审核页形态） |
| >10s（AI 解析类） | 明确预期文案 + 阶段说明（「通常需要 10~30 秒」范本），**禁伪造分段进度** |

硬规矩：**禁全屏黑遮罩**（Board.vue:886 为现存违例待清）；刷新时保留旧内容渲染（「旧内容 + 局部指示」优于白屏转圈）；失败不清空已展示内容。

### 5.10 Error State

- 页面级错误态 = 说明 + 重试按钮（保留结构）；操作级错误 = toast/字段错误；409 = 「状态已更新，请刷新后继续操作」口径。
- 错误文案三段式：发生了什么 + 为什么 + 怎么办。禁「失败」「Error」裸词。
- 部分成功必须分解报告（成功 N / 跳过 K + 名单 + 重试），BatchImport 结果页为全站范本。

---

## 6. 层级系统（Primary / Secondary / Tertiary）

| 层级 | 动作 | 信息 | 视觉 |
|---|---|---|---|
| Primary | 每屏 1 个主 CTA（primary/accent 按钮、状态机产出的「去审核投递」） | 页面锚点（行动队列首行、净收入数、时薪） | ink 胶囊 / display 字阶 / 明黄点缀 |
| Secondary | 并列次动作（secondary 按钮、「编辑订单信息」） | 区块标题、卡片标题 | title/emphasis 字阶 / 白底描边 |
| Tertiary | 行内操作、入口（ghost/text、整卡可点+chevron） | 元数据、说明、原文存档 | body-sm 及以下 / muted 色 / 无容器 |

判定口诀：**「用户现在必须做的」才是 Primary；其余一律降级**。批量操作条出现时它是当屏 Primary，行内按钮让位（现有 batchMode 禁用逻辑）。

---

## 7. 响应式规则

- **移动与桌面布局各自最优**，不是简单缩放（筛选行两行化、财务账本/六列表、订单卡片/七列表是三个既定范本）。
- 断点：H5 以 640px 为宽屏档（抽屉转浮窗）；admin 以 **1024px 为壳切换档**（AdminShell 侧栏 ↔ AdminTabbar，≥1024px 隐藏 van-nav-bar）；断点常量暂不新建文件，沿用现有 `lg:` 惯例。
- 固定元素让位：内容区为悬浮 tabbar 留 `pb-24`；`safe-bottom` 消费安全区。
- H5 容器 `max-w-2xl` 居中；触控目标见 §5.1。

---

## 8. 动效

| 类型 | 时长 | 规则 |
|---|---|---|
| 按压反馈 | 80-150ms | 卡片 scale 0.99 / 按钮 active 态（已有） |
| 颜色/hover 过渡 | 150-200ms | transition-colors |
| 弹层进出 | 200-300ms | 遮罩必淡入（黑闪硬规矩）；移动进来方向 = 底部/右侧 |
| 卡片悬浮 | 180ms | 仅阴影与描边变化，禁位移引起 layout shift |

硬规则：只动画 `transform`/`opacity`；禁 `transition: all`；列表不做逐项 stagger；仪表盘/工作台禁进场 reveal 动画；实现 `prefers-reduced-motion` 时全局降级（待补，P2）。

---

## 9. 文案规范（Honest Copy）

1. 按钮 = 动词+宾语；破坏性按钮点名对象与后果。
2. 错误 = 三段式；空态 = 简述+价值+行动；AI 置信度只定性不报百分比。
3. 状态词表以 `constants/orderStatus.ts` / `applicationStatus.ts` 为唯一来源，UI 不得自造状态名。
4. 数据必须真实：演示数据用非整数金额、真实城市学科；禁 Lorem/占位名/整十整百假指标。
5. 术语全站统一：教员（不混用「老师/教师」UI 文案）、投递（不混用「申请」）、归档/重新发布成对出现。

---

## 10. 治理（Governance）

1. **护栏**：`node scripts/check-tokens.mjs`（禁裸写 Tailwind 内置色）进开发习惯与 CI；改色必配 `-rgb`。
2. **新增 token 流程**：先查 design-tokens.css 是否已有语义近邻 → 确无 → 加变量 + `-rgb` + 用途注释 + 对比度实测值 → 更新本文档。
3. **新组件准入**：先搜 `components/ui`、`components/business`、`components.css` 是否可扩展；business 组件禁发请求；消灭重复组件以 NotificationList 合并为范本。
4. **九态自查表**（新页面/新组件交付前逐项勾选）：default / hover / focus-visible / active / disabled / loading（骨架优先） / empty（AppEmpty） / error（三段式+重试） / 部分成功（分解报告）。
5. **走查 SOP**（改版页面合入前）：375 / 768 / 1024 / 1440 四档截图 → 主流程键盘 Tab 走一遍 → 检查触控目标与字号下限 → `npm run build` + `check:tokens` → 三角色核心流手测。

---

## 附：现状与目标态差异清单（本文档新增规范 ↔ 现状）

| 规范 | 现状 | 差距 |
|---|---|---|
| 字阶 token（§2.1） | 无，228 处任意值 | **需新增**（P0） |
| 触控目标（§5.1） | 无约束，存在 26-28px 按钮 | **需整改**（P0） |
| 校验规范（§5.2） | 仅 Login 内联错误 | **需推广**（P1） |
| toast 皮肤唯一（§5.7） | 两套并存 | 需清理（P1） |
| focus-visible（§5.1） | 仅 AppButton | 需全局化（P1） |
| 全屏遮罩禁令（§5.9） | Board.vue 残留一处 | 需清理（P1） |
| 其余章节 | 已是现状规范 | 文档化即可 |
