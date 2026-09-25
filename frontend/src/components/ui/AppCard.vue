<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    padding?: "none" | "sm" | "md";
    interactive?: boolean;
    highlight?: boolean;
    /** soft: 弱化面底色（surface-soft）；flat: 去阴影描边化（嵌套/次要内容用） */
    soft?: boolean;
    flat?: boolean;
  }>(),
  { padding: "md", interactive: false, highlight: false, soft: false, flat: false },
);

const paddingClass = computed(
  () => ({ none: "", sm: "p-3", md: "p-4" })[props.padding],
);
</script>

<template>
  <div
    class="border border-default rounded-2xl"
    :class="[
      paddingClass,
      soft ? 'bg-surface-soft' : 'bg-surface',
      flat ? 'shadow-none' : 'shadow-card',
      highlight && 'border-brand-200 ring-1 ring-brand-100',
      interactive &&
        'st-card--interactive cursor-pointer hover:shadow-elevated hover:border-strong',
    ]"
  >
    <slot />
  </div>
</template>
