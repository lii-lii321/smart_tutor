# SmartTutor UI 2.0 改造说明书（v2 —— 已对照真实代码修订，可直接执行）

> 设计稿：https://ardot.tencent.com/file/732104549149101 （6 块画板：方案总览 / 设计系统 / 教员端 H5 ×2 / 中介后台 ×2）
> 本文档是唯一执行依据。目标：把现有「清新蓝工具风」升级为「白纸底 + 黑胶囊 CTA + 明黄品牌记忆点」，**不改动任何业务逻辑、路由、API 与权限流程**。
>
> **v2 修订记录（2026-10-02，对照代码逐项核实后）**：
> 1. Tailwind 语义色消费的是 `--st-*-rgb` 三元组（`tailwind.config.js` 的 `token()`），所有改色 hex 必须配对改 `-rgb`，新增变量必须建 `-rgb` 伴生变量；
> 2. 补上 brand-50~400 浅色阶映射（源码 48 处引用，原稿漏掉会导致旧蓝残留）；
> 3. info-deep / success-deep 按仓库 WCAG 矩阵压深（原稿数值 mid+deep 跌破 4.5:1 红线）；
> 4. 状态徽标改动落到 `constants/statusTone.ts`（AppStatusBadge 只是消费者），状态词表对齐真实枚举（recruiting/trial_in_progress/completed/archived）；
> 5. 修正文件路径（.st-focus 在 components.css；TeacherTabbar/AdminTabbar 在 components/ 根目录）与无效 Tailwind 语法（`text-[--st-ink]` → `text-ink`）。

## 0. 执行纪律（先读）

1. **按 Phase 顺序执行**，每个 Phase 一次独立提交，提交前跑 `cd frontend && npm run build` 确认零报错。
2. **禁止裸写 hex**：页面/组件只允许消费 `--st-*` 变量或 Tailwind 语义类（现有规则，见 design-tokens.css 头注释与 scripts/check-tokens.mjs）。
3. **保留全部现有 `--st-*` 变量名**，页面引用一行不改；本次只改值 + 新增少量变量。这样迁移是"换肤"而不是"翻新"。**改 hex 必须同步改同名 `-rgb` 三元组。**
4. 禁止引入新依赖、新 UI 库；Vant 组件继续用，通过现有 `--van-*` 映射自动跟随换肤。
5. 涉及 auth、订单状态机、金额计算的文件（`stores/`、`api/`、`services/`）一律不碰。
6. `scripts/check-tokens.mjs` 只拦 Tailwind 内置色系（bg-blue-500 之类），新增语义类（ink/accent/link）不会被拦，**无需改护栏**（已核实）。

---

## Phase 1 — Design Tokens 换肤（只改 `frontend/src/styles/design-tokens.css` + `styles/components.css` 一处）

### 1.1 新增变量（加在 `:root` 品牌区，hex 与 `-rgb` 成对）

```css
/* UI 2.0：墨黑主 CTA + 明黄品牌点缀（设计稿 02 设计系统画板） */
--st-ink: #1c1c1e;            --st-ink-rgb: 28 28 30;
--st-ink-soft: #2c2c34;       --st-ink-soft-rgb: 44 44 52;
--st-accent: #ffd02f;         --st-accent-rgb: 255 208 47;
--st-accent-deep: #fcb900;    --st-accent-deep-rgb: 252 185 0;
--st-accent-soft: #fff8e0;    --st-accent-soft-rgb: 255 248 224;
--st-accent-ink: #746019;     --st-accent-ink-rgb: 116 96 25;
--st-link: #4262ff;           --st-link-rgb: 66 98 255;
```

对比度实测：ink 上白字 17:1；ink 压 accent 11.6:1；accent-ink 压 accent-soft 5.8:1；link 压白底 4.75:1（AA 达标）。

### 1.2 修改现有变量值（变量名不动，hex 与 `-rgb` 成对改）

| 变量 | 旧值 | 新值 | 说明 |
|---|---|---|---|
| `--st-paper` | `#faf9f7` / `250 249 247` | `#f7f8fa` / `247 248 250` | 页面底色改冷一档白纸灰（`--st-page` 引用 paper，自动跟随） |
| `--st-brand-50` | `#eaf1f7` / `234 241 247` | `#eef1fe` / `238 241 254` | 浅蓝阶整体向品牌蓝 #4262ff 靠拢（ghost hover/选中底/标签底 48 处引用的承载） |
| `--st-brand-100` | `#d8e5f0` / `216 229 240` | `#e0e5ff` / `224 229 255` | |
| `--st-brand-200` | `#b7cee4` / `183 206 228` | `#c4ceff` / `196 206 255` | |
| `--st-brand-300` | `#8db1d3` / `141 177 211` | `#9dafff` / `157 175 255` | 步骤条连接线 |
| `--st-brand-400` | `#5c8cc0` / `92 140 192` | `#7186ff` / `113 134 255` | |
| `--st-brand-500` | `#4a80b5` / `74 128 181` | `#4262ff` / `66 98 255` | 品牌蓝（= link，focus 描边/进度填充） |
| `--st-brand-600` | `#3b6da3` / `59 109 163` | `#2a41b6` / `42 65 182` | |
| `--st-brand-700` | `#2f5c8c` / `47 92 140` | `#2a41b6` / `42 65 182` | pressed；白字 8.3:1，压 brand-50 7.4:1 |
| `--st-brand-800` | `#2f4f7a` / `47 79 122` | `#1c1c1e` / `28 28 30` | **关键**：原「主品牌色」位让位给墨黑，Vant 主色跟随 |
| `--st-brand-900` | `#26496e` / `38 73 110` | `#1c1c1e` / `28 28 30` | |
| `--st-info-soft` | `#eaf1f7` / `234 241 247` | `#c3faf5` / `195 250 245` | 薄荷浅底（「招聘中」chip 同族） |
| `--st-info-mid` | `#c6d9ec` / `198 217 236` | `#8fe8df` / `143 232 223` | |
| `--st-info` | `#315a86` / `49 90 134` | `#0fbcb0` / `15 188 176` | 薄荷主色（仅图标/色块/描边，不做白字底——已核实源码无 bg-info+白字用法） |
| `--st-info-deep` | `#2f4f7a` / `47 79 122` | `#0f615f` / `15 97 95` | chip 文字色；**比设计稿深一档**：mid+deep 5.1:1、soft+deep 6.3:1（原稿 #187574 压 mid 仅 3.9:1 破线） |
| `--st-success-soft` | `#e8f3ec` / `232 243 236` | `#e8f7f0` / `232 247 240` | |
| `--st-success` | `#15803d` / `21 128 61` | `#00b473` / `0 180 115` | 仅图标/色块（唯一用法是注册页密码强度条），不做白字底 |
| `--st-success-deep` | `#106b35` / `16 107 53` | `#0b6b45` / `11 107 69` | 实心徽标底（白字 6.6:1）；**比设计稿深一档**：mid+deep 4.8:1（原稿 #0b7a52 压 mid 4.0:1 破线） |
| `--st-radius-md` | `10px` | `12px` | 输入框/小卡（= Tailwind rounded-xl） |
| `--st-radius-lg` | `14px` | `16px` | 标准卡片（= Tailwind rounded-2xl） |
| `--st-radius-xl` | `18px` | `28px` | 强调卡（= Tailwind rounded-3xl，粉彩大圆角仅品牌时刻用） |
| `--st-sidebar-width` | `76px` | `240px` | 纯文档对齐（已核实全仓库无消费方，AdminShell 宽度在 Phase 3 直接改） |

同时更新 design-tokens.css 的头注释与状态色注释：方向改为「墨黑 + 明黄 + 品牌蓝 + 薄荷」；info/success 的 DEFAULT 档不再标注「可配白字」（新值仅图标/填充；danger DEFAULT 白字 5.1:1 维持不变）。

> 保留：`--st-surface`、`--st-text-*`、`--st-border`、`--st-shadow-*`、warning/danger 全档、`--st-ai` 族、暖色点缀、`--st-pink/peach/mint` 一律不动。

### 1.3 Vant 映射区（同文件底部）

```css
--van-primary-color: var(--st-ink);
--van-blue: var(--st-link);
```

### 1.4 焦点环（`frontend/src/styles/components.css:38` 的 `.st-focus`，注意不在 main.css）

- `box-shadow` 里裸写的 `rgb(30 53 88 / 0.12)` 改为 `rgb(28 28 30 / 0.14)`；`border-color: var(--st-brand-500)` 不动（自动变品牌蓝）。
- `main.css` 的 `.header-gradient`（background: var(--st-brand-800)）自动变墨黑，无需改代码。

**Phase 1 验收**：全站无布局变化；主按钮/Vant 主色变墨黑；页面底色 `#F7F8FA`；全站浅蓝 tint 跟随新品牌蓝（无旧蓝残留）；`npm run build` 通过。

---

## Phase 2 — 基础组件胶囊化（`components/ui/AppButton.vue` + `tailwind.config.js` + `constants/statusTone.ts`）

### 2.1 `AppButton.vue` —— 全部变体改胶囊形

- `sizeClass` 三档的 `rounded-lg / rounded-xl` 全部改 `rounded-full`（sm h-8 / md h-10 / lg h-12 高度不变）。
- `variant=primary`：`bg-ink text-white hover:bg-ink-soft active:bg-ink`（原 brand-800/700/900 引用全替换）。
- `variant=secondary`：白底 + `border border-strong`，胶囊，字色 primary（不变）。
- **新增 `variant=accent`**：`bg-accent text-ink hover:bg-accent-deep`（用于「一键匹配」「立即投递」等品牌时刻 CTA），同步扩 TS variant 联合类型。
- `ghost / text` 变体：字色 `text-brand-800`（自动变墨黑）保留，hover/active 底 `bg-brand-50/brand-100` 跟随新浅蓝阶，不改类名。

### 2.2 状态徽标 —— 改 `constants/statusTone.ts`（不是 AppStatusBadge.vue，它只是消费者；状态词表以 `constants/orderStatus.ts` 为准：招聘中/试课中/已成交/已归档）

`ORDER_STATUS_TONES` 与 `APPLICATION_STATUS_TONES` 中同名状态保持同色：

| 状态 | 改动 |
|---|---|
| recruiting 招聘中 / pending 待审 | `info-soft + info-deep`（不变类名，Phase 1 换值后自动变薄荷） |
| trial_in_progress 试课中 | `bg-info-mid` → **`bg-accent-soft text-accent-ink`，ring 改 `ring-accent`**（订单与投递两处同步改） |
| completed 已成交 | **实心档保持 `bg-success-deep text-white`**（新 success-deep 白字 6.6:1；不许用 DEFAULT 档 #00b473 配白字，2.7:1 破线） |
| archived 已归档 | 中性灰，不变 |

红线重申：实心档仅 success-deep / danger / info 深档允许白字；accent 与 warning 一律浅底深字。

### 2.3 `tailwind.config.js`

- 用既有 `token()` 风格注册（消费 `-rgb` 三元组，保透明度修饰符），不要用 `'var(--st-x)'` 直引：

```js
ink: { DEFAULT: token("ink"), soft: token("ink-soft") },
accent: { DEFAULT: token("accent"), deep: token("accent-deep"), soft: token("accent-soft"), ink: token("accent-ink") },
link: token("link"),
```

- `boxShadow.card/elevated` 不动。

**Phase 2 验收**：所有 AppButton 为胶囊形；primary 黑胶囊、accent 黄胶囊；试课中 chip 变黄底、已成交实心绿底；`node scripts/check-tokens.mjs` 通过。

---

## Phase 3 — 中介后台壳层（`components/admin/AdminShell.vue` 第 127-181 行侧栏 + `components/AdminTabbar.vue`）

现状：`w-[212px] bg-brand-900 text-white` 深色侧栏，激活态 `bg-white/15 text-white`。改为：

1. 侧栏容器：`w-[212px]` → `lg:w-60`（240px），`bg-brand-900 text-white` → `bg-surface text-secondary`，加 `border-r border-default`；侧栏内 `text-white/*` 全系改 `text-secondary/text-muted` 对应档。
2. Logo 行：白底方块「智」→ 明黄圆角方块（`bg-accent` + 墨黑 SVG/文字 Mark）+ `text-ink` 粗体 "SmartTutor"（移动端 `bg-brand-50 text-brand-800` 小方块同步改 `bg-accent text-ink`）。
3. 导航项激活态：`bg-white/15 text-white` → **黑胶囊**（`bg-ink text-white rounded-xl`）；非激活 `text-secondary hover:bg-surface-soft`（去掉 `hover:bg-white/10`）。
4. 「投递审核」计数 badge：→ `bg-accent text-ink` 小胶囊（数字 tabular 11px Bold）。
5. 顶栏保持白底；顶栏圆钮 `bg-surface-soft hover:bg-brand-50` 不改类名（自动跟随新浅蓝）。
6. `components/AdminTabbar.vue`：激活项改 `bg-ink text-white` 圆角块，与 H5 Tab 规范一致。

**Phase 3 验收**：Dashboard/订单/教员/财务各页壳层统一，导航激活态为黑胶囊，侧栏无蓝色残留、无白字压浅底。

---

## Phase 4 — 教员端 H5（`views/teacher/Board.vue`、`views/teacher/OrderDetail.vue`、`components/TeacherTabbar.vue`，另触及 Login/Register 胶囊化）

对照设计稿 03/04 画板逐项落地：

1. **首屏标题区**（Board.vue 推荐视图）：页面主标题 `text-lg` → `text-[28px] font-bold text-ink`（**不要写 `text-[--st-ink]`，那是无效语法**）；副标题一行讲清「匹配 N 个在招订单」（现有文案结构保留，仅放大层级）。
2. **视图切换（推荐/地图）**：现有顶栏分段器 → 右侧胶囊分段（白底描边容器 `rounded-full p-0.5`，激活段 `bg-ink text-white rounded-full`）。
3. **筛选 chips**：激活项 `bg-ink text-white`，非激活白底描边，全部胶囊。
4. **新增「本周动态」banner**（`bg-accent-soft text-accent-ink rounded-2xl`，星形图标）：数据取现有 filteredOrders 计数与最高时薪，无新接口；没有新增单时整块隐藏。
5. **订单卡重排**（核心转化改动）：
   - 第一行：学科 chip（`info-soft/info-deep`）+ 推荐标（`bg-accent text-ink`）+ 右侧更新时间；
   - 标题 16 semibold；第三行 **时薪 `text-[18px] font-bold` 前置** + 距离/投递数 12px 灰字；
   - 底部行：中介名 12px 灰 + 右侧小号黑胶囊「投递」（复用 AppButton sm primary；品牌时刻用 accent）。
   - 卡片统一 `st-card rounded-2xl`。
6. **OrderDetail.vue**：信息区改「label 72px 灰 + value 深色」行式卡片；中介联系卡改 `bg-accent-soft`；底部固定 CTA 条改白底 + 左侧收藏圆钮 + 右侧黑胶囊「立即投递 · 截止时间」（复用现有截止时间数据）。
7. **`components/TeacherTabbar.vue`**：容器改悬浮胶囊（白底描边 `rounded-[36px] p-1`，三等分），激活项 `bg-ink text-white rounded-[28px]`，非激活灰。引用它的四个页面（Board/MyApplications/Profile/HelpCenter）内容区 `pb-14` → `pb-24` 防遮挡。
8. **Login.vue / Register.vue**：`header-gradient` 按钮自动变墨黑后，`rounded-xl/2xl` → `rounded-full`；`shadow-brand-500/30` 蓝色投影 → `shadow-ink/25`（避免黑钮配蓝晕）。

**Phase 4 验收**：iPhone 12 宽度下首屏无横向溢出；订单卡时薪第一眼可见；投递主流程（列表→详情→投递）全通。

---

## Phase 5 — 工作台与订单看板（`views/admin/Dashboard.vue`、`views/admin/OrderWorkspace.vue`）

1. **Dashboard KPI 行**：四张 `AppStatCard`（在招订单/待审投递/本月成单/本月流水）；delta 统一为小胶囊（涨绿 `success-soft/success-deep`、警示黄 `accent-soft/accent-ink`）。
2. **新增「行动队列」卡**（首屏主区，宽卡）：三条规则——挂单 3 天 0 投递（紧急/黄）、待审投递>0（审核/薄荷）、试课中>0（试听/粉）。**数据来源（已核实）**：`stats`/`appSummary`/`roi`/`recent` 均已在页面加载（Dashboard.vue:18-25、111）；「挂单 3 天 0 投递」从 recent 订单列表派生（created_at + 投递数为 0）；「明日试听」现有接口无排期数据，**降级为「试课中 N 单待跟进」**（stats.trial，页面已有同款文案口径）。不新增后端接口；无待办时显示现有 AppEmpty。
3. **最近订单表**：行 hover `bg-surface-soft rounded-xl`；状态列用 Phase 2 换肤后的 AppStatusBadge；金额右对齐 tabular Bold；转化漏斗进度条 `bg-brand-700` → `bg-link`（pressed 色不做填充语义）。
4. **OrderWorkspace.vue**：列表视图之上新增看板视图切换（顶栏右侧胶囊分段：看板/列表，激活黑底）；四列 = 招聘中/试课中/已成交/已归档，列头「色点 + 名称 + 数量」，卡片复用订单卡精简版。列数据由现有 orders 列表按状态前端分组，不新增接口。

**Phase 5 验收**：工作台首屏先看到行动队列再看到表格；看板拖拽不在本期范围（只做展示 + 点击跳详情）。

---

## 全局验收清单（全部完成后自查）

- [ ] `grep -rn "#2f4f7a\|#4a80b5\|#26496e\|#3b6da3\|#2f5c8c\|#eaf1f7\|#c6d9ec\|#315a86\|#15803d\|#106b35\|#faf9f7" frontend/src` 仅剩 design-tokens.css 注释或零结果（旧蓝/旧值清零）
- [ ] 全站按钮均为胶囊形；主 CTA 墨黑、品牌 CTA 明黄
- [ ] 明黄从未作为白字底色出现；实心底白字仅 success-deep/danger（对比度红线）
- [ ] 教员端 H5 三屏 + 后台三屏与设计稿画板逐屏比对（截图对照）
- [ ] `npm run build` 通过；`node scripts/check-tokens.mjs` 通过；教师/中介/超管三角色登录与核心流程手测通过
- [ ] 现有 pytest 后端测试不受影响（本次前端-only）

## 提交切分

`docs(ui): ui2.0 说明书 v2（对齐代码与对比度矩阵）` → Phase 1 `feat(tokens): ui2.0 换肤` → Phase 2 `feat(ui): 胶囊组件体系` → Phase 3 `feat(admin): 壳层改版` → Phase 4 `feat(teacher): h5 首屏与详情改版` → Phase 5 `feat(admin): 工作台行动队列与看板`。
