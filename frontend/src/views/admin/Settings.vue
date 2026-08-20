<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { showToast } from "vant";

const router = useRouter();
const auth = useAuthStore();

const inviteLink = ref(`https://zhipai.app/teacher/board/${auth.tenant?.invite_code || "tx886"}`);

function copyLink() {
  navigator.clipboard.writeText(inviteLink.value);
  showToast("已复制橱窗链接");
}
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-20">
    <van-nav-bar title="设置" left-arrow @click-left="router.push('/admin/dashboard')" />

    <div class="p-4 space-y-4">
      <!-- 基本信息 -->
      <div class="bg-white rounded-2xl p-5 shadow-sm">
        <h3 class="font-semibold mb-4">📋 基本信息</h3>
        <van-field label="中介名称" :model-value="auth.tenant?.tenant_name || ''" readonly />
        <van-field label="邀请码" :model-value="auth.tenant?.invite_code || ''" readonly />
      </div>

      <!-- 橱窗链接 -->
      <div class="bg-white rounded-2xl p-5 shadow-sm">
        <h3 class="font-semibold mb-4">🔗 教员橱窗链接</h3>
        <div class="bg-gray-50 rounded-xl p-3 text-xs text-gray-600 break-all mb-3">
          {{ inviteLink }}
        </div>
        <button
          class="w-full bg-primary-50 text-primary-600 rounded-xl py-2.5 text-sm font-semibold"
          @click="copyLink"
        >
          📋 复制链接
        </button>
      </div>

      <!-- 退出 -->
      <div class="bg-white rounded-2xl overflow-hidden shadow-sm">
        <van-cell title="退出登录" icon="revoke" @click="auth.logout(); router.push('/')" />
      </div>
    </div>
  </div>
</template>
