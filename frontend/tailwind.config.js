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
        success: { DEFAULT: token("success"), soft: token("success-soft") },
        warning: { DEFAULT: token("warning"), soft: token("warning-soft") },
        danger: { DEFAULT: token("danger"), soft: token("danger-soft") },
        info: { DEFAULT: token("info"), soft: token("info-soft") },
      },
      boxShadow: {
        card: "var(--st-shadow-sm)",
        elevated: "var(--st-shadow-lg)",
        floating: "0 -6px 20px rgba(23, 24, 28, 0.07)",
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
