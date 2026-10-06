<script setup lang="ts">
import { computed, ref } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { showToast } from "vant";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const form = ref({
  invite_code: String(route.query.inviteCode || ""),
  name: "",
  gender: "" as "" | "male" | "female",
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

const phoneError = ref("");
const inviteError = ref("");
const passwordError = ref("");
const nameError = ref("");
const wechatError = ref("");
const schoolError = ref("");
const genderError = ref("");

const phoneField = ref<{ focus: () => void } | null>(null);
const inviteField = ref<{ focus: () => void } | null>(null);
const passwordField = ref<{ focus: () => void } | null>(null);
const nameField = ref<{ focus: () => void } | null>(null);
const wechatField = ref<{ focus: () => void } | null>(null);
const schoolField = ref<{ focus: () => void } | null>(null);
const genderRow = ref<HTMLElement | null>(null);

// 与后端 PasswordPolicy 保持一致：至少 6 位且同时包含字母和数字
const passwordChecks = computed(() => [
  { label: "至少 6 位", ok: form.value.password.length >= 6 },
  { label: "含字母", ok: /[A-Za-z]/.test(form.value.password) },
  { label: "含数字", ok: /\d/.test(form.value.password) },
]);
const passwordStrength = computed(() => {
  const passed = passwordChecks.value.filter((c) => c.ok).length;
  if (passed === 3) return { level: 3, label: "强", cls: "bg-success", text: "text-success-deep" };
  if (passed === 2) return { level: 2, label: "中", cls: "bg-warning", text: "text-warning-deep" };
  return { level: passed, label: "弱", cls: "bg-danger", text: "text-danger-deep" };
});

function getRedirectPath() {
  const redirect = route.query.redirect;
  return typeof redirect === "string" && redirect.startsWith("/teacher/") ? redirect : "/teacher/profile";
}

function validatePhone(): boolean {
  const phone = form.value.phone.trim().replace(/\s+/g, "");
  if (!phone) {
    phoneError.value = "请输入手机号";
    return false;
  }
  if (!/^1\d{10}$/.test(phone)) {
    phoneError.value = "请输入 1 开头的 11 位手机号";
    return false;
  }
  phoneError.value = "";
  return true;
}

function validateInviteCode(): boolean {
  if (!form.value.invite_code.trim()) {
    inviteError.value = "请输入中介邀请码";
    return false;
  }
  inviteError.value = "";
  return true;
}

function validatePassword(): boolean {
  if (!form.value.password) {
    passwordError.value = "请设置登录密码";
    return false;
  }
  if (passwordStrength.value.level < 3) {
    passwordError.value = "密码需至少 6 位，且同时包含字母和数字";
    return false;
  }
  passwordError.value = "";
  return true;
}

function validateName(): boolean {
  if (!form.value.name.trim()) {
    nameError.value = "请输入真实姓名";
    return false;
  }
  nameError.value = "";
  return true;
}

function validateWechatId(): boolean {
  if (!form.value.wechat_id.trim()) {
    wechatError.value = "请输入微信号，中介将用它联系你";
    return false;
  }
  wechatError.value = "";
  return true;
}

function validateSchool(): boolean {
  if (!form.value.school.trim()) {
    schoolError.value = "请输入毕业或在读院校";
    return false;
  }
  schoolError.value = "";
  return true;
}

function validateGender(): boolean {
  if (!form.value.gender) {
    genderError.value = "请选择性别";
    return false;
  }
  genderError.value = "";
  return true;
}

async function handleRegister() {
  const steps: Array<[() => boolean, () => void]> = [
    [validatePhone, () => phoneField.value?.focus()],
    [validateInviteCode, () => inviteField.value?.focus()],
    [validatePassword, () => passwordField.value?.focus()],
    [validateName, () => nameField.value?.focus()],
    [validateWechatId, () => wechatField.value?.focus()],
    [validateSchool, () => schoolField.value?.focus()],
    [validateGender, () => genderRow.value?.scrollIntoView({ block: "center" })],
  ];
  for (const [validate, focusFirst] of steps) {
    if (!validate()) {
      focusFirst();
      return;
    }
  }
  const { gender } = form.value;
  if (gender !== "male" && gender !== "female") return;
  loading.value = true;
  try {
    await auth.phoneInviteRegister({
      phone: form.value.phone.trim().replace(/\s+/g, ""),
      invite_code: form.value.invite_code.trim(),
      password: form.value.password,
      name: form.value.name.trim(),
      gender,
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
  } catch (e) {
    showToast(getApiErrorMessage(e, "注册失败"));
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen bg-page pb-20 mx-auto max-w-2xl">
    <van-nav-bar title="教员注册" left-arrow @click-left="router.back()" />

    <div class="p-4 space-y-4">
      <div class="bg-white rounded-2xl shadow-sm">
        <div class="px-4 pb-1 pt-4 text-xs font-medium text-muted">账号信息</div>
        <van-field
          ref="phoneField"
          v-model="form.phone"
          label="手机号"
          placeholder="请输入手机号"
          type="tel"
          maxlength="11"
          required
          :error-message="phoneError"
          @update:model-value="phoneError = ''"
          @blur="validatePhone"
        />
        <van-field
          ref="inviteField"
          v-model="form.invite_code"
          label="邀请码"
          placeholder="请输入中介邀请码"
          required
          :error-message="inviteError"
          @update:model-value="inviteError = ''"
          @blur="validateInviteCode"
        />
        <van-field
          ref="passwordField"
          v-model="form.password"
          label="密码"
          placeholder="设置登录密码"
          :type="showPassword ? 'text' : 'password'"
          required
          :error-message="passwordError"
          @update:model-value="passwordError = ''"
          @blur="validatePassword"
        >
          <template #button>
            <van-icon
              :name="showPassword ? 'eye-o' : 'closed-eye'"
              size="18"
              color="var(--st-text-muted)"
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
              :class="i <= passwordStrength.level ? passwordStrength.cls : 'bg-surface-soft'"
            />
          </div>
          <div class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span class="font-medium" :class="passwordStrength.text">密码强度：{{ passwordStrength.label }}</span>
            <span
              v-for="check in passwordChecks"
              :key="check.label"
              :class="check.ok ? 'text-success-deep' : 'text-muted'"
            >
              {{ check.ok ? "✓" : "○" }} {{ check.label }}
            </span>
          </div>
        </div>
      </div>

      <div class="bg-white rounded-2xl shadow-sm">
        <div class="px-4 pb-1 pt-4 text-xs font-medium text-muted">基本信息</div>
        <van-field
          ref="nameField"
          v-model="form.name"
          label="姓名"
          placeholder="请输入真实姓名"
          required
          :error-message="nameError"
          @update:model-value="nameError = ''"
          @blur="validateName"
        />
        <van-field
          ref="wechatField"
          v-model="form.wechat_id"
          label="微信号"
          placeholder="用于中介联系你"
          required
          :error-message="wechatError"
          @update:model-value="wechatError = ''"
          @blur="validateWechatId"
        />

        <div ref="genderRow" class="flex items-center justify-between px-4 py-3">
          <span class="text-sm text-secondary"><span class="text-danger">*</span> 性别</span>
          <van-radio-group v-model="form.gender" direction="horizontal" @update:model-value="genderError = ''">
            <van-radio name="male">男</van-radio>
            <van-radio name="female">女</van-radio>
          </van-radio-group>
        </div>
        <p v-if="genderError" class="px-4 pb-2 text-xs text-danger">{{ genderError }}</p>
      </div>

      <div class="bg-white rounded-2xl shadow-sm">
        <div class="px-4 pb-1 pt-4 text-xs font-medium text-muted">院校信息</div>
        <van-field
          ref="schoolField"
          v-model="form.school"
          label="院校"
          placeholder="毕业/在读院校"
          required
          :error-message="schoolError"
          @update:model-value="schoolError = ''"
          @blur="validateSchool"
        />
        <van-field v-model="form.major" label="专业" placeholder="所学专业" />
        <van-field v-model="form.grade" label="年级" placeholder="如：研二" />

        <div class="flex items-center justify-between px-4 py-3">
          <span class="text-sm text-secondary">985 院校</span>
          <van-switch v-model="form.is_985" size="22" />
        </div>

        <div class="flex items-center justify-between px-4 py-3">
          <span class="text-sm text-secondary">211 院校</span>
          <van-switch v-model="form.is_211" size="22" />
        </div>

        <div class="flex items-center justify-between px-4 py-3">
          <span class="text-sm text-secondary">双一流院校</span>
          <van-switch v-model="form.is_double_first_class" size="22" />
        </div>
      </div>

      <div class="bg-white rounded-2xl shadow-sm">
        <div class="px-4 pb-1 pt-4 text-xs font-medium text-muted">优势亮点（选填）</div>
        <van-field
          v-model="form.highlights"
          label="优势"
          placeholder="如：有三年家教经验，擅长提分"
          type="textarea"
          rows="2"
          autosize
        />
      </div>

      <AppButton
        block
        size="lg"
        :disabled="loading"
        @click="handleRegister"
      >
        {{ loading ? "注册中..." : "完成注册" }}
      </AppButton>

      <p class="mt-4 text-center text-caption leading-5 text-muted">
        注册即代表同意
        <router-link class="text-brand-700" to="/terms">《用户协议》</router-link>
        与
        <router-link class="text-brand-700" to="/privacy">《隐私政策》</router-link>
      </p>
    </div>
  </div>
</template>