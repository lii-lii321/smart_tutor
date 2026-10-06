<script setup lang="ts">
/**
 * 投递进度步进器（C 端我的投递）。
 *
 * 数据来自 components/business/timeline.ts 的 buildApplicationLifecycleSteps
 * ——全站唯一的"投递状态 → 展示步骤"映射（与 B 端 ApplicationStageTrail 同源），
 * 本组件只负责横向圆点排版，不做任何状态判断、不伪造时间。
 * 终止态（rejected/refunded/forfeited）由映射以 skipped + note 表达，
 * 本组件如实渲染划线，不假装流程还在推进。
 */
import { computed } from "vue";
import type { ApplicationItem } from "@/api/types";
import { buildApplicationLifecycleSteps, toCompactSteps } from "@/components/business/timeline";

const props = defineProps<{ application: ApplicationItem }>();

const steps = computed(() => toCompactSteps(buildApplicationLifecycleSteps(props.application)));
</script>

<template>
  <ol class="flex items-start">
    <template v-for="(step, i) in steps" :key="step.label">
      <li
        v-if="i > 0"
        class="mt-[7px] h-px flex-1"
        :class="steps[i - 1].state === 'done' && step.state !== 'todo' ? 'bg-brand-300' : 'bg-default'"
        aria-hidden="true"
      />
      <li
        class="flex w-9 shrink-0 flex-col items-center gap-1"
        :title="step.hint"
      >
        <span
          class="grid h-[15px] w-[15px] place-items-center rounded-full text-caption font-bold leading-none"
          :class="{
            'bg-brand-800 text-white': step.state === 'done',
            'border-2 border-brand-600 bg-surface': step.state === 'current',
            'border border-default bg-surface-soft': step.state === 'todo' || step.state === 'skipped',
          }"
        >
          <template v-if="step.state === 'done'">✓</template>
        </span>
        <span
          class="text-caption"
          :class="[
            step.state === 'current'
              ? 'font-semibold text-brand-800'
              : step.state === 'done'
                ? 'text-secondary'
                : 'text-muted',
            step.state === 'skipped' ? 'line-through' : '',
          ]"
        >
          {{ step.short }}
        </span>
      </li>
    </template>
  </ol>
</template>
