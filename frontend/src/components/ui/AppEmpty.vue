<script setup lang="ts">
withDefaults(
  defineProps<{ title: string; description?: string; icon?: string }>(),
  { description: undefined, icon: "📭" },
);
</script>

<template>
  <!-- 空态唯一口径：居中、一句话说清"现在没有"+ "下一步做什么"（见 slot） -->
  <div class="flex flex-col items-center justify-center px-6 py-12 text-center">
    <div class="mb-3 select-none text-4xl" aria-hidden="true">{{ icon }}</div>
    <p class="text-sm font-medium text-secondary">{{ title }}</p>
    <p v-if="description" class="mt-1 max-w-[240px] text-xs leading-5 text-muted">
      {{ description }}
    </p>
    <div v-if="$slots.action" class="mt-4">
      <slot name="action" />
    </div>
  </div>
</template>
