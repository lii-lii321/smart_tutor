<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    variant?:
      | "primary"
      | "accent"
      | "secondary"
      | "ghost"
      | "danger"
      | "text"
      | "danger-soft"
      | "warning-soft"
      | "info-soft";
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
      primary: "bg-ink text-white hover:bg-ink-soft active:bg-ink",
      accent: "bg-accent text-ink hover:bg-accent-deep active:bg-accent-deep",
      secondary:
        "bg-surface text-primary border border-strong hover:bg-surface-soft active:bg-surface-warm",
      ghost: "bg-transparent text-brand-800 hover:bg-brand-50 active:bg-brand-100",
      danger: "bg-danger text-white hover:opacity-90 active:opacity-80",
      text: "bg-transparent text-brand-800 hover:bg-brand-50 active:bg-brand-100",
      // 软色档：需警示但非不可逆主动作（没收定金/试课失败/评价等），形制与实心档一致
      "danger-soft": "bg-danger-soft text-danger-deep hover:opacity-90 active:opacity-80",
      "warning-soft": "bg-warning-soft text-warning-deep hover:opacity-90 active:opacity-80",
      "info-soft": "bg-info-soft text-info-deep hover:opacity-90 active:opacity-80",
    })[props.variant],
);

const sizeClass = computed(
  () =>
    ({
      sm: "h-8 px-3 text-xs rounded-full gap-1",
      md: "h-10 px-4 text-sm rounded-full gap-1.5",
      lg: "h-12 px-5 text-base rounded-full gap-2",
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
