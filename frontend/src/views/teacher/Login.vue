<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { showToast } from "vant";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const activeRole = ref<"teacher" | "admin" | "owner">("teacher");
const phone = ref("");
const inviteCode = ref(String(route.query.inviteCode || "tx886"));
const adminInviteCode = ref(String(route.query.inviteCode || "tx886"));
const loading = ref(false);

async function handleLogin() {
  const normalizedPhone = phone.value.trim().replace(/\s+/g, "");
  const normalizedInviteCode = inviteCode.value.trim();
  if (!/^1\d{10}$/.test(normalizedPhone)) {
    showToast("请输入 11 位手机号");
    return;
  }
  if (!normalizedInviteCode) {
    showToast("请输入邀请码");
    return;
  }
  loading.value = true;
  try {
    await auth.phoneInviteLogin(normalizedPhone, normalizedInviteCode);
    showToast("登录成功");
    router.back();
  } catch (e: any) {
    if (e?.response?.status === 404) {
      showToast("请先完善教员资料");
      router.push({
        path: "/teacher/register",
        query: {
          phone: normalizedPhone,
          inviteCode: normalizedInviteCode,
        },
      });
      return;
    }
    showToast(e?.response?.data?.detail || "登录失败");
  } finally {
    loading.value = false;
  }
}

async function handleAdminLogin() {
  const code = adminInviteCode.value.trim();
  if (!code) {
    showToast("请输入中介邀请码");
    return;
  }
  loading.value = true;
  try {
    await auth.tenantLogin(code);
    showToast("登录成功");
    router.push("/admin/dashboard");
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "登录失败");
  } finally {
    loading.value = false;
  }
}

const ownerAccessCode = ref("");

async function handleOwnerLogin() {
  const code = ownerAccessCode.value.trim();
  if (!code) {
    showToast("请输入老板访问码");
    return;
  }
  loading.value = true;
  try {
    await auth.ownerLogin(code);
    showToast("登录成功");
    router.push("/owner/tenants");
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "登录失败");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen bg-gray-50 flex flex-col">
    <van-nav-bar :title="activeRole === 'teacher' ? '教员登录' : activeRole === 'admin' ? '中介登录' : '老板入口'" left-arrow @click-left="router.back()" />

    <div class="flex-1 flex flex-col justify-center px-6 pb-20">
      <!-- Logo -->
      <div class="text-center mb-6">
        <div class="w-20 h-20 mx-auto rounded-2xl header-gradient flex items-center justify-center shadow-lg shadow-primary-500/30 mb-4">
          <van-icon :name="activeRole === 'teacher' ? 'manager-o' : activeRole === 'admin' ? 'shop-o' : 'setting-o'" size="40" color="#fff" />
        </div>
        <h2 class="text-xl font-bold">
          {{ activeRole === "teacher" ? "智派 · 教员端" : activeRole === "admin" ? "智派 · 中介后台" : "智派 · 老板管理" }}
        </h2>
        <p class="text-gray-400 text-sm mt-1">
          {{
            activeRole === "teacher"
              ? "手机号登录，未注册将完善资料"
              : activeRole === "admin"
                ? "用平台发放的邀请码进入中介后台"
                : "创建、停用和复制中介邀请码"
          }}
        </p>
      </div>

      <div class="mb-4 grid grid-cols-3 rounded-xl bg-white p-1 shadow-sm">
        <button
          class="rounded-lg py-2 text-sm font-semibold"
          :class="activeRole === 'teacher' ? 'bg-[#1a365d] text-white' : 'text-slate-500'"
          @click="activeRole = 'teacher'"
        >
          教员登录
        </button>
        <button
          class="rounded-lg py-2 text-sm font-semibold"
          :class="activeRole === 'admin' ? 'bg-[#1a365d] text-white' : 'text-slate-500'"
          @click="activeRole = 'admin'"
        >
          中介登录
        </button>
        <button
          class="rounded-lg py-2 text-sm font-semibold"
          :class="activeRole === 'owner' ? 'bg-[#1a365d] text-white' : 'text-slate-500'"
          @click="activeRole = 'owner'"
        >
          老板入口
        </button>
      </div>

      <!-- 登录表单 -->
      <div v-if="activeRole === 'teacher'" class="bg-white rounded-2xl p-5 shadow-sm space-y-4">
        <van-field
          v-model="phone"
          label="手机号"
          placeholder="请输入手机号"
          type="tel"
          maxlength="11"
          clearable
        />
        <van-field
          v-model="inviteCode"
          label="邀请码"
          placeholder="请输入中介邀请码"
          clearable
        />

        <button
          class="w-full header-gradient text-white rounded-xl py-3.5 text-base font-semibold disabled:opacity-50 shadow-lg shadow-primary-500/30"
          :disabled="loading || !phone.trim() || !inviteCode.trim()"
          @click="handleLogin"
        >
          {{ loading ? "登录中..." : "登录" }}
        </button>
      </div>

      <div v-else-if="activeRole === 'admin'" class="bg-white rounded-2xl p-5 shadow-sm space-y-4">
        <van-field
          v-model="adminInviteCode"
          label="邀请码"
          placeholder="请输入中介邀请码"
          clearable
        />

        <button
          class="w-full header-gradient text-white rounded-xl py-3.5 text-base font-semibold disabled:opacity-50 shadow-lg shadow-primary-500/30"
          :disabled="loading || !adminInviteCode.trim()"
          @click="handleAdminLogin"
        >
          {{ loading ? "登录中..." : "进入中介后台" }}
        </button>
      </div>

      <div v-else class="bg-white rounded-2xl p-5 shadow-sm space-y-4">
        <van-field
          v-model="ownerAccessCode"
          label="访问码"
          placeholder="请输入老板访问码"
          type="password"
          clearable
        />
        <div class="text-xs text-slate-400">开发环境默认访问码：boss888</div>

        <button
          class="w-full header-gradient text-white rounded-xl py-3.5 text-base font-semibold disabled:opacity-50 shadow-lg shadow-primary-500/30"
          :disabled="loading || !ownerAccessCode.trim()"
          @click="handleOwnerLogin"
        >
          {{ loading ? "登录中..." : "管理中介邀请码" }}
        </button>
      </div>

      <p class="text-center mt-6 text-sm text-gray-400">
        {{
          activeRole === "teacher"
            ? "首次使用会进入教员资料表单"
            : activeRole === "admin"
              ? "邀请码由平台老板统一发放和停用"
              : "默认访问码可在后端配置中修改"
        }}
      </p>
    </div>
  </div>
</template>
