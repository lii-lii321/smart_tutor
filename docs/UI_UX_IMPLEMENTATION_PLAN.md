# Smart Tutor UI/UX 实施计划

> 上游：`docs/UI_UX_AUDIT.md`（问题登记表，本计划所有编号一一对应）+ `docs/DESIGN_SYSTEM.md`（目标态规范）。
> 总原则：**修复与收敛，不重设计**。全程不改业务逻辑、路由结构、API 契约、状态机与金额计算；`stores/`、`api/`、后端零改动（Plan #1 只消费后端已返回的字段）。
> 排序依据：业务价值 × 使用频率 × 用户影响。每阶段独立提交、独立验收。

---

## 一、阶段划分（执行顺序即依赖顺序）

```
Phase A 地基修复（全局，先做，后续所有阶段受益）
  └─ Phase B B 端核心页 P0（批量/返回/hover）
       └─ Phase C 表单与错误处理规范落地
            └─ Phase D AI 解释与 C 端转化补强
                 └─ Phase E 全局一致性收尾
```

### Phase A — 地基（字阶 token + 触控目标 + focus 全局化）

| # | 内容 | 落点 |
|---|---|---|
| A1 | 新增字阶 token（`--st-text-caption 11px` → `--st-text-display`）并映射 Tailwind `fontSize`（消费 `-rgb` 同款思路，见 DESIGN_SYSTEM §2.1） | `design-tokens.css`、`tailwind.config.js` |
| A2 | 全局 focus-visible：把 `.st-focus` 推广为原生 `button/a/[role]` 的 `:focus-visible` 基线（styles 层一处），AppButton 保持现状 | `styles/main.css` 或 `components.css` |
| A3 | 触控目标整改：`MyApplications` 投递卡动作按钮（`py-1` ≈26-28px）、全库 `text-[9px]`/`text-[10px]` 违规位逐个升级到 caption(11px)+热区 ≥32px（主操作 ≥44px） | `views/teacher/MyApplications.vue`、`Board.vue:421` 等 |
| A4 | 死代码处置：`AppStatCard`（KPI 方向已否决，**删除**防复活）、`AppDrawer`/`AppPageHeader`（删除或标记 deprecated，倾向删除——Vant popup 已是事实标准） | `components/ui/` |

**验收门**：`npm run build`（含 vue-tsc）零错 · `node scripts/check-tokens.mjs` 通过 · 四档视口（375/768/1024/1440）截图无横向滚动 · 教师端三主流程真机手测（投递按钮不再误触）。

> **✅ Phase A 执行记录（2026-10-05 落地，前端 30 文件 +100/−155 左右，未提交待用户确认）**
> - **A1 ✅**：七级字阶 token（`--st-text-caption 11px` → `--st-text-display 24px`，含行高伴生变量）落 `design-tokens.css`，Tailwind `fontSize` 映射为 `text-caption ~ text-display`，与 DESIGN_SYSTEM §2.1 逐值一致。
> - **A2 ✅**：全局 focus-visible 基线（components.css），与 `.st-focus` 合并为单条规则，光环色消费 `--st-ink-rgb`（消除裸写 rgb）。
> - **A3 ✅**：45 处 `text-[9px]/[10px]` → `text-caption`（20 文件，Node 字节安全替换）；复审补漏 `FinancialRecords.vue` CSS 块形式 10px 一处；8 处 `leading-3` 行高覆写移除、回落 token 行高 16px；`.st-chip`/`main.css` 徽标改消费 caption token；MyApplications 投递卡两按钮 `min-h-[32px]`、空态 CTA 由 24px van-button small 换 AppButton lg；「滞」角标 `bg-warning`→`bg-warning-deep`（顺手修复 warning 白字 3.6:1 违例，danger 白字 5.1:1 合规保留）。
> - **A4 ✅**：`AppStatCard`/`AppDrawer`/`AppPageHeader` 删除（删除前后两轮全库零引用验证，`components.d.ts` 随构建同步）。
> - **验收结果**：build/vue-tsc ✅ · eslint ✅ · check-tokens ✅ · vitest 59/59 ✅。**e2e 3 个失败经 stash 基线归因为过时用例**（期望 vant 旧 `role=dialog` 确认框、旧 `/admin/login→/teacher/login` 统一路由、UI 2.0 改版前「为你推荐」标题），与本轮改动无关——**待办：Phase E 顺手更新这 3 个用例**。四档视口截图与真机手测留给用户执行。
> - **code-review 双轴自查**：Standards 无硬违反，Spec A1/A2/A4 符合、A3 复审后补齐；全部 judgement call 当场修复。遗留观察：ApplicationStepper 15px/OrderStageBar 16px 步骤圆点内 11px 数字的视觉紧度（实机走查确认，必要时圆点微放大）。

### Phase B — B 端核心页 P0

| # | 内容 | 落点 |
|---|---|---|
| B1（审计 BO-1） | **批量结果完整呈现**：读取后端已返回的 `skipped`，成功后按 BatchImport 结果页范式汇报「成功 updated 条 / 跳过 skipped 条」；skipped>0 时列出可定位信息并给「重新处理」入口（重试=对剩余单再发起同批次操作）。若现接口未返回 skipped 明细，第一版只展示计数与提示「N 条因状态变化被跳过，可筛选后重试」，不新增后端 | `OrdersList.vue:203-218` |
| B2（审计 IA-1） | **返回键跟随来路**：把 OrderWorkspace 的 `goBack()`（`router.back()` + 无历史兜底）提取为 `composables/useSmartBack.ts`（兜底路由作为参数），替换 OrdersList / ApplicationsReview / BatchImport / FinancialRecords 四处硬编码 `push('/admin/dashboard')`。兜底目标维持语义父级（dashboard），仅在有历史时跟随来路——与 4a72d0f 模式一致 | 四个视图 + 新 composable |
| B3（审计 IH-2） | **消灭纯 hover 依赖**：审核页订单上下文条的「查看完整信息/编辑」提示改为常显（移动端）或改整条卡片可供性表达（右侧 chevron + hover 提示保留为桌面增强），触屏上「可点」必须可见 | `ApplicationsReview.vue:580-582` |
| B4（审计 BO-2） | **批量确认影响预告**：确认弹窗正文列出「将处理 N 条：recruiting x 条、trial y 条…→ 目标状态」，数据源为已勾选订单的本地状态，不新增请求 | `OrdersList.vue:203-208` |

**验收门**：构建门同上 · 批量操作走查（选 3 条混状态单执行，确认弹窗、结果汇报、skipped 呈现、重试）· 从审核页深链订单列表再返回，验证回到审核页 · 手机端确认上下文条可点性可见。

> **✅ Phase B 执行记录（2026-10-05 落地，同日与 Phase A 先后提交）**
> - **B1 ✅ 批量黑洞修复**：核实后端语义——`batch_update_status` 返回的 `skipped` 是纯计数（= 发起数 − 成功数，含义为「已是目标状态或 id 不存在」），且任何一单流转非法会整批 400。因此正解是**分解汇报而非重试入口**：skipped>0 时用 appConfirm 呈现「已更新 X 条，跳过 Y 条」+ 原因说明（跳过的单无需处理），skipped=0 保持成功 toast。前端零后端改动。
> - **B2 ✅ 返回键统一**：新建 `composables/useSmartBack.ts`（back 有历史则退一层，无历史兜底语义父级）；OrderWorkspace 原 goBack 重构为消费该 composable（模式出处 4a72d0f），OrdersList / ApplicationsReview / BatchImport 兜底 `/admin/dashboard`；FinancialRecords 的 `useRouter` 仅有 NavBar 一处使用，已随之清除。
> - **B3 ✅ hover 依赖消灭**：审核页订单上下文条「查看完整信息 / 编辑订单 →」由 `opacity-0 group-hover:opacity-100` 改为常显（触屏可达，桌面不再有隐藏惊喜）；触碰行顺带迁移 `text-[11px]`→`text-caption`。
> - **B4 ✅ 影响预告**：批量确认弹窗从「将处理 N 条」升级为「选中 N 条：招聘中 2 条、试课中 1 条。确认后统一设为『XX』」——分布由已加载列表实时计算，不新增请求。
> - **验收结果**：build/vue-tsc ✅ · eslint ✅ · check-tokens ✅ · vitest 59/59 ✅ · e2e 失败集与干净基线完全一致（同 3 个过时用例，零新增失败）。真机走查项（混状态批量走查、审核页深链返回、触屏上下文条可点）留给用户。

### Phase C — 表单与错误处理（审计 FM-1/2、ER-1/2）

| # | 内容 | 落点 |
|---|---|---|
| C1 | **EditOrderPopup 校验改造**：必填星标；年级科目/课酬/展示地址 blur 校验 + 字段下 `error-message`（Login.vue 范本）；经纬度裸数字输入收起为「高级」折叠或地图选点入口（复用现有 geo 能力，不新建组件）；失败 toast 改为指明字段 | `components/admin/EditOrderPopup.vue` |
| C2 | **错误文案三段式清扫**：先改四处高频（「保存失败」「批量操作失败」「看板加载失败」「数据加载失败」），格式=发生了什么+为什么+怎么办 | 各视图 |
| C3 | **重试入口补齐**：MyApplications 加载失败态改「错误说明 + 重新加载」（复用 OrderDetail 范式）；看板列失败提供列级重试 | `MyApplications.vue:48-54`、`OrdersList.vue:320-322` |

**验收门**：构建门 · EditOrderPopup 空提交/非法提交走查（错误落位、聚焦首个错误）· 断网场景手测重试。

> **✅ Phase C 执行记录（2026-10-05 落地）**
> - **C1 ✅ EditOrderPopup 校验改造**：三个必填项（年级科目/课酬文本/展示地址）加 `required` 星标 + blur 校验 + 字段下内联错误（Login.vue 仓内范本模式）；提交时全量校验并**自动聚焦第一个非法字段**（Vant FieldInstance.focus）；错误文案三段式（「必填——年级科目是教员匹配与推荐的主要依据」）；经纬度裸数字输入**折叠进「坐标微调」高级区**（默认收起，label 注明「AI 自动定位一般无需改动」）；「保存失败」改为消费 `getApiErrorMessage`（后端 422 细节透传，兜底文案带网络指引）。
> - **C2 ✅ 错误文案三段式**：四处高频全部改齐——工作台 toast「工作台加载失败：网络或服务暂时不可用，请稍后下拉重试」、最近订单错误块、批量操作兜底「批量操作未完成：网络异常，请检查网络后重试」、EditOrderPopup 两处。
> - **C3 ✅ 重试入口补齐**：MyApplications 新增首屏错误态（warning 图标 + 说明 + AppButton 重新加载），与「暂无投递」空态严格区分（此前失败会被误读成没有投递）；看板从 `Promise.all` 一挂全空白改为**列级加载**——单列失败只折叠该列并给「本列加载失败：网络波动，点击重试」（列级重试，不连坐）。
> - **验收结果**：build/vue-tsc ✅ · eslint ✅ · check-tokens ✅ · vitest 59/59 ✅ · e2e 失败集与基线完全一致。

### Phase D — AI 解释与 C 端转化（审计 AI-2、TF-1）

| # | 内容 | 落点 |
|---|---|---|
| D1 | **B 端推荐解释接线**：`TeacherMatchPopup` 教员行接入现有 `RecommendationExplainCard`（或其精简形态），展示后端 reasons；数据缺失时保持现有 null 口径不放假解释。纯前端接线（推荐 API 已返回解释数据结构则直接消费；若 B 端邀约接口未含 reasons，则先展示规则说明文案「按科目/年级/距离/信用综合排序」升级为维度徽标，不动后端） | `components/admin/TeacherMatchPopup.vue`、`business/recommendation.ts` |
| D2 | **C 端复制动作前置**：MyApplications 投递卡内直接提供「复制联系消息」（复用 OrderDetail 的消息构建/clipboard 工具），原「微信联系中介」按钮语义改为直达详情不再承担复制职责 | `views/teacher/MyApplications.vue:274-280`、`utils/clipboard.ts` |

**验收门**：构建门 · 邀约弹窗解释展示与空态 · 教师端两步变一步实测。

> **✅ Phase D 执行记录（2026-10-05 落地）**
> - **D1 ✅ B 端推荐解释增强**：核实后端 `teacher_match.py`——内部算四维分（科目 .45/年级 .2/信用 .2/距离 .15）但只返回 `total_score`，此前**算完只用于排序、从未展示**。按计划预授权的降级方案（不动后端）：每行新增「匹配度 N」徽标（AI 紫，限推荐语境）+ 弹层说明升级为权重公式；六维分数条需后端在 `RecommendedTeacherItem` additive 下发 `score_breakdown`，记为 **OB-7**（后端零改动红线内不做）。顺手清掉 `window.__matchErr` 调试残留、错误文案三段式。
> - **D2 ✅ 复制动作前置**：MyApplications 卡内直接「复制联系消息」（与 OrderDetail 同文案口径，字段全部来自投递列表已有数据，零新请求）；原「微信联系中介」按钮实际只是跳详情，语义改为复制，转化末端「看状态→跳详情→复制」三步变「看状态→复制」一步。

**验收门**：构建门同上 · 全局走查按 DESIGN_SYSTEM §10 九态自查表逐屏过 · 三角色核心流回归（登录→B 端五页→C 端四页）。

> **✅ Phase E 执行记录（2026-10-05 落地）**
> - **E1 ✅ toast 皮肤二选一**：删除 main.css「白底居中胶囊」整段（UI 2.0 换肤前遗留的第二套皮肤，与 App.vue 深色胶囊长期并存靠 `!important` 赌加载顺序）；顶部深色胶囊（App.vue）为唯一口径。
> - **E2 ✅ 黑闪违例清理**：Board.vue 首屏全屏 `van-overlay` 移除（黑闪硬规矩违例；App.vue 已给 overlay 加淡入但遮罩本体仍在），首屏反馈由 `showLoadingToast` + 推荐区骨架承担，反馈不缺位。
> - **E3 ✅ 空态收敛**：MyApplications 手写空态换 `AppEmpty`（icon/标题/描述/action slot 全量语义，含「去看看订单」按钮）。HelpCenter 核实无列表空态（内容常显），无需处理。
> - **E4 ✅ 看板列头升级**：移动/桌面看板列头由「色点 + 文字」换为 `AppStatusBadge`（statusTone 唯一口径，与列表页同款），`KANBAN_COLUMNS` 的手写 dot 色字段随之删除。
> - **E5 ✅**：字阶任意值迁移随 B-E 各阶段触碰行完成（审核页上下文条、看板空态/列头等）。
> - **✅ e2e 过时用例修复（3 个）**：① Board 锚点改游客可见的 h1「找到适合你的家教订单」（「为你推荐」仅登录+有推荐时渲染）+ tabbar 定位改 `.teacher-tabbar`；② 中介登录断言改为停留 `/admin/login`（三角色独立路由已是现状）+ 工作台锚点改「本月经营」标题；③ 投递确认改定位 AppConfirm 底部弹层内按钮（无 dialog role，`.last()` 取顶层弹层防与投递弹层同名按钮冲突）。**e2e 8/8 全绿——修复后首次完整通过全链路（注册→简历→投递→审核五步流转→脱敏断言→成交展示）**。
> - **验收结果**：build/vue-tsc ✅ · eslint ✅ · check-tokens ✅ · vitest 59/59 ✅ · **e2e 8/8 ✅**。

### Phase E — 全局一致性收尾（审计 IH-4/5、VH-3）

| # | 内容 | 落点 |
|---|---|---|
| E1 | **toast 皮肤二选一**：保留 App.vue 顶部深色胶囊，删除 main.css 白底胶囊规则（实施时以真机效果定夺，只保留一套） | `App.vue:48-62`、`styles/main.css` |
| E2 | **Loading 形态收敛**：清除 Board.vue:886 全屏 van-overlay（黑闪硬规矩违例），改骨架/局部指示；新代码一律按 DESIGN_SYSTEM §5.9 阶梯 | `views/teacher/Board.vue` |
| E3 | **空态统一**：MyApplications、HelpCenter 手写空态收敛到 `AppEmpty` | 两视图 |
| E4 | **看板列头升级**：色点改为 `AppStatusBadge` 同款 chip（文字+色），数量保留 | `OrdersList.vue:287-292,442-444` |
| E5 | 字阶任意值迁移启动：Phase B-E 触碰到的页面顺手替换为字阶 token（不做全库专项） | 随各页 |

**验收门**：构建门 + `check:tokens` · 全局走查按 DESIGN_SYSTEM §10 九态自查表逐屏过 · 三角色核心流回归（登录→B 端五页→C 端四页）。

---

## 二、问题总表（优先级 × 页面 × 方案 × 影响 × 难度）

| 优先级 | 页面/模块 | 问题 | 改进方案 | 影响 | 难度 |
|---|---|---|---|---|---|
| P0 | OrdersList 批量 | skipped 黑洞（BO-1） | 消费已返回的 skipped + 分解汇报 + 重试入口 | 高 | 低 |
| P0 | B 端 4 视图 | 返回键硬编码回工作台（IA-1） | useSmartBack composable 推广 goBack 模式 | 高 | 低 |
| P0 | 全局 | 字阶无 token、9-10px 存在（VH-1/A11Y-2） | 字阶 token + 违规位清理 | 高 | 中 |
| P0 | MyApplications 等 | 触控目标 26-28px（A11Y-1） | 热区整改 ≥44/≥32+间距 | 高 | 中 |
| P0 | ApplicationsReview | 纯 hover 提示触屏不可达（IH-2） | 常显化/可供性改造 | 高 | 低 |
| P1 | EditOrderPopup | toast 校验、无必填标、裸经纬度（FM-2） | 字段级校验 + 必填标 + 收起机器字段 | 高 | 中 |
| P1 | TeacherMatchPopup | B 端推荐无解释（AI-2） | 接入 RecommendationExplainCard/维度徽标 | 中高 | 低中 |
| P1 | MyApplications | 「联系中介」复制动作深两层（TF-1） | 卡内直接复制 | 中高 | 低 |
| P1 | 全局 | 两套 toast 皮肤（IH-4） | 二选一清理 | 中 | 低 |
| P1 | Board 等 | Loading 三分 + 全屏遮罩违例（IH-4b） | 阶梯化 + 清违例 | 中 | 低中 |
| P1 | 全局 | focus-visible 仅 AppButton（IH-3） | styles 层全局基线 | 中 | 低 |
| P1 | OrdersList 批量 | 确认无影响预告（BO-2） | 弹窗列状态分布 | 中 | 低 |
| P1 | 各视图 | 错误文案半截 + 重试稀疏（ER-1/2） | 三段式清扫 + 重试态 | 中 | 低中 |
| P1 | MyApplications/Help | 手写空态（IH-5） | 收敛 AppEmpty | 低中 | 低 |
| P2 | OrdersList 看板 | 列头色点弱（VH-3） | 换 AppStatusBadge | 低 | 低 |
| P2 | components/ui | 死代码 3 件（VH-4） | 删除防复活 | 低 | 低 |

> P2 两项成本极低，可搭车进 Phase A/E，不单独立阶段。

---

## 三、三张决策清单

### 必须改（P0，阻碍任务完成或高频摩擦）
1. 批量操作 skipped 黑洞——中介会漏单而不自知。
2. B 端返回键不一致——导航不可预期，模式已存在于 OrderWorkspace，只差推广。
3. 字阶 token 化 + 9/10px 灭绝——可读性与一致性地基，越晚做迁移越贵。
4. 移动触控目标——误触率直接伤中介/教师日常操作。
5. 纯 hover 提示——触屏主力设备上功能不可达。

### 建议改（P1，显著影响效率/信任/一致性）
表单校验规范、B 端推荐解释、C 端复制前置、toast/loading/空态统一、focus 全局化、批量影响预告、错误三段式与重试入口。

### 目前不要动（含明确反对项）
| 项 | 理由 |
|---|---|
| **设计 token 体系与色值**（ink/accent/状态四档/AI 紫/暖点缀） | 已实机验收、WCAG 实测、护栏在位；换色=纯风险零收益 |
| **Workbench 的 Todo-centered 结构** | 行动队列+三个经营数+四行资金就是「现在有什么事要我处理」的正确答案；**明确反对**加 KPI 卡/折线图/饼图/巨型数字 |
| **AI 导入七件套可解释方案** | 分诊+定性置信度+字段级原因已是行业标准之上，任何「简化」都是倒退 |
| **财务三色口径与账本形态、18/20px 基线** | 既有拍板（财务红线区） |
| **orderActions 状态机驱动 CTA + 后端把关红线** | 安全边界，前端加判权只会造成两处真相 |
| **AppConfirm 堆叠确认模式** | 引入 undo toast 体系收益低（可逆操作均已有对向入口：归档↔重发布、拒绝↔恢复），且推翻全局惯例 |
| **悬浮胶囊 tabbar / AdminShell 1024 壳切换 / 导入页「空旷 vs 高级」框架** | 已验收的品牌与布局资产 |
| **不加面包屑** | H5 语境负资产；位置感现有方案足够 |
| **移动审核页左栏宽度、草稿保存、aria-live/焦点陷阱、快捷键推广** | 观察项 OB-1~6，等真实用户信号再动，避免为改而改 |

---

## 四、全程验证清单（每阶段提交前）

```bash
cd frontend
npm run build          # 含 vue-tsc --noEmit，零报错
npm run lint           # eslint 零新增告警
node scripts/check-tokens.mjs   # 护栏通过
```

人工门（每阶段）：
- [ ] 路由与跳转：三角色登录 → 各自首页 → 核心流走通，返回键行为正确
- [ ] 九态：default/hover/focus/active/disabled/loading/empty/error/部分成功 逐屏过
- [ ] 响应式：375 / 768 / 1024 / 1440 四档 + 微信真机（dvh、安全区）
- [ ] 业务回归：订单状态流转（投递→定金→试课→尾款→成交；试课失败退费）、金额展示、AI 导入一单全流程
- [ ] 后端零改动确认：`git diff --stat` 不含 `routers/ services/ models/ api/`
