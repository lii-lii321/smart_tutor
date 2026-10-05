# Smart Tutor UI/UX 专业审计报告

> 审计日期：2026-10-05 · 审计范围：前端全部 24 个视图 + 全局交互层（不改任何代码）
> 审计角色定位：SaaS 产品设计师 + UX Designer + 前端架构师 三合一视角
>
> 参照标准（外部 UI/UX Skills 提炼，见附录 A）：
> niсohodt/ui-ux-pro-max · touchine-ojo/OJO-Design-Skills · cuellarfr/design-skills ·
> arez-xd/ux-ui-design-taste · adamtossell/ui-skills
>
> 配套文档：`docs/DESIGN_SYSTEM.md`（设计系统现状与规范）、`docs/UI_UX_IMPLEMENTATION_PLAN.md`（分阶段实施计划）

---

## 0. 审计结论（TL;DR）

**这个产品的 UI/UX 底子显著好于典型 AI 生成项目，多处设计已达到或超过外部 Skills 的行业标准。**

- ✅ **不需要推翻任何视觉方向**：UI 2.0（白纸 + 墨黑胶囊 + 明黄记忆点）是成熟、克制、经过 WCAG 实测的体系，token 架构（`design-tokens.css` 单一来源 + `check-tokens.mjs` 护栏）在外部 Skills 的评级里属于「教科书级」。**本次审计未发现任何「AI 通用脸」特征**（无紫黑底、无玻璃拟态、无渐变按钮、无假数据）。
- ✅ **信息架构方向正确**：B 端工作台是真正的 Todo-centered（行动队列 + 真实待办数），不是数据大屏；订单工作区以状态机驱动 CTA，符合 Order-Centric 定位。
- ⚠️ **问题集中在执行层的 5 个裂缝**，全部可修且不碰业务逻辑：
  1. 批量改状态存在 **skipped 结果黑洞**（API 返回了数据，UI 不展示）——P0；
  2. B 端 4 个页面**返回键硬编码回工作台**，与已修复的订单工作区不一致——P0；
  3. **字阶无 token**（228 处 `text-[Npx]` 任意值，最小 9px）——P0 地基；
  4. **移动端触控目标过小**（投递卡动作按钮约 26-28px）——P0；
  5. 审核页一处 **纯 hover 依赖**，触屏不可达——P0。
- 结论：**做「修复与收敛」，不做「重设计」**。预计全部 P0+P1 改动不触碰 `stores/`、`api/`、状态机与金额逻辑。

---

## 1. 项目现状速览（审计基线事实）

### 1.1 技术栈与规模

| 项 | 事实 |
|---|---|
| 前端 | Vue 3.5 + Vite 8 + TS 5.9 + Pinia 4 + Tailwind **3.4** + Vant 4.10（auto-import） |
| 视图 | teacher 7 · admin(tenant) 9 · super_admin 1 · public 3 |
| 组件 | ui/ 8 个（其中 3 个死代码）· business/ 12 + 适配器 6 · admin/ 7 · teacher/ 10 · 壳 4 |
| 设计系统 | `src/styles/design-tokens.css`（`--st-*` 唯一来源，含 WCAG 实测注释）→ `tailwind.config.js` 语义类 → `.st-*` 基类；`constants/statusTone.ts` 状态徽标唯一出口；`scripts/check-tokens.mjs` 护栏拦截裸写 Tailwind 内置色 |
| Vant 换肤 | `--van-*` 全量映射到 `--st-*`（design-tokens.css:175-189） |

### 1.2 订单生命周期（后端事实，UI 的「单一事实来源」）

- **订单 4 态**：`recruiting → trial_in_progress → completed`；`archived` 可从 recruiting/trial 进入、可重开。三个历史废弃态只读。
- **投递 9 态**：`pending → shortlisted → deposit_paid → trial_in_progress → balance_paid → completed`，旁路 `rejected(可恢复)/refunded/forfeited`。
- **关键业务规则**：订单状态主要由投递动作驱动（付定金时订单保持 recruiting、成交时兄弟投递自动退款）；教员不直接驱动订单状态；前端不判操作合法性、后端 403/409/422 把关（`business/order/orderActions.ts:4-9` 明文红线）。
- **UI 映射质量**：`statusTone.ts` 把 9 个投递态 + 4 个订单态收敛到 4 色族 × 4 档，同名状态跨订单/投递同色，且自带「定金浅→尾款中→成交实心」的推进语义。**这是全项目最值得保护的设计资产之一。**

### 1.3 双端定位（审计判定基准）

- **B 端（中介）**：Convention Track 运营型 SaaS。验收旋钮 = density 7-9 / motion 1-3 / variance 3-5（ux-ui-design-taste `visual-dials.md` 口径）。核心问题只有一个：「现在有什么事要我处理？」
- **C 端（教师 H5）**：事务型工具（秒开秒用、零学习成本），兼品牌记忆点（明黄点缀、悬浮胶囊 tabbar）。

---

## 2. 逐维度审计

> 每条问题按固定格式：**问题 → 为什么是问题 → 对用户的影响 → 应该怎么改**。已合理的部分明确标注「不需要改」。

### 2.1 信息架构

**整体判断：不需要改结构。** 24 个视图、admin 侧栏三组导航（经营/订单/资金与教员）、H5 三个 tab，主层级清晰；订单状态信息在列表/看板/工作区/审核页四处出现属于 Order-Centric 的合理重复（同一事实的四个观察窗口），不构成信息冗余。

| # | 发现 | 证据 |
|---|---|---|
| IA-1 🔴 | **B 端返回键行为不一致**：OrdersList / ApplicationsReview / BatchImport / FinancialRecords 的 NavBar 左箭头全部硬编码 `router.push('/admin/dashboard')`，不回来源页；全 B 端只有 OrderWorkspace 是 history-aware 返回（`goBack()`，OrderWorkspace.vue:137-140）。用户从审核页深链进订单列表、看完按返回，会被送到工作台而不是审核页。这与 commit 4a72d0f 已在订单工作区落地的「返回键跟随来路」模式不一致，属于同一问题只修了一处。 | OrdersList.vue:345、ApplicationsReview.vue:421、BatchImport.vue:255、FinancialRecords.vue:314 |
| IA-2 🟡 | **移动端 B 端 9 视图对 5 tab**：教员管理/设置/批量导入不在 `AdminTabbar`（导入高亮已归并到订单 tab，AdminTabbar.vue:24-25），移动端只能从工作台入口进入。频率低可接受，但新中介不一定找得到「教员管理」。 | AdminTabbar.vue:42-54 |
| IA-3 🟢 | **紧迫度口径跨页不一致**：「急（≥7 天无反应或距过期 ≤24h）/滞/沉寂（14 天折叠）」的 triage 规则只存在于审核页左栏，订单列表按状态 chips 组织。两个入口排序逻辑不同，中介建立不起统一心智。低优先级，记录不展开。 | ApplicationsReview.vue:70-103 |
| IA-4 ⚪ | **不需要改**：不加面包屑。admin 页头各页自管（AdminShell 注释 L245-246），H5 语境面包屑是负担；位置感由 NavBar 标题 + tabbar 激活态维持，足够。 | — |

### 2.2 用户任务流

**C 端教师主链路**：浏览（推荐/地图）→ 订单详情 → 选简历投递 → **复制消息 → 微信联系中介**。前三步顺畅（状态机驱动 CTA、已投递隐藏按钮防 409、未登录带 redirect 跳转）。

| # | 发现 | 证据 |
|---|---|---|
| TF-1 🟠 | **转化末端摩擦**：投递后的真实下一步是「复制联系消息」，但该动作只在订单详情页（OrderDetail.vue:115-133）；投递列表页的「微信联系中介」按钮实际只是跳回订单详情（MyApplications.vue:274-280），用户要点两次才摸到复制按钮。这是全链路离成交最近的一步，摩擦最不该出现在这里。 | MyApplications.vue:274-280 |
| TF-2 🟡 | **简历编辑双形态**：详情页简历选择器里「修改这份简历」跳 `/teacher/profile?resumeId=`（跨页面），而个人中心里编辑简历是弹层（ProfileEditPopup）。同一对象两种编辑形态，用户会困惑「我刚才那个弹层哪去了」。 | OrderDetail.vue:216-218 |
| TF-3 ✅ | **B 端「下一步」引导达标**：工作台行动队列三条待办（待审投递/招聘中/试课中）每条带紧迫文案（「最久一份已等 X 小时 · 教员在等回音」）+ 直达按钮；审核页「急单置顶 → 待处理角标 → 发布时间」排序让待办自然浮现。数据全部来自真实 API total，无装饰性数字。**不需要改。** | Dashboard.vue:96-169 |
| TF-4 ✅ | **AI 导入四步流完整**：粘贴 → AI 识别 → 人工校对 → 批量发布，每步有出口（返回校对、修改重复编号后重试）。**不需要改。** | BatchImport.vue:54-64 |

### 2.3 视觉层级

**整体判断：方向不需要改，执行地基有一个系统性缺口。**

| # | 发现 | 证据 |
|---|---|---|
| VH-1 🔴 | **字阶无 token、任意值失控**：design-tokens.css 没有任何 font-size 变量，全库 228 处 `text-[Npx]` 手写任意值，最小到 **9px**（Board.vue:421 徽标）。页面之间的「标题/正文/辅助」层级靠随手定值维持，导致同类信息跨页不同大、9-10px 文本在移动端接近不可读。这是视觉层级唯一的系统性缺口，也是 DESIGN_SYSTEM.md 里最需要补的一块地基。 | 全库统计；Board.vue:403/421、MyApplications.vue:196 |
| VH-2 ✅ | **每页视觉锚点明确**：工作台=问候语+行动队列首行；订单列表=搜索框+状态 chips；审核页=左栏急单红标；财务页=净收入大数字（32px，配「没收不计」注）。第一眼/第二眼的次序经过设计。**不需要改。** | 各页审计证据 |
| VH-3 🟢 | **看板列头偏弱**：四列仅「色点+名称+数量」，未用 `AppStatusBadge` 同款徽标，与列表页的状态表达弱一档。 | OrdersList.vue:287-292、442-444 |
| VH-4 🟢 | **组件库与现状脱节**：`AppStatCard`（ui-2.0-handoff Phase 5 原计划的 KPI 卡）已因工作台拍板为 Todo-centered 而成为死代码；`AppDrawer`/`AppPageHeader` 同样零引用。留着会误导后续开发重新启用 KPI 卡方向。 | 全库零引用检索 |

### 2.4 信息密度

**整体判断：不需要改，本产品已经是「高密度 + 低认知负担」的正确形态。**

- B 端桌面表格 7 列（订单/状态/地址/频次/信息费/发布/操作）、财务六列、审核页左右分栏一屏双区——密度达标且不过载。
- 卡片信息排布有纪律：订单卡「时薪 18px 前置 + 距离/投递数 12px 灰字」（ui-2.0 Phase 4 落地结果）。
- 移动审核页左栏 `w-40`（160px）标题截断较狠，属于可观察项（OB-1，见 §3），暂不动。
- 明确反对项：**不要**给工作台加 KPI 卡/图表大屏——既有拍板正确，`ui-2.0-handoff.md` Phase 5 的 KPI 行计划已被正确地否决执行。

### 2.5 交互设计（九态覆盖）

| 状态 | 覆盖情况 |
|---|---|
| Hover | ✅ 桌面齐（表格行、卡片 `st-card--interactive`）；🔴 一处纯 hover 依赖（IH-2） |
| Focus | 🟡 仅 AppButton 挂 `.st-focus`；大量原生 button/chips/tabbar 无 focus-visible（IH-3） |
| Active | ✅ 按钮 `active:` 态齐；卡片按压缩放 0.99 |
| Disabled | ✅ `disabled:opacity-40` + pointer-events-none（AppButton.vue:52） |
| Loading | 🟡 形态三分：骨架屏（3 处）/ spinner / 全屏遮罩（Board.vue:886 仍在用，违反本项目自己的「禁全屏遮罩」黑闪硬规矩）（IH-4） |
| Empty | 🟡 AppEmpty 是「唯一口径」但 MyApplications、HelpCenter 手写空态（IH-5） |
| Error | 🟡 409 有专属文案、失败保留旧内容——好；但重试入口只有 2 处，部分错误文案不满足三段式（见 §2.7） |
| Success | ✅ toast + 计数反馈（「已更新 N 条」） |
| Partial Success | 🔴 批量改状态 skipped 黑洞（见 §2.6）；✅ AI 导入结果页是正面范本 |

| # | 发现 | 证据 |
|---|---|---|
| IH-1 ✅ | **确认弹窗体系健康**：`appConfirm()` 全局唯一口径，底部弹层、按钮上下堆叠物理防误触、危险动作红底。归档/拒绝等可逆操作用确认弹窗 + 对向恢复入口（归档↔重新发布、拒绝↔恢复待审核）的组合是合理的——**不需要引入 undo toast 推翻现有模式**，只要求危险文案继续点名对象（现有「归档后订单将不在橱窗展示」已是范本）。 | AppConfirm.vue:3-4、OrdersList.vue:224-255 |
| IH-2 🔴 | **纯 hover 依赖**：审核页订单上下文条的「查看完整信息 / 编辑订单 →」提示 `opacity-0 group-hover:opacity-100`，触屏（中介的主力设备）上永远不可见。该提示还承载着「这整条可以点」的可供性。 | ApplicationsReview.vue:580-582 |
| IH-3 🟡 | **focus-visible 只覆盖 AppButton**；`.st-focus` 存在但没推广。 | components.css:38-42、AppButton.vue:52 |
| IH-4 🟡 | **两套 toast 皮肤并存**：App.vue:48-62 顶部深色胶囊 vs main.css 白底胶囊，谁生效取决于选择器权重，属于换肤遗留债务。 | App.vue:48-62、styles/main.css |
| IH-5 🟡 | Drawer/Modal 全部直接用 Vant popup（无统一入口），`AppDrawer` 死代码；现状可用，统一优先级低。 | — |

### 2.6 批量操作（B 端最高频杠杆动作）

已有的好底子：桌面勾选即出批量条 + 快捷键（`/` `b` `Ctrl+A` `Esc` `r`）；移动端显式批量模式 + 底部固定条；刷新后失效勾选自动清理；AI 导入侧的批量发布防护（blocked 自动移出勾选 + 4 秒说明 toast + CTA 只计可创建数）是全项目的部分成功处理范本。

| # | 发现 | 证据 |
|---|---|---|
| BO-1 🔴 | **skipped 结果黑洞（全审计最重问题）**：后端 `batch_update_status` 返回 `{updated, skipped}`（routers/v1/orders.py:638-639，前端类型 `BatchStatusUpdateResponse` 同步有 skipped 字段），前端只读 `updated` 弹「已更新 N 条」。**被跳过的订单是哪些、为什么跳过、能不能重试——用户完全不知道**，中介会以为全部成功，直到发现漏网之单。对照 BatchImport 结果页（成功 N + 唤醒 M + 跳过 K 名单 + 重试入口），同一产品里两种标准。 | OrdersList.vue:203-218 |
| BO-2 🟡 | **影响预告缺失**：批量确认弹窗只有标题 +「将处理 N 条」，不说明这 N 条当前处于什么状态、将变成什么状态。中介批量操作的对象常常是混状态集合。 | OrdersList.vue:203-208 |

### 2.7 错误处理

拦截器层健康：401 统一登出+跳转、GET 断网 400ms 自动重试一次、业务错误由调用方 `getApiErrorMessage` 就地呈现（支持 FastAPI 422 detail 拼接）。OrderWorkspace 的 409 专属文案（「订单状态已更新，请刷新后继续操作」）是三段式的正确示范。

| # | 发现 | 证据 |
|---|---|---|
| ER-1 🟡 | **错误文案大量只说一半**：「保存失败」（EditOrderPopup.vue:99）、「批量操作失败」（OrdersList.vue:218）、「看板加载失败，请重试」——不满足「发生了什么 + 为什么 + 怎么办」三段式，用户看到后不知道下一步。 | 各处 |
| ER-2 🟡 | **重试入口覆盖率低**：全库仅 OrderDetail「重新加载」与 Board 地图刷新两处；MyApplications 失败仅 toast，页面停在空白。 | MyApplications.vue:48-54 |

### 2.8 表单与输入

| # | 发现 | 证据 |
|---|---|---|
| FM-1 🟠 | **校验模式原始**：全库（除 Login）为「提交时命令式校验 + toast」，错误不落在字段旁；无必填标记；多字段错误只能逐次提交逐次发现。Login.vue 的 `:error-message` 内联持久错误是仓库内已有的正确范本。 | Login.vue:237-275（范本）；EditOrderPopup.vue:71-103 |
| FM-2 🟠 | **EditOrderPopup 三个具体伤**：① 必填项（年级科目/课酬/展示地址）无星标，靠禁用保存键+toast；② 经纬度暴露为裸数字输入框（中介不可能手填）；③ 失败统一「保存失败」，不指字段。这是中介修正 AI 解析错误的高频弹层，输入效率直接决定录单吞吐。 | EditOrderPopup.vue:71-131 |
| FM-3 ✅ | **AI 导入的「表单」不需要改**：无传统必填标记，但三级分诊标签 + 字段级状态/原因（「原文未写明频次，请人工确认」）+ 即时费用试算 + 「低于最低定金」的修复指引，实际承担了必填沟通职责，且比星标更高级。**保护，不许倒退。** | BatchImport.vue:374-468 |
| FM-4 🟢 | **无草稿保存**：注册/简历/编辑订单中断即丢。用户量级小，暂缓（OB-2）。 | — |
| FM-5 ✅ | 防重复提交全覆盖：`useAsyncAction` + 按钮 loading/disabled + 文案切换（「登录中.../保存中...」）。 | useAsyncAction.ts:14-24 |

### 2.9 可访问性

已有的好底子：状态一律「色 + 文字」（AppStatusBadge/chip 文字标签），不单靠颜色；token 文件自带 WCAG 实测矩阵与「DEFAULT 档不做文字色」的边界声明；实心白字仅限 deep 档的纪律（accent/warning 永不白字底）。

| # | 发现 | 证据 |
|---|---|---|
| A11Y-1 🔴 | **触控目标**：投递卡动作按钮 `py-1` 实高约 26-28px、取消投递与「查看订单详情」同行竞争点击区；全库无最小触点约束（AppButton sm=32px 也低于 44px 常规）。中介/教师在手机上完成核心操作，这不是合规洁癖，是误触率问题。 | MyApplications.vue:281-289、AppButton.vue:40-44 |
| A11Y-2 🔴 | **字号下限破防**：9px/10px 实存（见 VH-1），移动端读图距离下不可读。 | Board.vue:421、MyApplications.vue:196 |
| A11Y-3 🟡 | **键盘可达性**：桌面快捷键仅 OrdersList 有（是亮点）；但 Tab 遍历全站无视觉焦点（IH-3），B 端桌面中介用键盘提速的场景会失效。 | OrdersList.vue:122-190 |
| A11Y-4 🟢 | aria 仅 27 处（label/hidden 两种）；toast 无 live region、自绘弹层焦点管理未验证。用户量级下暂缓（OB-3），随 A11Y-1/2 顺带修 label 缺失即可。 | 全库统计 |

### 2.10 AI UI（可解释性专项）

**结论：导入侧是行业标准之上的范本，推荐侧有明确缺口，方向不需要改。**

| # | 发现 | 证据 |
|---|---|---|
| AI-1 ✅ | **AI 导入可解释性（保护对象）**：三级分诊（可直接确认/待确认/无法创建）+ 定性置信度（高/中/AI 补全，红线「绝不生成数值百分比」）+ 字段级状态与原因 + 全部可改 + raw_text 存档不受影响 + 分段失败如实计数 + loading 诚实（「通常需要 10~30 秒」，不伪造进度）。这七条正好命中外部 Skills 对「AI UI」的全部要求。 | BatchImport.vue:374-565、aiImport.ts:44-109、AIImportProgress.vue:6-9 |
| AI-2 🟠 | **B 端推荐零解释**：`RecommendationExplainCard`（六维分数 + 后端 reasons 原文）只接在 C 端订单卡上；B 端 `TeacherMatchPopup` 里中介看到的只有排序结果（科目匹配 badge/距离/成交数/评分），**没有「为什么推荐 TA」**。中介挑人是要向家长解释的决策，理由缺失直接影响采用与信任；且解释数据结构与组件都已存在，纯接线问题。 | TeacherMatchPopup.vue:79-125、RecommendationExplainCard.vue:31-63 |
| AI-3 ✅ | **AI 紫使用纪律正确**：`--st-ai` 限定 AI 场景（导入步指示/解析态），未污染全局主色——恰好符合 OJO「反 AI 通用脸」检查（本产品全局无紫蓝渐变/玻璃拟态/科幻 UI，30 秒扫描零命中）。 | design-tokens.css:162-168 |
| AI-4 ✅ | 推荐数据缺失时 explanation 为 null「不放假默认值」（recommendation.ts:4-7）——诚实性正确，**不需要改**。 | — |

---

## 3. 观察项（本轮不动，留档）

| # | 内容 | 触发条件 |
|---|---|---|
| OB-1 | 移动审核页左栏 `w-40` 标题截断较狠 | 真实中介反馈找不到目标订单时再放宽 |
| OB-2 | 长表单草稿保存（注册/简历/编辑订单） | Pilot 用户反馈中断丢失后再做 |
| OB-3 | toast aria-live、弹层焦点陷阱、读屏 | 有无障碍诉求或 B 端规模化后 |
| OB-4 | 键盘快捷键推广到财务/审核页 | OrdersList 快捷键被真实使用后 |
| OB-5 | 移动端教员管理入口（IA-2） | 新中介 onboarding 反馈找不到时 |
| OB-6 | C 端简历编辑双形态统一（TF-2） | 与 Profile 相关改动同窗口处理 |

---

## 4. 必须保护的既有设计（「不要动」清单的依据）

1. **Token 三层体系**：design-tokens.css（含 -rgb 伴生规则）→ tailwind 语义类 → `.st-*` 基类 + check-tokens 护栏。换主题只改一个文件的能力是资产。
2. **statusTone 单一出口**：4 色族 × 4 档、同名状态同色、推进档位语义、WCAG 实测注释。
3. **Workbench 的 Todo-centered 结构**：问候 → 行动队列 → 本月经营（三个数）→ 本月资金（四行）→ 录单入口 → 最近订单。**禁止退化成 KPI 卡 + 图表的数据大屏。**
4. **AI 导入的七件套可解释方案**（AI-1）。
5. **财务三色口径**（收入 +绿 / 退款 −红 / 没收琥珀不计净额，带符号不靠色）与账本 18/20px 基线、移动账本/桌面六列的双形态。
6. **orderActions 状态机驱动 CTA**（前端不判权、后端把关红线）与 OrderWorkspace 的 409/内容保留/返回键模式——它应该被推广，而不是被改动。
7. **AppConfirm 堆叠按钮确认层**、C 端悬浮胶囊 tabbar、AdminShell 桌面壳（1024px 切换）、导入页「空旷 vs 高级」框架。
8. **黑闪硬规矩**（禁全屏黑遮罩/遮罩必淡入/禁 backdrop-blur/滚动条常驻）——审计发现 Board.vue:886 是现存违例，属于「执行未覆盖既有规矩」，不是规矩本身要改。

---

## 5. 问题总登记表

| ID | 维度 | 摘要 | 严重度 | 去向 |
|---|---|---|---|---|
| BO-1 | 批量 | skipped 结果黑洞，无定位/重试 | 🔴 P0 | Plan #1 |
| IA-1 | 架构 | B 端 4 页返回键硬编码回工作台 | 🔴 P0 | Plan #2 |
| VH-1 | 视觉 | 字阶无 token，228 处任意值，最小 9px | 🔴 P0 | Plan #3 |
| A11Y-1 | 可访问 | 移动触控目标 26-28px | 🔴 P0 | Plan #4 |
| IH-2 | 交互 | 审核页纯 hover 提示，触屏不可达 | 🔴 P0 | Plan #5 |
| FM-1/2 | 表单 | toast 式校验、必填无标记、错误不指字段 | 🟠 P1 | Plan #6 |
| AI-2 | AI UI | B 端推荐无解释卡 | 🟠 P1 | Plan #7 |
| TF-1 | 任务流 | C 端「联系中介」复制动作深两层 | 🟠 P1 | Plan #8 |
| IH-4 | 交互 | 两套 toast 皮肤并存 | 🟡 P1 | Plan #9 |
| IH-4b | 交互 | Loading 形态三分 + Board 全屏遮罩违例 | 🟡 P1 | Plan #10 |
| IH-3 | 交互 | focus-visible 仅 AppButton | 🟡 P1 | Plan #11 |
| BO-2 | 批量 | 批量确认无影响预告 | 🟡 P1 | Plan #12 |
| ER-1/2 | 错误 | 文案三段式缺失 + 重试入口稀疏 | 🟡 P1 | Plan #13 |
| IH-5 | 交互 | 空态未统一到 AppEmpty | 🟡 P1 | Plan #14 |
| VH-3 | 视觉 | 看板列头状态表达弱 | 🟢 P2 | Plan #15 |
| VH-4 | 视觉 | 死代码 AppStatCard/AppDrawer/AppPageHeader | 🟢 P2 | Plan #16 |

> P2 与观察项（OB-1~6）不在本期实施范围，详见实施计划「暂不动」章节。

---

## 附录 A：外部 Skills 参照标准摘要

审计采用的标准来自用户指定的 5 个公开 Skills 仓库（已全部在线研读原文，未安装、未改动业务代码）：

1. **ui-ux-pro-max**（nicohodt）：十级优先级规则（无障碍/触控为 CRITICAL）、表单规范（label 可见、错误落字段下、blur 校验、错误=原因+修复）、三层 token 架构、七阶段 Design Review 流程。
2. **OJO-Design-Skills**（touchine-ojo）：Convention Track vs Innovation Track（B 端工具默认 Convention）、Anti-AI 30 秒扫描（紫黑底/玻璃拟态/渐变按钮，命中 3 项即打回）、色彩面积预算（primary 8-12%）、8 态交互完整性、Honest Copy。
3. **design-skills**（cuellarfr）：设计评审 9 步框架（先答「用户是谁/要做什么/在哪一步/业务约束」）、严重度 0-4 分级、反馈公式（问题+违反原则+影响+建议）、Doherty 阈值（<400ms 反馈）、错误信息四段式。
4. **ux-ui-design-taste**（arez-xd）：运营型 SaaS 旋钮（density 7-9/motion 1-3）、质量底线一票否决清单、每屏一个焦点、字阶 3-4 级纪律、容器四选一、AI-Slop 特征清单。
5. **ui-skills**（adamtossell）：Scan→Diagnose→Fix（不重写）的存量项目改造法、动效时长体系与性能硬规则（只动画 transform/opacity、reduced-motion 必做）。

**本审计的评分口径**：严重度 🔴 P0 = 阻碍任务完成或高频摩擦；🟠 P1 = 显著影响效率/信任；🟡 P1 = 一致性/规范债；🟢 P2 = 打磨项。全部发现均附 file:line 证据，无推测性指控。
