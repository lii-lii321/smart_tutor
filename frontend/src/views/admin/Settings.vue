<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { authApi } from "@/api/auth";
import { tenantsApi, type MyTeacher } from "@/api/tenants";
import client from "@/api/client";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast, showConfirmDialog } from "vant";

const router = useRouter();
const auth = useAuthStore();

const boardOrigin = window.location.origin;
const inviteLink = ref(`${boardOrigin}/teacher/board/${auth.tenant?.invite_code || "tx886"}`);

const pwForm = ref({ oldPassword: "", newPassword: "" });
const pwSaving = ref(false);

const teachers = ref<MyTeacher[]>([]);
const teachersLoading = ref(false);

async function loadTeachers() {
  teachersLoading.value = true;
  try {
    teachers.value = await tenantsApi.myTeachers();
  } catch {
    teachers.value = [];
  } finally {
    teachersLoading.value = false;
  }
}
loadTeachers();

const exporting = ref(false);

async function exportTeachers() {
  exporting.value = true;
  try {
    const res = await client.get(tenantsApi.myTeachersExportUrl(), { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = `我的教员_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  } catch {
    showToast("导出失败，请重试");
  } finally {
    exporting.value = false;
  }
}

async function toggleBlacklist(teacher: MyTeacher) {
  const action = teacher.is_blacklisted ? "移出黑名单" : "拉黑";
  try {
    await showConfirmDialog({
      title: `${action}？`,
      message: teacher.is_blacklisted
        ? `移出后「${teacher.name}」可重新投递本中介的订单。`
        : teacher.violation_count > 0
          ? `该教员有 ${teacher.violation_count} 次违约记录。拉黑后其待审投递将被拒绝，且无法再投递本中介订单。`
          : `拉黑后「${teacher.name}」的待审投递将被拒绝，且无法再投递本中介订单。`,
    });
  } catch {
    return;
  }
  try {
    if (teacher.is_blacklisted) {
      await tenantsApi.unblacklist(teacher.teacher_id);
      showToast("已移出黑名单");
    } else {
      await tenantsApi.blacklist(teacher.teacher_id, "中介手动拉黑");
      showToast("已拉黑");
    }
    await loadTeachers();
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "操作失败");
  }
}

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
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "修改失败");
  } finally {
    pwSaving.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-20">
    <van-nav-bar title="设置" left-arrow @click-left="router.push('/admin/dashboard')" />

    <div class="p-4 space-y-4">
      <!-- 基本信息 -->
      <div class="bg-white rounded-2xl p-5 shadow-sm">
        <h3 class="mb-4 flex items-center gap-1.5 font-semibold">
          <van-icon name="setting-o" /> 基本信息
        </h3>
        <van-field label="中介名称" :model-value="auth.tenant?.tenant_name || ''" readonly />
        <van-field label="邀请码" :model-value="auth.tenant?.invite_code || ''" readonly />
      </div>

      <!-- 橱窗链接 -->
      <div class="bg-white rounded-2xl p-5 shadow-sm">
        <h3 class="mb-4 flex items-center gap-1.5 font-semibold">
          <van-icon name="link-o" /> 教员橱窗链接
        </h3>
        <div class="bg-gray-50 rounded-xl p-3 text-xs text-gray-600 break-all mb-3">
          {{ inviteLink }}
        </div>
        <button
          class="w-full bg-primary-50 text-primary-600 rounded-xl py-2.5 text-sm font-semibold"
          @click="copyLink"
        >
          <van-icon name="records" class="mr-1" /> 复制链接
        </button>
      </div>

      <!-- 我的教员 -->
      <div class="bg-white rounded-2xl p-5 shadow-sm">
        <div class="mb-3 flex items-center justify-between">
          <h3 class="flex items-center gap-1.5 font-semibold">
            <van-icon name="friends-o" /> 我的教员
          </h3>
          <button
            v-if="teachers.length > 0"
            class="text-xs text-blue-600 disabled:opacity-50"
            :disabled="exporting"
            @click="exportTeachers"
          >
            {{ exporting ? "导出中..." : "导出名单" }}
          </button>
        </div>
        <div v-if="teachersLoading" class="flex justify-center py-4">
          <van-loading color="#2563eb" />
        </div>
        <div v-else-if="teachers.length === 0" class="text-sm text-gray-400">
          还没有教员投递过你的订单。收到投递后，可在这里查看信用并管理。
        </div>
        <div v-else class="space-y-2">
          <div
            v-for="teacher in teachers"
            :key="teacher.teacher_id"
            class="flex items-center justify-between gap-2 rounded-xl bg-gray-50 p-3"
          >
            <div class="min-w-0 text-sm">
              <div class="font-medium text-gray-800">
                {{ teacher.name }}
                <span
                  v-if="teacher.is_blacklisted"
                  class="ml-1 rounded-full bg-red-50 px-2 py-0.5 text-[10px] text-red-500"
                >
                  已拉黑
                </span>
              </div>
              <div class="mt-0.5 truncate text-xs text-gray-400">
                {{ teacher.phone }} · 投递 {{ teacher.applications_total }} 次
                <span class="text-emerald-600">成交 {{ teacher.completed_count }}</span>
                <span :class="teacher.violation_count > 0 ? 'text-red-500' : ''">
                  违约 {{ teacher.violation_count }}
                </span>
                <span v-if="teacher.avg_rating != null" class="text-amber-600">
                  {{ teacher.avg_rating }}★
                </span>
              </div>
            </div>
            <button
              class="shrink-0 rounded-lg px-2.5 py-1.5 text-xs"
              :class="teacher.is_blacklisted ? 'bg-blue-50 text-blue-600' : 'bg-red-50 text-red-500'"
              @click="toggleBlacklist(teacher)"
            >
              {{ teacher.is_blacklisted ? "移出" : "拉黑" }}
            </button>
          </div>
        </div>
        <div class="mt-2 text-xs text-gray-400">拉黑仅对本中介生效，教员仍可投递其他中介</div>
      </div>

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
        <button
          class="mt-3 w-full bg-primary-50 text-primary-600 rounded-xl py-2.5 text-sm font-semibold disabled:opacity-50"
          :disabled="pwSaving"
          @click="submitPassword"
        >
          {{ pwSaving ? "提交中..." : "确认修改" }}
        </button>
        <div class="mt-2 text-xs text-gray-400">忘记密码请联系平台老板重置</div>
      </div>

      <!-- 退出 -->
      <div class="bg-white rounded-2xl overflow-hidden shadow-sm">
        <van-cell title="退出登录" icon="revoke" @click="auth.logout(); router.push('/')" />
      </div>
    </div>
    <AdminTabbar />
  </div>
</template>
