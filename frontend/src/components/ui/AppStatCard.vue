<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    label: string;
    value: string | number;
    hint?: string;
    tone?: "default" | "brand" | "success" | "warning" | "danger";
  }>(),
  { hint: undefined, tone: "default" },
);

const valueClass = computed(
  () =>
    ({
      default: "text-ink",
      brand: "text-brand-800",
      success: "text-success",
      warning: "text-warning",
      danger: "text-danger",
    })[props.tone],
);
</script>

<template>
  <div class="bg-surface border border-default rounded-2xl p-3 shadow-card">
    <div class="text-xs text-muted">{{ label }}</div>
    <div
      class="price-highlight mt-1 text-xl font-bold leading-7 tracking-tight"
      :class="valueClass"
    >
      {{ value }}
    </div>
    <div v-if="hint" class="mt-0.5 text-[11px] text-muted">{{ hint }}</div>
  </div>
</template>
