import pluginVue from "eslint-plugin-vue";
import globals from "globals";
import tseslint from "typescript-eslint";

// 设计令牌护栏不在这里：no-restricted-syntax 基于 AST selector，
// 走不进 vue-eslint-parser 的 templateBody，.vue 模板里的 class 拦不住
// （实测只有 .ts 字符串会命中）。改用 scripts/check-tokens.mjs 扫源码，
// 由 npm run check:tokens / pre-commit / CI 强制执行。

export default tseslint.config(
  { ignores: ["dist/", "node_modules/", "src/api/schema.d.ts", "test-results/"] },
  ...tseslint.configs.recommended,
  ...pluginVue.configs["flat/recommended"],
  {
    files: ["**/*.vue"],
    languageOptions: {
      parserOptions: { parser: tseslint.parser },
    },
  },
  {
    // 声明文件里的 ambient var / 类型重导出是标准写法
    files: ["**/*.d.ts"],
    rules: {
      "no-var": "off",
      "@typescript-eslint/no-empty-object-type": "off",
    },
  },
  {
    languageOptions: {
      globals: { ...globals.browser },
    },
    rules: {
      // 工程底线基线：存量 any 先以警告暴露，逐步收敛；未用变量允许下划线前缀
      "@typescript-eslint/no-explicit-any": "warn",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      "vue/multi-word-component-names": "off",
      // 模板排版类规则关闭：格式统一交给 Prettier（npm run format），
      // 避免 lint 首次接入对存量 .vue 产生整文件重排
      "vue/max-attributes-per-line": "off",
      "vue/singleline-html-element-content-newline": "off",
      "vue/multiline-html-element-content-newline": "off",
      "vue/html-indent": "off",
      "vue/html-self-closing": "off",
      "vue/first-attribute-linebreak": "off",
      "vue/html-closing-bracket-newline": "off",
      "vue/attributes-order": "off",
    },
  }
);
