<script setup lang="ts">
/** 修改登录密码弹层（自 Profile.vue 拆出）。提交成功后后端会使旧 token 失效。 */
import { ref, watch } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { authApi } from "@/api/auth";
import { showToast } from "vant";

const show = defineModel<boolean>("show", { default: false });

const pwSaving = ref(false);
const pwForm = ref({ oldPassword: "", newPassword: "" });

watch(show, (visible) => {
  if (visible) {
    pwForm.value = { oldPassword: "", newPassword: "" };
  }
});

async function submitPassword() {
  if (pwForm.value.oldPassword.length < 6 || pwForm.value.newPassword.length < 6) {
    showToast("密码至少 6 位");
    return;
  }
  if (!/[A-Za-z]/.test(pwForm.value.newPassword) || !/\d/.test(pwForm.value.newPassword)) {
    showToast("新密码需同时包含字母和数字");
    return;
  }
  if (pwForm.value.oldPassword === pwForm.value.newPassword) {
    showToast("新密码不能与原密码相同");
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
      <div class="mb-3 text-base font-semibold text-slate-950">修改登录密码</div>
      <van-field
        v-model="pwForm.oldPassword"
        label="原密码"
        placeholder="请输入原密码"
        type="password"
      />
      <van-field
        v-model="pwForm.newPassword"
        label="新密码"
        placeholder="至少 6 位，含字母和数字"
        type="password"
      />
      <button
        class="mt-3 w-full rounded-xl bg-slate-700 py-3 text-sm font-semibold text-white disabled:opacity-50"
        :disabled="pwSaving"
        @click="submitPassword"
      >
        {{ pwSaving ? "提交中..." : "确认修改" }}
      </button>
    </div>
  </van-popup>
</template>
