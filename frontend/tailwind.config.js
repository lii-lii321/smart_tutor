/** @type {import('tailwindcss').Config} */

// 设计令牌唯一来源：src/styles/design-tokens.css（--st-* 变量）。
// 本文件只是 Token 的消费者：语义色一律指向 CSS 变量（rgb 三元组 +
// <alpha-value>），保证 brand/50 等继续支持 /50 透明度修饰符。
// 禁止在这里新增第二套硬编码色值。换主题 = 只改 design-tokens.css。
const token = (name) => `rgb(var(--st-${name}-rgb) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{vue,js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // 品牌海军蓝：Logo / 主 CTA / 激活态 / 关键导航 / 重要数据
        brand: {
          50: token("brand-50"),
          100: token("brand-100"),
          200: token("brand-200"),
          300: token("brand-300"),
          400: token("brand-400"),
          500: token("brand-500"),
          600: token("brand-600"),
          700: token("brand-700"),
          800: token("brand-800"),
          900: token("brand-900"),
          DEFAULT: token("brand-800"),
        },
        // UI 2.0 核心三色：墨黑动作 / 明黄品牌点缀 / 品牌蓝链接
        ink: {
          DEFAULT: token("ink"),
          soft: token("ink-soft"),
        },
        accent: {
          DEFAULT: token("accent"),
          deep: token("accent-deep"),
          soft: token("accent-soft"),
          ink: token("accent-ink"),
        },
        link: token("link"),
        // AI 专属紫：仅限 AI 解析 / 智能推荐 / AI 状态
        ai: {
          soft: token("ai-soft"),
          DEFAULT: token("ai"),
          deep: token("ai-deep"),
        },
        // 表面与页面底色
        page: token("paper"),
        surface: {
          DEFAULT: token("surface"),
          soft: token("surface-soft"),
          warm: token("warm"),
        },
        // 文字语义：text-primary（主）/ text-secondary（次）/ text-muted（弱）
        primary: token("text-primary"),
        secondary: token("text-secondary"),
        muted: token("text-muted"),
        // 描边：border-default / border-strong（选中/强调描边）
        default: token("border"),
        strong: token("border-strong"),
        // 状态色
        // 状态色：soft(浅底) / mid(推进中底) / DEFAULT(图标·色块) / deep(文字·实心底)
        // 档位职责与 WCAG 实测见 design-tokens.css 的状态色注释。
        // chip 一律 soft|mid 底 + deep 字；deep 底配白字。
        success: {
          soft: token("success-soft"),
          mid: token("success-mid"),
          DEFAULT: token("success"),
          deep: token("success-deep"),
        },
        warning: {
          soft: token("warning-soft"),
          mid: token("warning-mid"),
          DEFAULT: token("warning"),
          deep: token("warning-deep"),
        },
        danger: {
          soft: token("danger-soft"),
          mid: token("danger-mid"),
          DEFAULT: token("danger"),
          deep: token("danger-deep"),
        },
        info: {
          soft: token("info-soft"),
          mid: token("info-mid"),
          DEFAULT: token("info"),
          deep: token("info-deep"),
        },
      },
      boxShadow: {
        // shadow-sm 原先由 main.css 用 !important 全局覆写，此处接回配置层，取值不变
        sm: "var(--st-shadow-sm)",
        card: "var(--st-shadow-sm)",
        elevated: "var(--st-shadow-lg)",
        floating: "0 -6px 20px rgba(23, 24, 28, 0.07)",
      },
      // 圆角：原先 main.css 用 !important 把 rounded-xl/2xl 劫持到 token 尺度，
      // 导致 Tailwind 自身的圆角语义失效。此处改为在配置层覆写，取值与旧行为
      // 逐一对齐（xl=10px、2xl=14px），全站渲染零变化。
      // sm/md/lg 未被覆写，保持 Tailwind 默认（2/6/8px），与现状一致。
      // 3xl 此前全站未被使用，接上 --st-radius-xl 补齐缺失的第三档层级。
      borderRadius: {
        xl: "var(--st-radius-md)",
        "2xl": "var(--st-radius-lg)",
        "3xl": "var(--st-radius-xl)",
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"Segoe UI"',
          '"PingFang SC"',
          '"Hiragino Sans GB"',
          '"Microsoft YaHei"',
          '"Helvetica Neue"',
          "Arial",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
