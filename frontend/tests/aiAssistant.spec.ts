/**
 * AI 助手渲染口径测试：回答 markdown 走 marked+DOMPurify 单点，
 * LLM 生成内容（可能被提示注入夹带标记）必须消毒后才能进 v-html。
 */
import { describe, expect, it } from "vitest";

import { renderAnswerHtml } from "@/components/business/ai/assistant";

describe("renderAnswerHtml 回答渲染", () => {
  it("渲染基本 markdown（加粗/列表/引用编号原样保留）", () => {
    const html = renderAnswerHtml("**加粗** 与 [1]\n\n- 第一点\n- 第二点");
    expect(html).toContain("<strong>加粗</strong>");
    expect(html).toContain("<li>第一点</li>");
    expect(html).toContain("[1]");
  });

  it("内嵌 HTML 全部转义为惰性文本（LLM 输出不可信）", () => {
    const html = renderAnswerHtml(
      '正常文字<script>alert(1)</script><img src=x onerror="alert(1)"><a href="javascript:alert(1)">链接</a>',
    );
    // 任何尖括号标签都不允许以裸形态出现在产物里
    expect(html).not.toContain("<script");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("<a ");
    expect(html).toContain("&lt;script&gt;");
    expect(html).toContain("正常文字");
  });

  it("空输入返回空串不抛错", () => {
    expect(renderAnswerHtml("")).toBe("");
  });
});
