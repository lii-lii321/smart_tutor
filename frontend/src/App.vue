<script setup lang="ts">
import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
</script>

<template>
  <!--
    不做路由转场动画：mode="out-in" 的淡入淡出依赖 transitionend/rAF，
    在省电模式、动画被禁用或部分 WebView 遮挡场景下会永久卡住
    （URL 已变、页面不渲染），H5 直切更稳。
  -->
  <router-view />
</template>

<style>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.25s ease;
}
.slide-enter-from {
  transform: translateX(100%);
}
.slide-leave-to {
  transform: translateX(-100%);
}

/* 同一原因：toast 的淡入淡出事件丢失时会永久停留（挡住页面中部），
   直接禁用其过渡，让 Vue 立即完成挂载/卸载 */
.van-toast {
  transition: none !important;
  animation: none !important;
}
</style>
