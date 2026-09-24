<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    padding?: "none" | "sm" | "md";
    interactive?: boolean;
    highlight?: boolean;
  }>(),
  { padding: "md", interactive: false, highlight: false },
);

const paddingClass = computed(
  () => ({ none: "", sm: "p-3", md: "p-4" })[props.padding],
);
</script>

<template>
  <div
    class="bg-surface border border-default rounded-2xl shadow-card"
    :class="[
      paddingClass,
      highlight && 'border-brand-200 ring-1 ring-brand-100',
      interactive &&
        'st-card--interactive cursor-pointer hover:shadow-elevated hover:border-slate-300',
    ]"
  >
    <slot />
  </div>
</template>
