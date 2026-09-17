<script setup lang="ts">
/**
 * 注销账号弹层（合规：个人信息删除权）。
 * 密码确认后不可逆执行：PII 匿名化、简历删除、立即登出；财务流水按法规保留。
 */
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { getApiErrorMessage } from "@/utils/apiError";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";
import { getLastInviteCode } from "@/utils/inviteCode";
import { showToast } from "vant";
import { appConfirm } from "@/composables/appConfirm";

const show = defineModel<boolean>("show", { default: false });

const auth = useAuthStore();
const router = useRouter();

const password = ref("");
const submitting = ref(false);

watch(show, (visible) => {
  if (visible) {
    password.value = "";
  }
});

async function confirmDeactivate() {
  if (!password.value) {
    showToast("请输入密码确认身份");
    return;
  }
  // 二次确认：不可逆操作必须显式知晓后果
  const ok = await appConfirm({
    title: "确认注销？",
    message: "个人信息与简历将被删除且不可恢复；投递与财务记录按法规要求保留。注销后需重新注册才能再次使用。",
    confirmText: "永久注销",
    danger: true,
  });
  if (!ok) return;

  submitting.value = true;
  try {
    await authApi.deactivateAccount(password.value);
    showToast("账号已注销");
    show.value = false;
    const inviteCode = getLastInviteCode();
    auth.logout();
    router.replace({ path: "/teacher/login", query: { inviteCode } });
  } catch (e) {
    showToast(getApiErrorMessage(e, "注销失败"));
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <van-popup v-model:show="show" round position="bottom" close-on-click-overlay>
    <div class="p-4">
      <div class="mb-1 text-base font-semibold text-red-600">注销账号</div>
      <div class="mb-3 text-xs leading-5 text-slate-500">
        注销后<b>不可恢复</b>：姓名、手机号、微信号、简历等个人信息将被删除，
        投递与财务记录按法规要求保留。原手机号可重新注册。
      </div>
      <van-field
        v-model="password"
        label="登录密码"
        placeholder="输入密码确认身份"
        type="password"
      />
      <button
        class="mt-3 w-full rounded-xl bg-red-500 py-3 text-sm font-semibold text-white disabled:opacity-50"
        :disabled="submitting"
        @click="confirmDeactivate"
      >
        {{ submitting ? "注销中..." : "确认注销" }}
      </button>
    </div>
  </van-popup>
</template>
