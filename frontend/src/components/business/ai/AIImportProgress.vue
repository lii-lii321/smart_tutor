<script setup lang="ts">
import { computed } from "vue";
import type { DraftTriage, DraftTriageCounts } from "./aiImport";

/**
 * AI 解析异常摘要（Batch 03 / H5）：
 * 展示"本次解析 N 条需求 → 正常/待确认/无法创建"三级分诊，并承担过滤入口。
 * 分段失败（后端 warnings）如实展示段序号与原因原文；后端未下发失败段原文片段，
 * 不在前端编造"对应原文第几段"的映射。
 */
const props = withDefaults(
  defineProps<{
    total: number;
    counts: DraftTriageCounts;
    /** 后端 warnings 原文列表（"第 N 段解析失败：<原因>"）。
     * 注意：N 是后端 AI 分块序号，仅全篇走 AI 解析时才与原文分段一致；
     * 跨段精确定位需后端 additive 下发结构化字段。 */
    segmentWarnings?: string[];
    modelValue?: "all" | DraftTriage;
  }>(),
  { segmentWarnings: () => [], modelValue: "all" },
);

const emit = defineEmits<{ (e: "update:modelValue", value: "all" | DraftTriage): void }>();

const filters = computed(() =>
  [
    { key: "all" as const, label: `全部 ${props.total}`, disabled: props.total === 0 },
    { key: "ready" as const, label: `✓ 正常 ${props.counts.ready}`, disabled: props.counts.ready === 0 },
    { key: "review" as const, label: `⚠ 待确认 ${props.counts.review}`, disabled: props.counts.review === 0 },
    { key: "blocked" as const, label: `✕ 无法创建 ${props.counts.blocked}`, disabled: props.counts.blocked === 0 },
  ]
);
</script>

<template>
  <div class="rounded-2xl border border-default bg-surface p-4 shadow-card">
    <div class="flex items-center justify-between gap-2">
      <div class="flex items-center gap-2">
        <span class="inline-flex items-center rounded-full bg-ai-soft px-2 py-0.5 text-caption font-bold text-ai-deep">AI</span>
        <span class="text-sm font-semibold text-primary">本次解析 {{ total }} 条需求</span>
      </div>
    </div>

    <!-- 分诊过滤：点击过滤下方列表 -->
    <div class="mt-2.5 flex flex-wrap gap-1.5">
      <button
        v-for="f in filters"
        :key="f.key"
        class="rounded-full px-2.5 py-1 text-caption font-medium transition-colors disabled:opacity-40"
        :class="modelValue === f.key ? 'bg-brand-800 text-white' : 'bg-surface-soft text-secondary hover:bg-surface-soft'"
        :disabled="f.disabled"
        @click="emit('update:modelValue', f.key)"
      >
        {{ f.label }}
      </button>
    </div>

    <!-- 分段失败：后端 warnings 逐条原文展示（段序号 + 原因），不做前端推断映射 -->
    <template v-if="segmentWarnings.length > 0">
      <p class="mt-2 text-caption leading-4 text-warning">
        另有 {{ segmentWarnings.length }} 段原文未能解析成功，可补全后重新粘贴该段：
      </p>
      <ul class="mt-1 list-disc space-y-0.5 pl-4">
        <li
          v-for="(w, i) in segmentWarnings"
          :key="i"
          class="break-all text-caption leading-4 text-warning"
        >
          {{ w }}
        </li>
      </ul>
    </template>
  </div>
</template>
