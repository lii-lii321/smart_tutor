<script setup lang="ts">
/**
 * 投递流转横条（B 端审核页常驻）。
 *
 * 数据来自 components/business/timeline.ts 的 buildApplicationLifecycleSteps
 * ——那是全站唯一的"投递状态 → 展示步骤"映射，本组件只负责横向排版，
 * 不做任何状态判断。缺时间戳的阶段只表达"是否已发生"，不伪造时间。
 *
 * 用途：中介在审核一条投递时，能立刻看出它卡在哪一环、按钮该点哪个，
 * 不用展开详情逐个时间戳去找。
 */
import { computed } from "vue";
import type { ApplicationItem } from "@/api/types";
import { buildApplicationLifecycleSteps, toCompactSteps } from "@/components/business/timeline";

const props = defineProps<{ application: ApplicationItem }>();

const steps = computed(() => toCompactSteps(buildApplicationLifecycleSteps(props.application)));
</script>

<template>
  <ol class="flex flex-wrap items-center gap-x-1 gap-y-1">
    <template v-for="(step, i) in steps" :key="step.label">
      <li v-if="i > 0" class="text-caption text-default" aria-hidden="true">›</li>
      <li
        class="rounded px-1.5 py-0.5 text-caption leading-4"
        :class="{
          'bg-brand-50 font-semibold text-brand-800': step.state === 'current',
          'text-secondary': step.state === 'done',
          'text-muted': step.state === 'todo',
          'text-default line-through': step.state === 'skipped',
        }"
        :title="step.hint"
      >
        {{ step.short }}
      </li>
    </template>
  </ol>
</template>
