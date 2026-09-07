<script setup lang="ts">
import { useRouter } from "vue-router";

const router = useRouter();

function goHome() {
  router.replace("/");
}
</script>

<template>
  <div class="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-6 text-center">
    <div class="text-6xl font-black text-slate-200">404</div>
    <div class="mt-3 text-lg font-semibold text-slate-800">页面不存在或已下线</div>
    <p class="mt-2 text-sm leading-6 text-slate-500">
      链接可能输错了。回到首页继续找单，或联系分享给你链接的人。
    </p>
    <button
      class="mt-6 w-full max-w-xs rounded-xl bg-[#1a365d] py-3 text-sm font-semibold text-white"
      @click="goHome"
    >
      返回首页
    </button>
  </div>
</template>
