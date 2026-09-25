<script setup lang="ts">
withDefaults(defineProps<{ title: string; subtitle?: string; sticky?: boolean }>(), {
  subtitle: undefined,
  sticky: false,
});
</script>

<template>
  <header
    class="flex items-start justify-between gap-3 px-4 pb-3 pt-4"
    :class="sticky && 'sticky top-0 z-20 border-b border-default bg-page/95 backdrop-blur'"
  >
    <div class="min-w-0">
      <h1 class="truncate text-lg font-bold leading-6 text-primary">{{ title }}</h1>
      <p v-if="subtitle" class="mt-0.5 text-xs text-muted">{{ subtitle }}</p>
      <slot />
    </div>
    <div v-if="$slots.actions" class="flex shrink-0 items-center gap-2">
      <slot name="actions" />
    </div>
  </header>
</template>
