# ADR-0006: 设计系统收敛为 Navy + Slate + Warm Paper（Design Token 架构）

- 状态：**已接受（Accepted）**——Batch 01 已实施
- 日期：2026-09-23
- 关联代码：`frontend/src/styles/design-tokens.css`、`frontend/tailwind.config.js`、
  `frontend/index.html`、`frontend/src/components/ui/*`

## 背景

前端视觉在 0.9.0 前后经历三次叠加，互不知情：Tailwind token 层是 AI 蓝
（`primary-600 = #2563eb`）、CSS 变量层是 navy/米白（`--navy/--paper`）、
灰主题批次又把 Vant 主色打成 `slate-700`；页面另散落 399 处裸写
`slate-*` 与 9 个文件的硬编码 hex。结果：换一次主题就要全项目扫射
（灰主题批次靠十几个补丁脚本逐文件 patch 完成），且"高级灰"与品牌
识别之间始终没有拍板。

## 决策

1. **主色拍板：Navy + Slate + Warm Paper**，不做纯灰（产品是人与人撮合的
   交易平台，全灰偏冷硬后台感），也不回到 AI 蓝。
   - Navy（#1E3558 系）：Logo、主 CTA、激活态、关键导航、重要数据；
   - Slate 系：正文、描边、次级按钮、Tab、后台中性件；
   - Warm Paper（#FAF9F7）：页面底色；
   - AI 紫（#8B7CF6）：仅限 AI 解析 / 智能推荐 / AI 状态，禁止做全局主色。
2. **Token 单一来源**：新增 `src/styles/design-tokens.css`（`--st-*`，hex +
   rgb 三元组双份，rgb 供 Tailwind `<alpha-value>` 透明度修饰符）；
   `tailwind.config.js` 只做 Token 消费者（brand/ai/page/surface/ink/
   secondary/muted/default/success/warning/danger/info），禁止新增第二套
   硬编码色。换主题 = 只改 tokens 文件。
3. **存量兼容桥接**：旧 CSS 变量（`--ink/--navy/--line/...`）全部重指到
   Token；Tailwind `primary-*` 尺度重指 navy（原 38 处消费点从 AI 蓝
   一次性转为品牌色，页面零改动）。Batch 06 清理消费点后删除桥接层。
4. **裸 slate 迁移分批**：399 处不一次性人工替换（回归风险），仅随
   Batch 02-06 页面重构逐页迁移到语义类。
5. 组件层新增 8 个基础件（AppButton/AppCard/AppBadge/AppStatusBadge/
   AppPageHeader/AppStatCard/AppEmpty/AppDrawer），其中状态徽标只从
   `constants/orderStatus.ts` 读颜色与文案，业务状态口径不变。
6. 暗色模式 / 多租户皮肤 / 主题市场：商业化阶段之前不做。

## 后果

- 视觉收敛有了"尺子"：后续批次页面重构只能消费语义类，不会再出现
  三套颜色系统各自为政；
- `index.html` 保留一份 navy 字面量作首屏兜底（防 FOUC），以注释声明
  唯一口径在 tokens 文件；
- 过渡期内新旧页面短暂混色（存量 slate 按钮 + 新 navy CTA），按批次
  消除，属预期中间态。

## 备选与否决

- **纯高级灰（延续灰主题批次）**：失去品牌温度，像内部后台，否决；
- **立即全量迁移 399 处裸 slate**：纯机械替换、视觉回归面不可控，否决，
  改为随页面重构分批；
- **引入 CSS-in-JS / UI 框架换血**：超出当前需求，违背既有栈约束，否决。
