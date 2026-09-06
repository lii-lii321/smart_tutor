<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { showToast } from "vant";

const router = useRouter();
const auth = useAuthStore();

const inviteCode = ref("");
const password = ref("");
const loading = ref(false);

async function handleLogin() {
  if (!inviteCode.value.trim()) return;
  if (password.value.length < 6) {
    showToast("请输入至少 6 位密码");
    return;
  }
  loading.value = true;
  try {
    await auth.tenantLogin(inviteCode.value.trim(), password.value);
    showToast("登录成功");
    router.push("/admin/dashboard");
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "登录失败");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page min-h-screen flex flex-col">
    <div class="login-content flex-1 flex flex-col px-4 pb-24">
    <div class="login-identity text-center mb-5">
      <div class="w-20 h-20 mx-auto rounded-2xl header-gradient flex items-center justify-center shadow-lg mb-4">
        <van-icon name="shop-o" size="40" color="#fff" />
      </div>
      <h2 class="text-xl font-bold">智派 · 中介后台</h2>
      <p class="text-gray-400 text-sm mt-1">登录后录入、管理和审核家教单</p>
    </div>

    <div class="login-role-switch mb-4 grid grid-cols-2 rounded-xl bg-white p-1 shadow-sm">
      <button
        class="rounded-lg py-2 text-sm font-semibold text-slate-500"
        @click="router.push('/teacher/login')"
      >
        教员登录
      </button>
      <button class="rounded-lg bg-[#1a365d] py-2 text-sm font-semibold text-white">
        中介登录
      </button>
    </div>

    <div class="login-form bg-white rounded-2xl p-5 shadow-sm space-y-4">
      <van-field
        v-model="inviteCode"
        label="邀请码"
        placeholder="请输入中介邀请码"
        clearable
      />
      <van-field
        v-model="password"
        label="密码"
        placeholder="请输入后台密码"
        type="password"
        clearable
      />
      <button
        class="w-full header-gradient text-white rounded-xl py-3.5 text-base font-semibold disabled:opacity-50"
        :disabled="loading || !inviteCode.trim() || password.length < 6"
        @click="handleLogin"
      >
        {{ loading ? "登录中..." : "进入后台" }}
      </button>
    </div>
  </div>
  </div>
</template>
