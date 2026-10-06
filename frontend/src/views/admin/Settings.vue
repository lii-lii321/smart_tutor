<script setup lang="ts">
import { ref } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";
import { DEFAULT_INVITE_CODE } from "@/utils/inviteCode";
import AdminShell from "@/components/admin/AdminShell.vue";
import AppButton from "@/components/ui/AppButton.vue";
import { showToast } from "vant";

const router = useRouter();
const auth = useAuthStore();

const boardOrigin = window.location.origin;
const inviteLink = ref(`${boardOrigin}/teacher/board/${auth.tenant?.invite_code || DEFAULT_INVITE_CODE}`);

const pwForm = ref({ oldPassword: "", newPassword: "" });
const pwSaving = ref(false);

async function copyLink() {
  try {
    await navigator.clipboard.writeText(inviteLink.value);
    showToast("已复制橱窗链接");
  } catch {
    showToast("复制失败，请长按链接手动复制");
  }
}

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
    await authApi.tenantChangePassword(pwForm.value.oldPassword, pwForm.value.newPassword);
    showToast("密码已更新");
    pwForm.value = { oldPassword: "", newPassword: "" };
  } catch (e) {
    showToast(getApiErrorMessage(e, "修改失败"));
  } finally {
    pwSaving.value = false;
  }
}
</script>

<template>
  <AdminShell>
    <van-nav-bar
      title="设置"
      left-arrow
      @click-left="router.push('/admin/dashboard')"
    />

    <div class="p-4 space-y-4">
      <!-- 基本信息 -->
      <div class="bg-white rounded-2xl p-5 shadow-sm">
        <h3 class="mb-4 flex items-center gap-1.5 font-semibold">
          <van-icon name="setting-o" /> 基本信息
        </h3>
        <van-field
          label="中介名称"
          :model-value="auth.tenant?.tenant_name || ''"
          readonly
        />
        <van-field
          label="邀请码"
          :model-value="auth.tenant?.invite_code || ''"
          readonly
        />
      </div>

      <!-- 橱窗链接 -->
      <div class="bg-white rounded-2xl p-5 shadow-sm">
        <h3 class="mb-4 flex items-center gap-1.5 font-semibold">
          <van-icon name="link-o" /> 教员橱窗链接
        </h3>
        <div class="bg-surface-soft rounded-xl p-3 text-xs text-secondary break-all mb-3">
          {{ inviteLink }}
        </div>
        <AppButton
          block
          size="md"
          variant="secondary"
          @click="copyLink"
        >
          <van-icon
            name="records"
            class="mr-1"
          /> 复制链接
        </AppButton>
      </div>

      <!-- 我的教员：已升格为独立页 /admin/teachers，这里只留入口 -->
      <van-cell
        title="教员管理"
        icon="friends-o"
        is-link
        @click="router.push('/admin/teachers')"
      >
        <template #label>
          <span class="text-xs text-muted">投递过你订单的教员名录、信用与拉黑管理</span>
        </template>
      </van-cell>

      <!-- 后台密码 -->
      <div class="bg-white rounded-2xl p-5 shadow-sm">
        <h3 class="mb-4 flex items-center gap-1.5 font-semibold">
          <van-icon name="shield-o" /> 后台登录密码
        </h3>
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
        <AppButton
          block
          size="md"
          class="mt-3"
          :disabled="pwSaving"
          @click="submitPassword"
        >
          {{ pwSaving ? "提交中..." : "确认修改" }}
        </AppButton>
        <div class="mt-2 text-xs text-muted">
          忘记密码请联系平台老板重置
        </div>
      </div>

      <!-- 退出 -->
      <div class="bg-white rounded-2xl overflow-hidden shadow-sm">
        <van-cell
          title="退出登录"
          icon="revoke"
          @click="auth.logout(); router.push('/')"
        />
      </div>
    </div>
  </AdminShell>
</template>
