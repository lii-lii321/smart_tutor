<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    tone?: "neutral" | "brand" | "success" | "warning" | "danger" | "info" | "ai";
    size?: "sm" | "md";
    dot?: boolean;
  }>(),
  { tone: "neutral", size: "md", dot: false },
);

const toneClass = computed(
  () =>
    ({
      neutral: "bg-slate-100 text-slate-600",
      brand: "bg-brand-50 text-brand-700",
      success: "bg-success-soft text-success",
      warning: "bg-warning-soft text-warning",
      danger: "bg-danger-soft text-danger",
      info: "bg-info-soft text-info",
      ai: "bg-ai-soft text-ai-deep",
    })[props.tone],
);

const sizeClass = computed(() =>
  props.size === "sm" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs",
);
</script>

<template>
  <span
    class="inline-flex items-center rounded-full font-medium"
    :class="[toneClass, sizeClass]"
  >
    <span v-if="dot" class="mr-1 h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
    <slot />
  </span>
</template>
