<script setup lang="ts">
import type { RecommendationExplanation } from "./recommendation";
import AppCard from "@/components/ui/AppCard.vue";

/**
 * 推荐解释卡（Batch 02 核心新组件）：
 * 回答"系统为什么认为这个订单适合你"——展示后端 score_breakdown 六维分数
 * 与真实 reasons，不做任何前端计算。
 * 视觉纪律（规格书）：解释能力而非 AI 炫技——无发光/渐变/粒子，
 * AI 紫（ai-soft/ai-deep）只作辅助 accent。
 */
defineProps<{
  explanation: RecommendationExplanation;
  compact?: boolean;
}>();
</script>

<template>
  <AppCard :padding="compact ? 'sm' : 'md'" flat class="border-ai-soft bg-ai-soft/40">
    <div class="flex items-start gap-3">
      <!-- 匹配度 -->
      <div class="shrink-0 text-center">
        <div class="price-highlight text-xl font-bold leading-6 text-ai-deep">
          {{ explanation.totalScore }}<span class="text-xs">%</span>
        </div>
        <div class="mt-0.5 text-[10px] text-secondary">匹配度</div>
      </div>

      <div class="min-w-0 flex-1">
        <div class="text-xs font-semibold text-ai-deep">为什么推荐给你？</div>

        <!-- 六维分数条：分数来自接口，前端不复算 -->
        <div class="mt-2 space-y-1.5">
          <div
            v-for="factor in explanation.factors"
            :key="factor.key"
            class="flex items-center gap-2"
          >
            <span class="w-14 shrink-0 text-[11px] text-secondary">{{ factor.label }}</span>
            <div class="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-surface">
              <div
                class="h-full rounded-full bg-ai"
                :style="{ width: `${Math.max(0, Math.min(100, factor.score))}%` }"
              />
            </div>
            <span class="price-highlight w-8 shrink-0 text-right text-[11px] tabular-nums text-secondary">
              {{ factor.score }}
            </span>
          </div>
        </div>

        <!-- 后端 reasons 原文；没有就不渲染，绝不生成假理由 -->
        <ul v-if="explanation.reasons.length" class="mt-2.5 space-y-1">
          <li
            v-for="reason in explanation.reasons"
            :key="reason"
            class="flex items-start gap-1 text-[11px] leading-4 text-secondary"
          >
            <span class="text-ai-deep" aria-hidden="true">✓</span>
            <span class="min-w-0">{{ reason }}</span>
          </li>
        </ul>
      </div>
    </div>
  </AppCard>
</template>
