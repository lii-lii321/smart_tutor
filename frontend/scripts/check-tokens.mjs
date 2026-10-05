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

// 裸 hex 护栏（2026-10-05 外审补盲）：类名护栏拦不住 <style> 块与 Vant color prop
// 里的裸 hex（换主题会漏色）。只扫 .vue；design-tokens.css 是唯一来源，天然豁免。
// 白名单：#fff/#ffffff（纯白与主题无关）。其余一律走 var(--st-*)。
const HEX_PATTERN = /#[0-9a-fA-F]{3,8}\b/g;
const HEX_ALLOW = new Set(["#fff", "#ffffff"]);
const HEX_SUGGEST =
  "裸 hex 会让该页面在换主题时漏色：CSS 里用 var(--st-*)，" +
  "Vant color prop 传 var(--st-*) 字符串（如 color=\"var(--st-text-secondary)\"）。纯白 #fff 允许。";

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
  const isVue = file.endsWith(".vue");
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
    if (isVue) {
      HEX_PATTERN.lastIndex = 0;
      const hexHits = (line.match(HEX_PATTERN) || []).filter((h) => !HEX_ALLOW.has(h.toLowerCase()));
      if (hexHits.length) {
        violations.push({
          file: relative(join(ROOT, ".."), file).replace(/\\/g, "/"),
          line: i + 1,
          hits: [...new Set(hexHits)],
          text: line.trim().slice(0, 90),
          hex: true,
        });
      }
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
console.error(HEX_SUGGEST);
console.error("唯一来源：frontend/src/styles/design-tokens.css");
process.exit(1);
