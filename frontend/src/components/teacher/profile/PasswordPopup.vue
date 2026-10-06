<script setup lang="ts">
/** 修改登录密码弹层（自 Profile.vue 拆出）。提交成功后后端会使旧 token 失效。 */
import { computed, ref, watch } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { authApi } from "@/api/auth";
import { showToast } from "vant";
import AppButton from "@/components/ui/AppButton.vue";

const show = defineModel<boolean>("show", { default: false });

const pwSaving = ref(false);
const pwForm = ref({ oldPassword: "", newPassword: "" });

const oldPasswordError = ref("");
const newPasswordError = ref("");

const oldPasswordField = ref<{ focus: () => void } | null>(null);
const newPasswordField = ref<{ focus: () => void } | null>(null);

watch(show, (visible) => {
  if (visible) {
    pwForm.value = { oldPassword: "", newPassword: "" };
    oldPasswordError.value = "";
    newPasswordError.value = "";
  }
});

// 与后端 PasswordPolicy 保持一致：至少 6 位且同时包含字母和数字（Register 同款口径）
const passwordChecks = computed(() => [
  { label: "至少 6 位", ok: pwForm.value.newPassword.length >= 6 },
  { label: "含字母", ok: /[A-Za-z]/.test(pwForm.value.newPassword) },
  { label: "含数字", ok: /\d/.test(pwForm.value.newPassword) },
]);
const passwordStrength = computed(() => {
  const passed = passwordChecks.value.filter((c) => c.ok).length;
  if (passed === 3) return { level: 3, label: "强", cls: "bg-success", text: "text-success-deep" };
  if (passed === 2) return { level: 2, label: "中", cls: "bg-warning", text: "text-warning-deep" };
  return { level: passed, label: "弱", cls: "bg-danger", text: "text-danger-deep" };
});

function validateOldPassword(): boolean {
  if (!pwForm.value.oldPassword) {
    oldPasswordError.value = "请输入原密码";
    return false;
  }
  if (pwForm.value.oldPassword.length < 6) {
    oldPasswordError.value = "密码至少 6 位";
    return false;
  }
  oldPasswordError.value = "";
  return true;
}

function validateNewPassword(): boolean {
  if (!pwForm.value.newPassword) {
    newPasswordError.value = "请设置新密码";
    return false;
  }
  if (passwordStrength.value.level < 3) {
    newPasswordError.value = "新密码需至少 6 位，且同时包含字母和数字";
    return false;
  }
  if (pwForm.value.newPassword === pwForm.value.oldPassword) {
    newPasswordError.value = "新密码不能与原密码相同";
    return false;
  }
  newPasswordError.value = "";
  return true;
}

async function submitPassword() {
  if (!validateOldPassword()) {
    oldPasswordField.value?.focus();
    return;
  }
  if (!validateNewPassword()) {
    newPasswordField.value?.focus();
    return;
  }
  pwSaving.value = true;
  try {
    await authApi.teacherChangePassword(pwForm.value.oldPassword, pwForm.value.newPassword);
    showToast("密码已更新");
    show.value = false;
    pwForm.value = { oldPassword: "", newPassword: "" };
  } catch (e) {
    showToast(getApiErrorMessage(e, "修改失败"));
  } finally {
    pwSaving.value = false;
  }
}
</script>

<template>
  <van-popup v-model:show="show" round position="bottom" close-on-click-overlay>
    <div class="p-4">
      <div class="mb-3 text-base font-semibold text-primary">修改登录密码</div>
      <van-field
        ref="oldPasswordField"
        v-model="pwForm.oldPassword"
        label="原密码"
        placeholder="请输入原密码"
        type="password"
        required
        :error-message="oldPasswordError"
        @update:model-value="oldPasswordError = ''"
        @blur="validateOldPassword"
      />
      <van-field
        ref="newPasswordField"
        v-model="pwForm.newPassword"
        label="新密码"
        placeholder="至少 6 位，含字母和数字"
        type="password"
        required
        :error-message="newPasswordError"
        @update:model-value="newPasswordError = ''"
        @blur="validateNewPassword"
      />
      <div v-if="pwForm.newPassword" class="px-4 pb-2 pt-1">
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
      <AppButton
        block
        size="lg"
        class="mt-3"
        :disabled="pwSaving"
        @click="submitPassword"
      >
        {{ pwSaving ? "提交中..." : "确认修改" }}
      </AppButton>
    </div>
  </van-popup>
</template>
