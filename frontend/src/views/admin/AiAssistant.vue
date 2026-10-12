<script setup lang="ts">
/**
 * AI 助手（阶段 1b）：知识库问答（带引用）+ 知识文档管理。
 * 诚实性约定：后端无依据时如实回答，前端不美化空答案；
 * 回答为 LLM 生成内容，渲染一律走 renderAnswerHtml（marked+DOMPurify 单点）。
 */
import { nextTick, onMounted, ref } from "vue";
import { showToast } from "vant";

import { aiApi, type Citation, type KnowledgeDoc } from "@/api/ai";
import AdminShell from "@/components/admin/AdminShell.vue";
import AppButton from "@/components/ui/AppButton.vue";
import { renderAnswerHtml } from "@/components/business/ai/assistant";
import { appConfirm } from "@/composables/appConfirm";
import { useSmartBack } from "@/composables/useSmartBack";
import { getApiErrorMessage } from "@/utils/apiError";

const { goBack } = useSmartBack("/admin/dashboard");

const activeTab = ref<"chat" | "kb">("chat");

// ── 对话 ──
interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  latencyMs?: number | null;
}
const messages = ref<ChatMessage[]>([]);
const question = ref("");
const asking = ref(false);
const messagesEnd = ref<HTMLElement | null>(null);

const SAMPLE_QUESTIONS = ["教员试课后家长要考虑几天，我该怎么跟进？", "信息费和定金是怎么算的？", "怎么提高投递响应率？"];

async function scrollToBottom() {
  await nextTick();
  messagesEnd.value?.scrollIntoView({ behavior: "smooth", block: "end" });
}

async function handleAsk(raw?: string) {
  const text = (raw ?? question.value).trim();
  if (!text || asking.value) return;
  question.value = "";
  messages.value.push({ role: "user", text });
  asking.value = true;
  scrollToBottom();
  try {
    const answer = await aiApi.ask(text);
    messages.value.push({
      role: "assistant",
      text: answer.answer,
      citations: answer.citations,
      latencyMs: answer.latency_ms,
    });
  } catch (e) {
    showToast(getApiErrorMessage(e, "AI 服务暂时不可用，请稍后重试"));
  } finally {
    asking.value = false;
    scrollToBottom();
  }
}

// ── 知识库 ──
const docs = ref<KnowledgeDoc[]>([]);
const docsLoading = ref(false);
const docsError = ref(false);
const showCreate = ref(false);
const creating = ref(false);
const form = ref({ title: "", content: "" });

const STATUS_META: Record<string, { text: string; cls: string }> = {
  ready: { text: "已就绪", cls: "bg-success-soft text-success" },
  failed: { text: "处理失败", cls: "bg-danger-soft text-danger" },
  pending: { text: "处理中", cls: "bg-warning-soft text-warning" },
};

function statusMeta(doc: KnowledgeDoc) {
  return STATUS_META[doc.status] ?? { text: doc.status, cls: "bg-surface-soft text-muted" };
}

function timeText(doc: KnowledgeDoc) {
  return (doc.updated_at || doc.created_at || "").slice(0, 10);
}

async function loadDocs() {
  docsLoading.value = true;
  docsError.value = false;
  try {
    docs.value = (await aiApi.listDocuments()).items;
  } catch {
    docsError.value = true;
  } finally {
    docsLoading.value = false;
  }
}

async function handleCreate() {
  const title = form.value.title.trim();
  const content = form.value.content.trim();
  if (!title || !content) {
    showToast("请填写标题和正文");
    return;
  }
  creating.value = true;
  try {
    const doc = await aiApi.createDocument(title, content);
    showCreate.value = false;
    form.value = { title: "", content: "" };
    if (doc.status === "failed") {
      showToast(`上传成功但处理失败：${doc.fail_reason ?? "未知原因"}`);
    } else {
      showToast("已上传并完成向量化");
    }
    await loadDocs();
  } catch (e) {
    showToast(getApiErrorMessage(e, "上传失败，请稍后重试"));
  } finally {
    creating.value = false;
  }
}

async function handleDelete(doc: KnowledgeDoc) {
  const ok = await appConfirm({
    title: "删除知识文档",
    message: `「${doc.title}」删除后 AI 问答将立即检索不到该内容。`,
    confirmText: "删除",
  });
  if (!ok) return;
  try {
    await aiApi.deleteDocument(doc.id);
    showToast("已删除");
    await loadDocs();
  } catch (e) {
    showToast(getApiErrorMessage(e, "删除失败，请稍后重试"));
  }
}

onMounted(loadDocs);
</script>

<template>
  <AdminShell>
    <van-nav-bar title="AI 助手" left-arrow @click-left="goBack" />

    <main class="mx-auto w-full max-w-3xl px-4 pt-3">
      <van-tabs v-model:active="activeTab" shrink>
        <van-tab title="问答" name="chat">
          <!-- 空态引导：回答只基于知识库，先给示例问题 -->
          <div v-if="messages.length === 0" class="mt-4 rounded-xl border border-default bg-white p-5 text-center">
            <span class="inline-flex items-center gap-1.5 rounded-full bg-ai-soft px-2.5 py-1 text-caption font-semibold text-ai-deep">
              <span class="h-1.5 w-1.5 rounded-full bg-ai" />
              智派 AI 助手
            </span>
            <p class="mt-3 text-sm font-semibold text-primary">问我业务规则、流程与产品用法</p>
            <p class="mx-auto mt-1 max-w-xs text-xs leading-5 text-secondary">
              回答基于知识库文档并附来源；知识库没有的内容我会如实说明
            </p>
            <div class="mt-4 flex flex-wrap justify-center gap-2">
              <button
                v-for="sample in SAMPLE_QUESTIONS"
                :key="sample"
                class="rounded-full border border-default px-3 py-1.5 text-caption text-secondary hover:bg-surface-soft"
                @click="handleAsk(sample)"
              >
                {{ sample }}
              </button>
            </div>
          </div>

          <!-- 消息流 -->
          <div v-else class="mt-4 space-y-3">
            <div
              v-for="(msg, i) in messages"
              :key="i"
              :class="msg.role === 'user' ? 'flex justify-end' : 'flex justify-start'"
            >
              <div
                class="max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-6"
                :class="msg.role === 'user' ? 'bg-ink text-white' : 'border border-default bg-white text-primary'"
              >
                <!-- 用户消息纯文本回显；助手消息走消毒渲染单点 -->
                <template v-if="msg.role === 'user'">{{ msg.text }}</template>
                <!-- eslint-disable-next-line vue/no-v-html -- 回答经 renderAnswerHtml 转义（business/ai/assistant.ts），内嵌 HTML 已惰性化 -->
                <div v-else class="assistant-answer" v-html="renderAnswerHtml(msg.text)" />
                <div v-if="msg.citations?.length" class="mt-2 border-t border-default pt-2">
                  <div class="text-caption font-medium text-muted">来源</div>
                  <div
                    v-for="citation in msg.citations"
                    :key="citation.index"
                    class="mt-1 flex items-start gap-1.5 text-caption text-secondary"
                  >
                    <span class="shrink-0 rounded bg-surface-soft px-1 font-semibold text-muted">[{{ citation.index }}]</span>
                    <span class="min-w-0">
                      <span class="font-medium text-secondary">{{ citation.title }}</span>
                      <span class="text-muted"> · {{ citation.snippet }}…</span>
                    </span>
                  </div>
                </div>
                <div v-if="msg.latencyMs" class="mt-1 text-right text-caption text-muted">
                  {{ msg.latencyMs }}ms
                </div>
              </div>
            </div>
            <!-- 诚实加载态：一个小圆点，不伪造打字机/进度 -->
            <div v-if="asking" class="flex justify-start">
              <div class="rounded-2xl border border-default bg-white px-4 py-3">
                <span class="inline-flex items-center gap-1.5 text-caption text-muted">
                  <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-ai" />
                  正在检索知识库并组织回答…
                </span>
              </div>
            </div>
            <div ref="messagesEnd" />
          </div>

          <div class="h-24" />
        </van-tab>

        <!-- 知识库管理 -->
        <van-tab title="知识库" name="kb">
          <div class="mt-4 flex items-center justify-between">
            <p class="text-xs text-muted">文档向量化后即可被 AI 助手检索引用</p>
            <AppButton size="sm" @click="showCreate = true">上传文档</AppButton>
          </div>

          <div v-if="docsError" class="mt-4 rounded-xl border border-default bg-white p-8 text-center">
            <p class="text-sm text-muted">知识库加载失败：网络或服务暂时不可用</p>
            <button class="mt-3 rounded-lg border border-default px-4 py-2 text-body text-secondary" @click="loadDocs">
              重试
            </button>
          </div>

          <div v-else-if="!docsLoading && docs.length === 0" class="mt-4 rounded-xl border border-default bg-white p-8 text-center">
            <p class="text-sm text-muted">还没有知识文档</p>
            <p class="mx-auto mt-1 max-w-xs text-xs leading-5 text-secondary">
              上传你的中介业务规范、常见问答、收费规则，AI 即可据此回答团队问题
            </p>
            <button class="mt-3 rounded-full bg-ink px-4 py-2 text-body font-medium text-white" @click="showCreate = true">
              上传第一份文档
            </button>
          </div>

          <div v-else class="mt-3 space-y-2">
            <article
              v-for="doc in docs"
              :key="doc.id"
              class="rounded-xl border border-default bg-white px-4 py-3"
            >
              <div class="flex items-start gap-3">
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <span class="text-sm font-semibold text-primary">{{ doc.title }}</span>
                    <span class="rounded-full px-1.5 py-0.5 text-caption font-medium" :class="statusMeta(doc).cls">
                      {{ statusMeta(doc).text }}
                    </span>
                    <span v-if="doc.tenant_id === null" class="rounded-full bg-surface-soft px-1.5 py-0.5 text-caption text-muted">
                      平台
                    </span>
                  </div>
                  <div class="mt-1 text-xs text-secondary">
                    {{ doc.chunk_count }} 个片段
                    <template v-if="timeText(doc)"> · 更新于 {{ timeText(doc) }}</template>
                  </div>
                  <p
                    v-if="doc.status === 'failed' && doc.fail_reason"
                    class="mt-1.5 rounded-md bg-danger-soft px-2 py-1 text-caption text-danger"
                  >
                    {{ doc.fail_reason }}——可删除后重新上传
                  </p>
                </div>
                <button
                  v-if="doc.tenant_id !== null"
                  class="shrink-0 rounded-md border border-default px-2 py-1 text-xs text-secondary hover:bg-surface-soft"
                  @click="handleDelete(doc)"
                >
                  删除
                </button>
              </div>
            </article>
          </div>
          <div class="h-8" />
        </van-tab>
      </van-tabs>
    </main>

    <!-- 底部提问条（问答页固定；知识库页隐藏） -->
    <div
      v-if="activeTab === 'chat'"
      class="fixed inset-x-0 bottom-[50px] z-20 border-t border-default bg-white px-4 py-3 lg:bottom-0"
    >
      <div class="mx-auto flex w-full max-w-3xl items-end gap-2">
        <textarea
          v-model="question"
          rows="1"
          class="max-h-24 min-h-[40px] flex-1 resize-none rounded-xl border border-default bg-surface-soft/50 px-3 py-2.5 text-body leading-5 text-primary focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-default"
          placeholder="输入业务问题，回车发送"
          @keydown.enter.exact.prevent="handleAsk()"
        />
        <AppButton size="md" :disabled="asking || !question.trim()" @click="handleAsk()">
          {{ asking ? "思考中…" : "发送" }}
        </AppButton>
      </div>
    </div>

    <!-- 上传文档弹层 -->
    <van-popup v-model:show="showCreate" position="bottom" round class="px-4 pb-6 pt-4">
      <h3 class="text-base font-semibold text-primary">上传知识文档</h3>
      <p class="mt-1 text-xs text-secondary">支持直接粘贴文本；上传后自动切分并向量化</p>
      <label class="mt-4 block">
        <span class="text-xs font-medium text-secondary">标题</span>
        <input
          v-model="form.title"
          maxlength="100"
          class="mt-1 w-full rounded-lg border border-default bg-surface-soft/50 px-3 py-2 text-body text-primary focus:border-brand-500 focus:bg-white focus:outline-none"
          placeholder="如：试课跟进规范"
        />
      </label>
      <label class="mt-3 block">
        <span class="text-xs font-medium text-secondary">正文</span>
        <textarea
          v-model="form.content"
          rows="8"
          maxlength="50000"
          class="mt-1 w-full resize-none rounded-lg border border-default bg-surface-soft/50 px-3 py-2 text-body leading-6 text-primary focus:border-brand-500 focus:bg-white focus:outline-none"
          placeholder="粘贴业务规范、常见问答、流程说明…"
        />
      </label>
      <div class="mt-4 flex gap-3">
        <AppButton size="md" variant="secondary" class="flex-1" @click="showCreate = false">取消</AppButton>
        <AppButton size="md" class="flex-1" :disabled="creating || !form.title.trim() || !form.content.trim()" @click="handleCreate">
          {{ creating ? "处理中…" : "上传并向量化" }}
        </AppButton>
      </div>
    </van-popup>
  </AdminShell>
</template>

<style scoped>
/* 助手回答的 markdown 基础排版：克制、跟随正文排版口径 */
.assistant-answer :deep(p) {
  margin: 0.25rem 0;
}
.assistant-answer :deep(ul),
.assistant-answer :deep(ol) {
  margin: 0.25rem 0;
  padding-left: 1.25rem;
  list-style: disc;
}
.assistant-answer :deep(ol) {
  list-style: decimal;
}
.assistant-answer :deep(code) {
  background: var(--st-surface-soft);
  border-radius: 4px;
  padding: 0 4px;
  font-size: 0.85em;
}
</style>
