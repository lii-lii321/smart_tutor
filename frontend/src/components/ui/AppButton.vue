<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    variant?: "primary" | "secondary" | "ghost" | "danger";
    size?: "sm" | "md" | "lg";
    block?: boolean;
    loading?: boolean;
    disabled?: boolean;
    type?: "button" | "submit";
  }>(),
  {
    variant: "primary",
    size: "md",
    block: false,
    loading: false,
    disabled: false,
    type: "button",
  },
);

defineEmits<{ (e: "click", event: MouseEvent): void }>();

const variantClass = computed(
  () =>
    ({
      primary: "bg-brand-800 text-white hover:bg-brand-700 active:bg-brand-900",
      secondary:
        "bg-surface text-ink border border-default hover:bg-surface-soft active:bg-surface-warm",
      ghost: "bg-transparent text-brand-800 hover:bg-brand-50 active:bg-brand-100",
      danger: "bg-danger text-white hover:opacity-90 active:opacity-80",
    })[props.variant],
);

const sizeClass = computed(
  () =>
    ({
      sm: "h-8 px-3 text-xs rounded-lg gap-1",
      md: "h-10 px-4 text-sm rounded-xl gap-1.5",
      lg: "h-12 px-5 text-base rounded-xl gap-2",
    })[props.size],
);
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    class="st-focus inline-flex select-none items-center justify-center font-semibold transition-colors disabled:pointer-events-none disabled:opacity-40"
    :class="[variantClass, sizeClass, block && 'w-full']"
    @click="$emit('click', $event)"
  >
    <span v-if="loading" class="st-spinner" aria-hidden="true" />
    <slot />
  </button>
</template>
