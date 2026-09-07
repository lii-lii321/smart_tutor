<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { showToast } from "vant";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

// 访问码等演示提示只在开发构建显示
const isDevBuild = import.meta.env.DEV;

type Role = "teacher" | "admin" | "owner";
const roleMeta: Record<Role, { tab: string; icon: string; title: string; tagline: string; note: string; cta: string }> = {
  teacher: {
    tab: "教员登录",
    icon: "manager-o",
    title: "智派 · 教员端",
    tagline: "手机号 + 密码登录，未注册将完善资料",
    note: "首次使用会进入教员资料表单；密码遗忘请联系中介重置",
    cta: "登录",
  },
  admin: {
    tab: "中介登录",
    icon: "shop-o",
    title: "智派 · 中介后台",
    tagline: "用平台发放的邀请码和密码进入中介后台",
    note: "邀请码和初始密码由平台老板统一发放；密码遗忘可联系老板重置",
    cta: "进入中介后台",
  },
  owner: {
    tab: "老板入口",
    icon: "setting-o",
    title: "智派 · 老板管理",
    tagline: "创建、停用和复制中介邀请码",
    note: "默认访问码可在后端配置中修改",
    cta: "管理中介邀请码",
  },
};

function normalizeTab(value: unknown): Role {
  return value === "admin" || value === "owner" ? value : "teacher";
}
const activeRole = ref<Role>(normalizeTab(route.query.tab));
const roleOrder: Role[] = ["teacher", "admin", "owner"];

const phone = ref("");
const password = ref("");
const inviteCode = ref(String(route.query.inviteCode || ""));
const showPassword = ref(false);
const phoneError = ref("");

const adminInviteCode = ref(String(route.query.inviteCode || ""));
const adminPassword = ref("");
const showAdminPassword = ref(false);
const adminPasswordError = ref("");

const ownerAccessCode = ref("");
const showOwnerCode = ref(false);

const loading = ref(false);

const PHONE_KEY = "tutor_login_phone";
const INVITE_KEY = "tutor_login_invite";
const ADMIN_INVITE_KEY = "tutor_admin_invite";

onMounted(() => {
  // 回填上次成功登录的凭证，减少重复输入
  phone.value = localStorage.getItem(PHONE_KEY) || "";
  if (!inviteCode.value) {
    inviteCode.value = localStorage.getItem(INVITE_KEY) || "";
  }
  if (!adminInviteCode.value) {
    adminInviteCode.value = localStorage.getItem(ADMIN_INVITE_KEY) || "";
  }
});

const canSubmit = computed(() => {
  if (loading.value) return false;
  if (activeRole.value === "teacher") {
    return !!phone.value.trim() && !!inviteCode.value.trim() && password.value.length >= 6;
  }
  if (activeRole.value === "admin") {
    return !!adminInviteCode.value.trim() && adminPassword.value.length >= 6;
  }
  return !!ownerAccessCode.value.trim();
});

function switchRole(role: Role) {
  activeRole.value = role;
  phoneError.value = "";
  adminPasswordError.value = "";
}

function getRedirectPath() {
  const redirect = route.query.redirect;
  if (typeof redirect === "string" && (redirect.startsWith("/teacher/") || redirect.startsWith("/admin/") || redirect.startsWith("/owner/"))) {
    return redirect;
  }
  if (activeRole.value === "admin") return "/admin/dashboard";
  if (activeRole.value === "owner") return "/owner/tenants";
  return inviteCode.value.trim() ? `/teacher/board/${inviteCode.value.trim()}` : "/teacher/profile";
}

async function handleLogin() {
  const normalizedPhone = phone.value.trim().replace(/\s+/g, "");
  const normalizedInviteCode = inviteCode.value.trim();
  if (!/^1\d{10}$/.test(normalizedPhone)) {
    phoneError.value = "请输入 11 位手机号";
    return;
  }
  phoneError.value = "";
  if (!normalizedInviteCode) {
    showToast("请输入邀请码");
    return;
  }
  if (password.value.length < 6) {
    showToast("请输入至少 6 位密码");
    return;
  }
  loading.value = true;
  try {
    await auth.phoneInviteLogin(normalizedPhone, normalizedInviteCode, password.value);
    localStorage.setItem(PHONE_KEY, normalizedPhone);
    localStorage.setItem(INVITE_KEY, normalizedInviteCode);
    showToast("登录成功");
    router.replace(getRedirectPath());
  } catch (e: any) {
    if (e?.response?.status === 404) {
      showToast("请先完善教员资料");
      router.push({
        path: "/teacher/register",
        query: {
          phone: normalizedPhone,
          inviteCode: normalizedInviteCode,
          redirect: getRedirectPath(),
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
  if (adminPassword.value.length < 6) {
    adminPasswordError.value = "密码至少 6 位";
    return;
  }
  adminPasswordError.value = "";
  loading.value = true;
  try {
    await auth.tenantLogin(code, adminPassword.value);
    localStorage.setItem(ADMIN_INVITE_KEY, code);
    showToast("登录成功");
    router.replace(getRedirectPath());
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "登录失败");
  } finally {
    loading.value = false;
  }
}

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
    router.replace(getRedirectPath());
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "登录失败");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="login-page min-h-screen flex flex-col">
    <van-nav-bar :title="roleMeta[activeRole].tab" left-arrow @click-left="router.back()" />

    <div class="login-content flex-1 flex flex-col px-4 pb-24">
      <!-- 品牌区 -->
      <div class="login-identity text-center mb-5">
        <div class="w-20 h-20 mx-auto rounded-2xl header-gradient flex items-center justify-center shadow-lg shadow-primary-500/30 mb-4">
          <van-icon :name="roleMeta[activeRole].icon" size="40" color="#fff" />
        </div>
        <h2 class="text-xl font-bold">{{ roleMeta[activeRole].title }}</h2>
        <p class="text-gray-400 text-sm mt-1">{{ roleMeta[activeRole].tagline }}</p>
      </div>

      <div class="login-role-switch mb-4 grid grid-cols-3 rounded-xl bg-white p-1 shadow-sm">
        <button
          v-for="role in roleOrder"
          :key="role"
          class="rounded-lg py-2 text-sm font-semibold flex items-center justify-center gap-1"
          :class="activeRole === role ? 'bg-[#1a365d] text-white' : 'text-slate-500'"
          @click="switchRole(role)"
        >
          <van-icon :name="roleMeta[role].icon" size="15" />
          {{ roleMeta[role].tab }}
        </button>
      </div>

      <!-- 教员登录 -->
      <div v-if="activeRole === 'teacher'" class="login-form bg-white rounded-2xl p-5 shadow-sm space-y-4">
        <van-field
          v-model="phone"
          label="手机号"
          placeholder="请输入手机号"
          type="tel"
          maxlength="11"
          clearable
          :error-message="phoneError"
          @update:model-value="phoneError = ''"
          @keyup.enter="handleLogin"
        />
        <van-field
          v-model="password"
          label="密码"
          placeholder="请输入登录密码"
          :type="showPassword ? 'text' : 'password'"
          clearable
          @keyup.enter="handleLogin"
        >
          <template #button>
            <van-icon
              :name="showPassword ? 'eye-o' : 'closed-eye'"
              size="18"
              color="#94a3b8"
              @click="showPassword = !showPassword"
            />
          </template>
        </van-field>
        <van-field
          v-model="inviteCode"
          label="邀请码"
          placeholder="请输入中介邀请码"
          clearable
          @keyup.enter="handleLogin"
        />

        <button
          class="w-full header-gradient text-white rounded-xl py-3.5 text-base font-semibold disabled:opacity-50 shadow-lg shadow-primary-500/30 flex items-center justify-center gap-2"
          :disabled="!canSubmit"
          @click="handleLogin"
        >
          <van-loading v-if="loading" type="spinner" size="16" color="#fff" />
          {{ loading ? "登录中..." : roleMeta.teacher.cta }}
        </button>
      </div>

      <!-- 中介登录 -->
      <div v-else-if="activeRole === 'admin'" class="login-form bg-white rounded-2xl p-5 shadow-sm space-y-4">
        <van-field
          v-model="adminInviteCode"
          label="邀请码"
          placeholder="请输入中介邀请码"
          clearable
          @keyup.enter="handleAdminLogin"
        />
        <van-field
          v-model="adminPassword"
          label="密码"
          placeholder="请输入后台密码"
          :type="showAdminPassword ? 'text' : 'password'"
          clearable
          :error-message="adminPasswordError"
          @update:model-value="adminPasswordError = ''"
          @keyup.enter="handleAdminLogin"
        >
          <template #button>
            <van-icon
              :name="showAdminPassword ? 'eye-o' : 'closed-eye'"
              size="18"
              color="#94a3b8"
              @click="showAdminPassword = !showAdminPassword"
            />
          </template>
        </van-field>

        <button
          class="w-full header-gradient text-white rounded-xl py-3.5 text-base font-semibold disabled:opacity-50 shadow-lg shadow-primary-500/30 flex items-center justify-center gap-2"
          :disabled="!canSubmit"
          @click="handleAdminLogin"
        >
          <van-loading v-if="loading" type="spinner" size="16" color="#fff" />
          {{ loading ? "登录中..." : roleMeta.admin.cta }}
        </button>
      </div>

      <!-- 老板入口 -->
      <div v-else class="login-form bg-white rounded-2xl p-5 shadow-sm space-y-4">
        <van-field
          v-model="ownerAccessCode"
          label="访问码"
          placeholder="请输入老板访问码"
          :type="showOwnerCode ? 'text' : 'password'"
          clearable
          @keyup.enter="handleOwnerLogin"
        >
          <template #button>
            <van-icon
              :name="showOwnerCode ? 'eye-o' : 'closed-eye'"
              size="18"
              color="#94a3b8"
              @click="showOwnerCode = !showOwnerCode"
            />
          </template>
        </van-field>
        <div v-if="isDevBuild" class="text-xs text-slate-400">开发环境默认访问码：boss888（生产环境不会显示）</div>

        <button
          class="w-full header-gradient text-white rounded-xl py-3.5 text-base font-semibold disabled:opacity-50 shadow-lg shadow-primary-500/30 flex items-center justify-center gap-2"
          :disabled="!canSubmit"
          @click="handleOwnerLogin"
        >
          <van-loading v-if="loading" type="spinner" size="16" color="#fff" />
          {{ loading ? "登录中..." : roleMeta.owner.cta }}
        </button>
      </div>

      <p class="login-note text-center mt-5 text-sm">{{ roleMeta[activeRole].note }}</p>
    </div>
  </div>
</template>
