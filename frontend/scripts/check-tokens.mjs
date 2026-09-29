#!/usr/bin/env node
/**
 * 设计令牌护栏：禁止在视图/组件里裸写 Tailwind 内置色系。
 *
 * 为什么不用 ESLint 的 no-restricted-syntax：
 *   该规则基于 AST selector 匹配，而 vue-eslint-parser 把模板静态属性放在
 *   ast.templateBody 下，ESLint 的 selector 遍历进不去 —— 实测 .vue 模板里的
 *   class="bg-red-500" 完全拦不住（.ts 里的字符串能拦）。护栏如果看起来在、
 *   实际不生效，比没有护栏更危险，所以改成直接扫源码。
 *
 * 允许的语义色（来自 tailwind.config.js，源自 design-tokens.css）：
 *   brand / ai / surface / paper / primary / secondary / muted /
 *   default / strong / success / warning / danger / info
 *
 * 状态徽标一律经 src/constants/statusTone.ts 取色，视图层不得自己拼。
 *
 * 用法：node scripts/check-tokens.mjs   有违规则 exit 1
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "..", "src");
const EXT = new Set([".vue", ".ts"]);

// Tailwind 内置色系全枚举（语义色不在此列）
const RAW_PALETTE = [
  "red", "rose", "pink", "orange", "amber", "yellow", "lime", "green",
  "emerald", "teal", "cyan", "sky", "blue", "indigo", "violet", "purple",
  "fuchsia", "slate", "gray", "zinc", "neutral", "stone", "brown",
].join("|");

const PATTERN = new RegExp(
  String.raw`\b(?:bg|text|border|ring|divide|placeholder|from|via|to|fill|stroke)` +
    String.raw`(?:-[trblxy](?:-[trblxy])?)?-(?:${RAW_PALETTE})-\d{2,3}\b`,
  "g",
);

const SUGGEST =
  "颜色一律走 design-token 语义类，如 bg-danger-soft / text-success-deep / " +
  "border-warning-mid / bg-info-soft；状态徽标请用 constants/statusTone.ts。";

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    if (entry === "node_modules" || entry === "dist" || entry.startsWith(".")) continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) yield* walk(full);
    else if (EXT.has(full.slice(full.lastIndexOf(".")))) yield full;
  }
}

const violations = [];
for (const file of walk(ROOT)) {
  const lines = readFileSync(file, "utf8").split(/\r?\n/);
  lines.forEach((line, i) => {
    PATTERN.lastIndex = 0;
    const hits = line.match(PATTERN);
    if (hits) {
      violations.push({
        file: relative(join(ROOT, ".."), file).replace(/\\/g, "/"),
        line: i + 1,
        hits: [...new Set(hits)],
        text: line.trim().slice(0, 90),
      });
    }
  });
}

if (violations.length === 0) {
  console.log("[check-tokens] OK — 全站颜色均来自 design-tokens.css");
  process.exit(0);
}

console.error(`[check-tokens] 发现 ${violations.length} 处裸写色系：\n`);
for (const v of violations) {
  console.error(`  ${v.file}:${v.line}  ${v.hits.join("  ")}`);
  console.error(`      ${v.text}`);
}
console.error(`\n${SUGGEST}`);
console.error("唯一来源：frontend/src/styles/design-tokens.css");
process.exit(1);
