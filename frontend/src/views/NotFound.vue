<script setup lang="ts">
import { useRouter } from "vue-router";
import AppButton from "@/components/ui/AppButton.vue";

const router = useRouter();

function goHome() {
  router.replace("/");
}
</script>

<template>
  <div class="flex min-h-screen flex-col items-center justify-center bg-page px-6 text-center">
    <div class="text-6xl font-black text-default">404</div>
    <div class="mt-3 text-lg font-semibold text-primary">页面不存在或已下线</div>
    <p class="mt-2 text-sm leading-6 text-secondary">
      链接可能输错了。回到首页继续找单，或联系分享给你链接的人。
    </p>
    <AppButton block size="lg" class="mt-6 max-w-xs" @click="goHome">
      返回首页
    </AppButton>
  </div>
</template>
