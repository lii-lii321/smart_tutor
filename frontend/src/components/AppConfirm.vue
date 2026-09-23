<script setup lang="ts">
/**
 * 全局底部确认弹层：在 App.vue 挂载一次，任何地方经 appConfirm() 调起。
 * 按钮上下堆叠 + 颜色分离（确认蓝/危险红，取消灰），物理上避免并排误触。
 */
import { appConfirmState, settleAppConfirm } from "@/composables/appConfirm";
</script>

<template>
  <van-popup
    :show="appConfirmState.visible"
    position="bottom"
    round
    @update:show="(value: boolean) => !value && settleAppConfirm(false)"
    @closed="settleAppConfirm(false)"
  >
    <div class="p-5 pb-[calc(16px+env(safe-area-inset-bottom))]">
      <div class="text-center text-base font-semibold text-slate-950">
        {{ appConfirmState.title }}
      </div>
      <div class="mt-2 whitespace-pre-line text-center text-sm leading-5 text-slate-500">
        {{ appConfirmState.message }}
      </div>
      <button
        class="mt-5 w-full rounded-xl py-3 text-sm font-semibold text-white active:opacity-80"
        :class="appConfirmState.danger ? 'bg-red-500' : 'bg-slate-700'"
        @click="settleAppConfirm(true)"
      >
        {{ appConfirmState.confirmText }}
      </button>
      <button
        class="mt-3 w-full rounded-xl bg-slate-100 py-3 text-sm font-medium text-slate-600 active:bg-slate-200"
        @click="settleAppConfirm(false)"
      >
        取消
      </button>
    </div>
  </van-popup>
</template>
