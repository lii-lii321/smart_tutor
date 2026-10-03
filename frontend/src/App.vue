<script setup lang="ts">
import AppConfirm from "@/components/AppConfirm.vue";
</script>

<template>
  <!--
    不做路由转场动画：mode="out-in" 的淡入淡出依赖 transitionend/rAF，
    在省电模式、动画被禁用或部分 WebView 遮挡场景下会永久卡住
    （URL 已变、页面不渲染），H5 直切更稳。
  -->
  <router-view />
  <!-- 全局底部确认弹层：appConfirm() 的唯一挂载点 -->
  <AppConfirm />
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

/* 操作结果提示统一为顶部居中的深色小胶囊：
   - 不再悬在屏幕正中挡住操作按钮；
   - 图标与文字并排（vant 默认上下堆叠又高又宽），视觉更轻。
   vant 默认白底黑字反差生硬，统一为深板岩底白字。 */
.van-toast {
  top: 7% !important;
  left: 50% !important;
  transform: translate(-50%, 0) !important;
  flex-direction: row !important;
  align-items: center !important;
  width: auto !important;
  min-width: 0 !important;
  max-width: 78vw;
  padding: 9px 18px;
  background: rgba(15, 23, 42, 0.88);
  color: #fff;
  border-radius: 999px;
  box-shadow: 0 6px 20px rgba(15, 23, 42, 0.2);
}
.van-toast .van-toast__icon {
  font-size: 18px;
  margin-right: 6px;
}
.van-toast .van-toast__text {
  font-size: 13px;
  line-height: 1.4;
}

/* popup/overlay 同理：关闭动画的 transitionend 丢失会让 van-overlay 永久停留
   （一层看不见的遮罩吃掉全部点击，表现为"点不到按钮/误触"），禁用过渡根治。
   但 transition: none 让遮罩瞬间满黑出现/消失=用户投诉的"点击黑闪一下"，
   故 overlay 用 keyframes 淡入替代（animationend 不存在"丢失卡住"问题：
   动画结束即 opacity:1 常驻，与是否监听事件无关）；popup 保持瞬现可接受 */
@keyframes van-overlay-fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}
.van-popup {
  transition: none !important;
  animation: none !important;
}
.van-overlay {
  transition: none !important;
  animation: van-overlay-fade-in 0.16s ease-out !important;
}
</style>
