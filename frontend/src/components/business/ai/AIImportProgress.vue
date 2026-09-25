<script setup lang="ts">
import { computed } from "vue";
import type { DraftTriage, DraftTriageCounts } from "./aiImport";

/**
 * AI 解析进度/异常摘要（Batch 03）：
 * 展示"本次解析 N 条需求 → 正常/待确认/无法创建"三级分诊，并承担过滤入口。
 * 纪律：解析请求进行中只显示"解析中"文案，**绝不显示前端自跑的假百分比**；
 * 分段失败数（后端 warnings）如实展示。
 */
const props = withDefaults(
  defineProps<{
    total: number;
    counts: DraftTriageCounts;
    /** 后端 warnings 长度：解析失败的段数 */
    segmentFailures?: number;
    parsing?: boolean;
    modelValue?: "all" | DraftTriage;
  }>(),
  { segmentFailures: 0, parsing: false, modelValue: "all" },
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
    <!-- 解析中：只有诚实文案，没有假进度条百分比 -->
    <template v-if="parsing">
      <div class="flex items-center gap-2">
        <span class="inline-flex items-center rounded-full bg-ai-soft px-2 py-0.5 text-[10px] font-bold text-ai-deep">AI</span>
        <span class="text-sm font-medium text-primary">正在处理 {{ total }} 条需求…</span>
      </div>
      <p class="mt-1 text-xs leading-5 text-muted">自动提取地址 · 年级 · 科目 · 课酬 · 时间，完成后在此逐条人工校对</p>
    </template>

    <template v-else>
      <div class="flex items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <span class="inline-flex items-center rounded-full bg-ai-soft px-2 py-0.5 text-[10px] font-bold text-ai-deep">AI</span>
          <span class="text-sm font-semibold text-primary">本次解析 {{ total }} 条需求</span>
        </div>
      </div>

      <!-- 分诊过滤：点击过滤下方列表 -->
      <div class="mt-2.5 flex flex-wrap gap-1.5">
        <button
          v-for="f in filters"
          :key="f.key"
          class="rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors disabled:opacity-40"
          :class="modelValue === f.key ? 'bg-brand-800 text-white' : 'bg-surface-soft text-secondary hover:bg-slate-100'"
          :disabled="f.disabled"
          @click="emit('update:modelValue', f.key)"
        >
          {{ f.label }}
        </button>
      </div>

      <p v-if="segmentFailures > 0" class="mt-2 text-[11px] leading-4 text-warning">
        另有 {{ segmentFailures }} 段原文未能解析成功，可补全后重新粘贴该段。
      </p>
    </template>
  </div>
</template>
