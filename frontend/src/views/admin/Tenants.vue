<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { formatMoney } from "@/utils/format";
import { useRouter } from "vue-router";
import { showToast, showConfirmDialog } from "vant";
import { useAuthStore } from "@/stores/auth";
import { tenantsApi, type OwnerStats, type TeacherAdmin, type TenantAdmin } from "@/api/tenants";

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
// 教员管理：后端分页返回，支持姓名/手机号搜索与封禁状态筛选
const TEACHER_PAGE_SIZE = 20;
const teacherQuery = ref("");
const teacherBanFilter = ref<"all" | "active" | "banned">("all");
const teacherPage = ref(1);
const teacherHasMore = ref(false);
const stats = ref<OwnerStats | null>(null);

onMounted(() => {
  loadTenants();
  loadTeachers();
  loadStats();
});

async function loadStats() {
  try {
    stats.value = await tenantsApi.stats();
  } catch {
    stats.value = null;
  }
}

const funnelStages = computed(() => {
  if (!stats.value) return [];
  const f = stats.value.funnel;
  return [
    { label: "投递", count: f.applications_total },
    { label: "候选", count: f.shortlisted },
    { label: "付定金", count: f.deposit_paid },
    { label: "成交", count: f.completed },
  ];
});

function funnelPercent(count: number) {
  const max = funnelStages.value[0]?.count || 0;
  if (!max) return 0;
  // 以投递数为 100% 基准，转化率一目了然
  return Math.max(2, Math.round((count / max) * 100));
}

async function loadTenants() {
  loading.value = true;
  try {
    tenants.value = await tenantsApi.list();
  } catch (e) {
    showToast(getApiErrorMessage(e, "加载中介列表失败"));
  } finally {
    loading.value = false;
  }
}

async function loadTeachers(reset = true) {
  teachersLoading.value = true;
  if (reset) teacherPage.value = 1;
  try {
    const params: { q?: string; banned?: boolean; page: number; page_size: number } = {
      page: reset ? 1 : teacherPage.value,
      page_size: TEACHER_PAGE_SIZE,
    };
    if (teacherQuery.value.trim()) params.q = teacherQuery.value.trim();
    if (teacherBanFilter.value !== "all") params.banned = teacherBanFilter.value === "banned";
    const list = await tenantsApi.listTeachers(params);
    teachers.value = reset ? list : [...teachers.value, ...list];
    teacherPage.value = (reset ? 1 : teacherPage.value) + 1;
    teacherHasMore.value = list.length === TEACHER_PAGE_SIZE;
  } catch {
    if (reset) teachers.value = [];
  } finally {
    teachersLoading.value = false;
  }
}

let teacherSearchTimer: number | undefined;
function onTeacherFilterChange() {
  window.clearTimeout(teacherSearchTimer);
  teacherSearchTimer = window.setTimeout(() => loadTeachers(true), 400);
}

onUnmounted(() => {
  window.clearTimeout(teacherSearchTimer);
});

const teacherFilterOptions: { key: "all" | "active" | "banned"; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "active", label: "正常" },
  { key: "banned", label: "已封禁" },
];

function setTeacherBanFilter(key: "all" | "active" | "banned") {
  teacherBanFilter.value = key;
  loadTeachers(true);
}

async function seedDemo() {
  seeding.value = true;
  try {
    await tenantsApi.seedDemo();
    showToast("示例数据已补齐");
    await Promise.all([loadTenants(), loadTeachers()]);
  } catch (e) {
    showToast(getApiErrorMessage(e, "补充失败"));
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
  } catch (e) {
    showToast(getApiErrorMessage(e, "创建失败"));
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
  } catch (e) {
    showToast(getApiErrorMessage(e, "重置失败"));
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
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
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
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
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
  <div class="min-h-screen bg-gray-50 pb-8 mx-auto max-w-3xl">
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
      <!-- 经营看板 -->
      <div v-if="stats" class="bg-white rounded-2xl p-5 shadow-sm">
        <h3 class="flex items-center gap-1.5 font-semibold mb-3">
          <van-icon name="chart-trending-o" /> 经营看板
        </h3>
        <div class="grid grid-cols-4 gap-2 text-center">
          <div class="rounded-xl bg-slate-50 p-2.5">
            <div class="text-lg font-bold text-slate-900">{{ stats.orders_recruiting }}</div>
            <div class="text-[11px] text-slate-400">在招订单</div>
          </div>
          <div class="rounded-xl bg-slate-50 p-2.5">
            <div class="text-lg font-bold text-slate-900">{{ stats.orders_completed }}</div>
            <div class="text-[11px] text-slate-400">已成交</div>
          </div>
          <div class="rounded-xl bg-slate-50 p-2.5">
            <div class="text-lg font-bold text-emerald-600">{{ formatMoney(stats.gmv_total) }}</div>
            <div class="text-[11px] text-slate-400">累计收入</div>
          </div>
          <div class="rounded-xl bg-slate-50 p-2.5">
            <div class="text-lg font-bold text-red-500">{{ formatMoney(stats.refund_total) }}</div>
            <div class="text-[11px] text-slate-400">退款支出</div>
          </div>
        </div>
        <div class="mt-3 rounded-xl bg-slate-50 p-3">
          <div class="mb-2 text-xs font-medium text-slate-500">投递漏斗（历史到达口径）</div>
          <div class="space-y-1.5">
            <div
              v-for="stage in funnelStages"
              :key="stage.label"
              class="flex items-center gap-2 text-xs"
            >
              <span class="w-12 shrink-0 text-slate-500">{{ stage.label }}</span>
              <div class="h-4 flex-1 overflow-hidden rounded bg-white">
                <div
                  class="h-full rounded bg-[#1a365d]"
                  :style="{ width: funnelPercent(stage.count) + '%' }"
                />
              </div>
              <span class="w-10 shrink-0 text-right font-semibold text-slate-700">{{ stage.count }}</span>
            </div>
          </div>
          <div
            v-for="item in stats.ranking.slice(0, 5)"
            :key="item.tenant_id"
            class="flex items-center justify-between border-t border-slate-100 py-2 text-xs"
          >
            <span class="min-w-0 truncate font-medium text-slate-700">
              {{ item.tenant_name }}
              <span v-if="!item.is_active" class="ml-1 text-slate-400">(停用)</span>
            </span>
            <span class="shrink-0 text-slate-500">
              {{ item.orders_completed }} 单成交 · 收入 {{ formatMoney(item.gmv) }}
            </span>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-3 gap-3">
        <div class="bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-2xl font-bold">{{ tenants.length }}</div>
          <div class="text-xs text-slate-400 mt-1">中介数</div>
        </div>
        <div class="bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-2xl font-bold">{{ stats?.teacher_count ?? teachers.length }}</div>
          <div class="text-xs text-slate-400 mt-1">教员数</div>
        </div>
        <div class="bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-2xl font-bold">{{ stats?.banned_teacher_count ?? 0 }}</div>
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
            <span class="text-xs text-slate-400">共 {{ stats?.teacher_count ?? teachers.length }} 位</span>
          </div>
          <div class="mb-3 space-y-2">
            <van-field
              v-model="teacherQuery"
              placeholder="搜索姓名或手机号"
              clearable
              class="rounded-lg border border-gray-200"
              @update:model-value="onTeacherFilterChange"
            />
            <div class="flex gap-1.5">
              <button
                v-for="opt in teacherFilterOptions"
                :key="opt.key"
                class="rounded-full px-3 py-1 text-xs font-medium"
                :class="teacherBanFilter === opt.key ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-500'"
                @click="setTeacherBanFilter(opt.key)"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
          <div v-if="teachersLoading" class="flex justify-center py-6">
            <van-loading color="#2563eb" />
          </div>
          <div v-else-if="teachers.length === 0" class="text-sm text-slate-400">
            {{ teacherQuery || teacherBanFilter !== "all" ? "没有符合条件的教员" : "暂无教员数据" }}
          </div>
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
            <button
              v-if="teacherHasMore && !teachersLoading"
              class="w-full rounded-lg bg-slate-100 py-2 text-sm text-slate-600"
              @click="loadTeachers(false)"
            >
              加载更多
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>