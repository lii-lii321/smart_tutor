<script setup lang="ts">
/**
 * 相似订单迷你卡（阶段 2）：语义相似度 + 关键字段，点击切换到该订单工作区。
 * 展示字段与找单卡片同一数据口径（order_list_payload）。
 */
import { computed } from "vue";

import type { SimilarOrderItem } from "@/api/ai";
import { priceLabel } from "./aiFindOrders";

const props = defineProps<{ item: SimilarOrderItem }>();

defineEmits<{ (e: "open", id: number): void }>();

const similarityText = computed(() => `${Math.round(props.item.similarity * 100)}%`);
const createdText = computed(() => (props.item.created_at ?? "").slice(0, 10));
</script>

<template>
  <button
    type="button"
    class="w-full rounded-xl border border-default bg-surface-soft/40 px-3 py-2.5 text-left transition-colors hover:bg-surface-soft"
    @click="$emit('open', item.id)"
  >
    <div class="flex items-center gap-2">
      <span class="min-w-0 flex-1 truncate text-body-sm font-semibold text-primary">
        {{ item.grade_subject }}
      </span>
      <span class="shrink-0 rounded-full bg-ai-soft px-1.5 py-0.5 text-caption font-semibold text-ai-deep">
        相似 {{ similarityText }}
      </span>
    </div>
    <div class="mt-1 flex items-center gap-2 text-caption text-muted">
      <span class="min-w-0 flex-1 truncate">{{ item.fuzzy_address }}</span>
      <span
        class="shrink-0 font-medium"
        :class="item.needs_manual_price ? 'text-warning-deep' : 'text-secondary'"
      >
        {{ priceLabel(item) }}
      </span>
      <span v-if="createdText" class="shrink-0">{{ createdText }}</span>
    </div>
  </button>
</template>
