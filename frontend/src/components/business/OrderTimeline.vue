<script setup lang="ts">
import type { TimelineStep } from "./timeline";

/**
 * 订单生命周期时间线（Batch 01 基础结构，规格书定义的"未来订单详情页核心组件"）。
 * 纯展示组件：只渲染 TimelineStep 数组，状态→步骤的映射在 timeline.ts 单点收敛。
 * 业务页面（订单详情/我的投递）在 Batch 02 接入，本阶段不改动任何业务页面。
 */
withDefaults(defineProps<{ steps: TimelineStep[]; compact?: boolean }>(), {
  compact: false,
});
</script>

<template>
  <ol class="space-y-0" :class="compact ? 'text-xs' : 'text-sm'">
    <li
      v-for="(step, i) in steps"
      :key="step.label"
      class="relative flex gap-3 pb-4 last:pb-0"
    >
      <!-- 竖向连接线：最后一项不画 -->
      <span
        v-if="i < steps.length - 1"
        class="absolute top-5 left-[7px] h-full w-px"
        :class="step.state === 'done' ? 'bg-brand-200' : 'bg-slate-200'"
        aria-hidden="true"
      />
      <!-- 状态圆点 -->
      <span
        class="relative mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2"
        :class="{
          'border-brand-800 bg-brand-800': step.state === 'done',
          'border-brand-800 bg-surface ring-2 ring-brand-100': step.state === 'current',
          'border-slate-300 bg-surface': step.state === 'todo',
          'border-slate-200 bg-slate-100': step.state === 'skipped',
        }"
      >
        <span
          v-if="step.state === 'done'"
          class="h-1.5 w-1.5 rounded-full bg-surface"
          aria-hidden="true"
        />
      </span>

      <div class="min-w-0 flex-1">
        <div class="flex items-baseline justify-between gap-2">
          <span
            class="font-medium leading-5"
            :class="{
              'text-primary': step.state === 'done' || step.state === 'current',
              'text-muted': step.state === 'todo' || step.state === 'skipped',
            }"
          >
            {{ step.label }}
          </span>
          <span v-if="step.time" class="shrink-0 text-[11px] text-muted">{{ step.time }}</span>
        </div>
        <p v-if="step.note" class="mt-0.5 text-[11px] leading-4 text-muted">{{ step.note }}</p>
      </div>
    </li>
  </ol>
</template>
