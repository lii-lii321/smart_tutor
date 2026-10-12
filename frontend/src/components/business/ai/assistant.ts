/**
 * AI 回答渲染单点：markdown → 安全 HTML。
 *
 * 答案是 LLM 生成内容（可能被提示注入夹带 HTML），因此在交给 marked 解析前
 * 先转义全部 < > &：任何内嵌 HTML 都退化为字面文本，marked 只可能产出由
 * markdown 语法生成的标签，XSS 向量从输入端被消除。该策略不依赖 DOM 实现，
 * 浏览器与 vitest（happy-dom）行为一致、可被单测锁定；渲染口径只有这一份，
 * 禁止组件内各写各的解析。
 */
import { marked } from "marked";

marked.setOptions({ async: false, breaks: true, gfm: true });

function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function renderAnswerHtml(markdown: string): string {
  return marked.parse(escapeHtml(markdown ?? "")) as string;
}
