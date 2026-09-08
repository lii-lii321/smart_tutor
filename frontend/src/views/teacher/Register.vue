<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { showToast } from "vant";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const form = ref({
  invite_code: String(route.query.inviteCode || ""),
  name: "",
  gender: "male" as "male" | "female",
  phone: String(route.query.phone || ""),
  password: "",
  wechat_id: "",
  school: "",
  is_985: false,
  is_211: false,
  is_double_first_class: false,
  major: "",
  grade: "",
  highlights: "",
});

const loading = ref(false);
const showPassword = ref(false);

// 与后端 PasswordPolicy 保持一致：至少 6 位且同时包含字母和数字
const passwordChecks = computed(() => [
  { label: "至少 6 位", ok: form.value.password.length >= 6 },
  { label: "含字母", ok: /[A-Za-z]/.test(form.value.password) },
  { label: "含数字", ok: /\d/.test(form.value.password) },
]);
const passwordStrength = computed(() => {
  const passed = passwordChecks.value.filter((c) => c.ok).length;
  if (passed === 3) return { level: 3, label: "强", cls: "bg-emerald-500", text: "text-emerald-600" };
  if (passed === 2) return { level: 2, label: "中", cls: "bg-amber-500", text: "text-amber-600" };
  return { level: passed, label: "弱", cls: "bg-red-400", text: "text-red-500" };
});

function getRedirectPath() {
  const redirect = route.query.redirect;
  return typeof redirect === "string" && redirect.startsWith("/teacher/") ? redirect : "/teacher/profile";
}

async function handleRegister() {
  const phone = form.value.phone.trim().replace(/\s+/g, "");
  if (!/^1\d{10}$/.test(phone)) {
    showToast("请输入 11 位手机号");
    return;
  }
  if (!form.value.invite_code.trim()) {
    showToast("请输入邀请码");
    return;
  }
  if (passwordStrength.value.level < 3) {
    showToast("密码需至少 6 位，且同时包含字母和数字");
    return;
  }
  if (!form.value.name.trim() || !form.value.wechat_id.trim() || !form.value.school.trim()) {
    showToast("请填写姓名、微信号和院校");
    return;
  }
  loading.value = true;
  try {
    await auth.phoneInviteRegister({
      phone,
      invite_code: form.value.invite_code.trim(),
      password: form.value.password,
      name: form.value.name.trim(),
      gender: form.value.gender,
      wechat_id: form.value.wechat_id.trim(),
      school: form.value.school.trim(),
      is_985_211: form.value.is_985 || form.value.is_211,
      is_985: form.value.is_985,
      is_211: form.value.is_211,
      is_double_first_class: form.value.is_double_first_class,
      major: form.value.major.trim() || undefined,
      grade: form.value.grade.trim() || undefined,
      highlights: form.value.highlights.trim() || undefined,
    });
    showToast("注册成功");
    router.replace(getRedirectPath());
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "注册失败");
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-20 mx-auto max-w-2xl">
    <van-nav-bar title="教员注册" left-arrow @click-left="router.back()" />

    <div class="p-4 space-y-4">
      <div class="bg-white rounded-2xl p-5 shadow-sm">
        <van-field v-model="form.phone" label="手机号" placeholder="请输入手机号" type="tel" maxlength="11" required />
        <van-field v-model="form.invite_code" label="邀请码" placeholder="请输入中介邀请码" required />
        <van-field
          v-model="form.password"
          label="密码"
          placeholder="设置登录密码"
          :type="showPassword ? 'text' : 'password'"
          required
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
        <div v-if="form.password" class="px-4 pb-2 pt-1">
          <div class="flex gap-1">
            <div
              v-for="i in 3"
              :key="i"
              class="h-1 flex-1 rounded-full transition-colors"
              :class="i <= passwordStrength.level ? passwordStrength.cls : 'bg-gray-100'"
            />
          </div>
          <div class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span class="font-medium" :class="passwordStrength.text">密码强度：{{ passwordStrength.label }}</span>
            <span
              v-for="check in passwordChecks"
              :key="check.label"
              :class="check.ok ? 'text-emerald-600' : 'text-gray-400'"
            >
              {{ check.ok ? "✓" : "○" }} {{ check.label }}
            </span>
          </div>
        </div>
        <van-field v-model="form.name" label="姓名" placeholder="请输入真实姓名" required />
        <van-field v-model="form.wechat_id" label="微信号" placeholder="用于中介联系你" required />
        <van-field v-model="form.school" label="院校" placeholder="毕业/在读院校" required />
        <van-field v-model="form.major" label="专业" placeholder="所学专业" />
        <van-field v-model="form.grade" label="年级" placeholder="如：研二" />
        <van-field
          v-model="form.highlights"
          label="优势"
          placeholder="如：有三年家教经验，擅长提分"
          type="textarea"
          rows="2"
          autosize
        />

        <div class="flex items-center justify-between px-4 py-3">
          <span class="text-sm text-gray-600">性别</span>
          <van-radio-group v-model="form.gender" direction="horizontal">
            <van-radio name="male">男</van-radio>
            <van-radio name="female">女</van-radio>
          </van-radio-group>
        </div>

        <div class="flex items-center justify-between px-4 py-3">
          <span class="text-sm text-gray-600">985 院校</span>
          <van-switch v-model="form.is_985" size="22" />
        </div>

        <div class="flex items-center justify-between px-4 py-3">
          <span class="text-sm text-gray-600">211 院校</span>
          <van-switch v-model="form.is_211" size="22" />
        </div>

        <div class="flex items-center justify-between px-4 py-3">
          <span class="text-sm text-gray-600">双一流院校</span>
          <van-switch v-model="form.is_double_first_class" size="22" />
        </div>
      </div>

      <button
        class="w-full header-gradient text-white rounded-2xl py-4 text-base font-semibold shadow-lg shadow-primary-500/30 disabled:opacity-50"
        :disabled="loading"
        @click="handleRegister"
      >
        {{ loading ? "注册中..." : "完成注册" }}
      </button>
    </div>
  </div>
</template>
