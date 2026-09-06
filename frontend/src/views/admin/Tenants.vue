<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { showToast, showConfirmDialog } from "vant";
import { useAuthStore } from "@/stores/auth";
import { tenantsApi, type TeacherAdmin, type TenantAdmin } from "@/api/tenants";

const router = useRouter();
const auth = useAuthStore();

// 演示数据相关入口只在开发构建暴露
const isDevBuild = import.meta.env.DEV;

const tenants = ref<TenantAdmin[]>([]);
const loading = ref(false);
const submitting = ref(false);
const seeding = ref(false);
const tenantName = ref("");
const contactWechat = ref("");
const customInviteCode = ref("");
const teachers = ref<TeacherAdmin[]>([]);
const teachersLoading = ref(false);

onMounted(() => {
  loadTenants();
  loadTeachers();
});

async function loadTenants() {
  loading.value = true;
  try {
    tenants.value = await tenantsApi.list();
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "加载中介列表失败");
  } finally {
    loading.value = false;
  }
}

async function loadTeachers() {
  teachersLoading.value = true;
  try {
    teachers.value = await tenantsApi.listTeachers();
  } catch {
    teachers.value = [];
  } finally {
    teachersLoading.value = false;
  }
}

async function seedDemo() {
  seeding.value = true;
  try {
    await tenantsApi.seedDemo();
    showToast("示例数据已补齐");
    await Promise.all([loadTenants(), loadTeachers()]);
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "补充失败");
  } finally {
    seeding.value = false;
  }
}

async function createTenant() {
  if (!tenantName.value.trim() || !contactWechat.value.trim()) {
    showToast("请填写中介名称和微信");
    return;
  }
  submitting.value = true;
  try {
    const tenant = await tenantsApi.create({
      tenant_name: tenantName.value.trim(),
      contact_wechat: contactWechat.value.trim(),
      invite_code: customInviteCode.value.trim() || undefined,
    });
    tenants.value.unshift(tenant);
    if (tenant.initial_password) {
      await showInitialPassword(tenant.tenant_name, tenant.invite_code, tenant.initial_password);
    } else {
      showToast("已创建邀请码");
    }
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "创建失败");
  } finally {
    submitting.value = false;
  }
}

async function resetPassword(tenant: TenantAdmin) {
  try {
    await showConfirmDialog({
      title: "重置登录密码",
      message: `确定重置「${tenant.tenant_name}」的后台密码吗？原密码将立即失效。`,
    });
  } catch {
    return;
  }
  try {
    const updated = await tenantsApi.resetPassword(tenant.id);
    if (updated.initial_password) {
      await showInitialPassword(tenant.tenant_name, tenant.invite_code, updated.initial_password);
    } else {
      showToast("密码已重置");
    }
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "重置失败");
  }
}

async function toggleBan(teacher: TeacherAdmin) {
  const action = teacher.is_banned ? "解封" : "封禁";
  try {
    await showConfirmDialog({
      title: `${action}教员？`,
      message: teacher.is_banned
        ? `解封后「${teacher.name}」可恢复正常投递。`
        : `封禁后「${teacher.name}」将无法投递和被推荐。`,
    });
  } catch {
    return;
  }
  try {
    const updated = await tenantsApi.setTeacherBan(teacher.id, !teacher.is_banned);
    const index = teachers.value.findIndex((item) => item.id === teacher.id);
    if (index >= 0) teachers.value[index] = updated;
    showToast(updated.is_banned ? "已封禁" : "已解封");
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "操作失败");
  }
}

async function showInitialPassword(name: string, inviteCode: string, password: string) {
  try {
    await showConfirmDialog({
      title: "初始登录密码",
      message: `${name}（${inviteCode}）的初始密码：${password}\n\n仅此一次展示，请立即复制并转达中介，关闭后无法再查看。`,
      confirmButtonText: "复制密码",
      cancelButtonText: "我已记下",
    });
    await navigator.clipboard.writeText(password);
    showToast("密码已复制");
  } catch {
    // 用户取消时不需要提示
  }
}

async function toggleTenant(tenant: TenantAdmin) {
  try {
    const updated = await tenantsApi.updateStatus(tenant.id, !tenant.is_active);
    const index = tenants.value.findIndex((item) => item.id === tenant.id);
    if (index >= 0) tenants.value[index] = updated;
    showToast(updated.is_active ? "已启用" : "已停用");
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "操作失败");
  }
}

function boardLink(tenant: TenantAdmin) {
  return `${window.location.origin}/teacher/board/${tenant.invite_code}`;
}

async function copyText(text: string, message: string) {
  try {
    await navigator.clipboard.writeText(text);
    showToast(message);
  } catch {
    showToast("复制失败，请手动复制");
  }
}

function logout() {
  auth.logout();
  router.push("/teacher/login");
}
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-8">
    <div class="dashboard-header mx-3 mt-2 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <div class="flex items-center justify-between">
        <div class="text-slate-900">
          <div class="text-lg font-bold">中介邀请码管理</div>
          <div class="mt-1 text-xs text-slate-500">给每个中介发放独立随机码</div>
        </div>
        <button class="rounded-lg bg-slate-100 px-3 py-2 text-sm text-slate-700" @click="logout">
          退出
        </button>
      </div>
    </div>

    <div class="p-4 space-y-4">
      <div class="grid grid-cols-3 gap-3">
        <div class="bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-2xl font-bold">{{ tenants.length }}</div>
          <div class="text-xs text-slate-400 mt-1">中介数</div>
        </div>
        <div class="bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-2xl font-bold">{{ teachers.length }}</div>
          <div class="text-xs text-slate-400 mt-1">教员数</div>
        </div>
        <div class="bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-2xl font-bold">{{ teachers.filter((t) => t.is_banned).length }}</div>
          <div class="text-xs text-slate-400 mt-1">封禁中</div>
        </div>
      </div>

      <div class="bg-white rounded-2xl p-5 shadow-sm space-y-3">
        <h3 class="font-semibold">新增中介</h3>
        <van-field v-model="tenantName" label="名称" placeholder="例如：成都成华张老师" clearable />
        <van-field v-model="contactWechat" label="微信" placeholder="用于你线下联系中介" clearable />
        <van-field
          v-model="customInviteCode"
          label="指定码"
          placeholder="可不填，系统自动生成"
          clearable
        />
        <button
          class="w-full header-gradient text-white rounded-xl py-3 text-base font-semibold disabled:opacity-50"
          :disabled="submitting"
          @click="createTenant"
        >
          {{ submitting ? "创建中..." : "生成中介邀请码" }}
        </button>
        <button
          v-if="isDevBuild"
          class="w-full bg-slate-100 text-slate-700 rounded-xl py-3 text-base font-semibold disabled:opacity-50"
          :disabled="seeding"
          @click="seedDemo"
        >
          {{ seeding ? "补充中..." : "补充示例数据（仅开发环境）" }}
        </button>
      </div>

      <div class="space-y-3">
        <div class="flex items-center justify-between">
          <h3 class="font-semibold">已发放邀请码</h3>
          <span class="text-xs text-slate-400">{{ tenants.length }} 个中介</span>
        </div>

        <div v-if="loading" class="bg-white rounded-2xl p-8 text-center">
          <van-loading color="#2563eb" />
        </div>

        <div v-else-if="tenants.length === 0" class="bg-white rounded-2xl p-8 text-center text-slate-400">
          还没有中介，先创建第一个邀请码
        </div>

        <div
          v-for="tenant in tenants"
          v-else
          :key="tenant.id"
          class="bg-white rounded-2xl p-4 shadow-sm space-y-3"
        >
          <div class="flex items-start justify-between gap-3">
            <div>
              <div class="font-semibold text-slate-900">{{ tenant.tenant_name }}</div>
              <div class="text-xs text-slate-400 mt-1">联系微信：{{ tenant.contact_wechat }}</div>
            </div>
            <button
              class="rounded-full px-3 py-1 text-xs"
              :class="tenant.is_active ? 'bg-blue-50 text-primary-600' : 'bg-slate-100 text-slate-500'"
              @click="toggleTenant(tenant)"
            >
              {{ tenant.is_active ? "启用中" : "已停用" }}
            </button>
          </div>

          <div class="rounded-xl bg-gray-50 p-3">
            <div class="text-xs text-slate-400 mb-1">中介登录邀请码</div>
            <div class="flex items-center justify-between gap-3">
              <div class="font-mono text-lg text-slate-900">{{ tenant.invite_code }}</div>
              <button
                class="text-sm text-primary-600"
                @click="copyText(tenant.invite_code, '已复制邀请码')"
              >
                复制
              </button>
            </div>
          </div>

          <div class="flex items-center justify-between gap-3">
            <span class="text-xs text-slate-400">后台凭邀请码 + 密码登录</span>
            <button class="text-sm text-amber-600" @click="resetPassword(tenant)">
              重置密码
            </button>
          </div>

          <div class="rounded-xl bg-gray-50 p-3">
            <div class="text-xs text-slate-400 mb-1">发给教员看的橱窗链接</div>
            <div class="text-xs text-slate-600 break-all">{{ boardLink(tenant) }}</div>
            <button
              class="mt-2 text-sm text-primary-600"
              @click="copyText(boardLink(tenant), '已复制橱窗链接')"
            >
              复制链接
            </button>
          </div>
        </div>

        <div class="bg-white rounded-2xl p-5 shadow-sm">
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-semibold">教员管理</h3>
            <span class="text-xs text-slate-400">{{ teachers.length }} 位</span>
          </div>
          <div v-if="teachersLoading" class="flex justify-center py-6">
            <van-loading color="#2563eb" />
          </div>
          <div v-else-if="teachers.length === 0" class="text-sm text-slate-400">暂无教员数据</div>
          <div v-else class="space-y-3">
            <div v-for="teacher in teachers" :key="teacher.id" class="rounded-xl bg-gray-50 p-3">
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="font-semibold">
                    {{ teacher.name }}
                    <span
                      v-if="teacher.is_banned"
                      class="ml-1 rounded-full bg-red-50 px-2 py-0.5 text-xs text-red-500"
                    >
                      已封禁
                    </span>
                  </div>
                  <div class="text-xs text-slate-400 mt-1">{{ teacher.school }} · {{ teacher.major || "未填写专业" }}</div>
                </div>
                <div class="flex shrink-0 items-center gap-2">
                  <div class="text-xs text-slate-500">{{ teacher.phone }}</div>
                  <button
                    class="rounded-lg px-2.5 py-1 text-xs"
                    :class="teacher.is_banned ? 'bg-blue-50 text-blue-600' : 'bg-red-50 text-red-500'"
                    @click="toggleBan(teacher)"
                  >
                    {{ teacher.is_banned ? "解封" : "封禁" }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
