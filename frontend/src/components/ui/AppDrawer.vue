<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    show: boolean;
    title?: string;
    height?: "auto" | "full";
  }>(),
  { title: "", height: "auto" },
);

const emit = defineEmits<{ (e: "update:show", value: boolean): void }>();

const popupStyle = computed(() =>
  props.height === "full" ? { height: "86%" } : undefined,
);

const close = () => emit("update:show", false);
</script>

<template>
  <!-- 底部抽屉统一封装：圆角、标题栏、安全区内边距；禁用过渡由 App.vue 全局处理 -->
  <van-popup
    :show="show"
    position="bottom"
    round
    :style="popupStyle"
    @update:show="emit('update:show', $event)"
  >
    <div class="safe-bottom flex max-h-[86vh] flex-col">
      <div class="flex shrink-0 items-center justify-between px-4 pb-2 pt-3">
        <h3 class="text-base font-bold text-primary">{{ title }}</h3>
        <van-icon name="cross" class="text-xl text-muted" @click="close" />
      </div>
      <div class="overflow-y-auto px-4 pb-4">
        <slot />
      </div>
    </div>
  </van-popup>
</template>
