<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { showToast } from "vant";
import { useAuthStore } from "@/stores/auth";
import { tenantsApi, type DemoTeacher, type TenantAdmin } from "@/api/tenants";

const router = useRouter();
const auth = useAuthStore();

const tenants = ref<TenantAdmin[]>([]);
const loading = ref(false);
const submitting = ref(false);
const seeding = ref(false);
const tenantName = ref("");
const contactWechat = ref("");
const customInviteCode = ref("");
const teachers = ref<DemoTeacher[]>([]);
const counts = ref({ tenants: 0, teachers: 0, resumes: 0 });

onMounted(loadTenants);

async function loadTenants() {
  loading.value = true;
  try {
    const data = await tenantsApi.demoData();
    tenants.value = data.tenants;
    teachers.value = data.teachers;
    counts.value = data.counts;
  } finally {
    loading.value = false;
  }
}

async function seedDemo() {
  seeding.value = true;
  try {
    const data = await tenantsApi.seedDemo();
    tenants.value = data.tenants;
    teachers.value = data.teachers;
    counts.value = data.counts;
    showToast("示例数据已补齐");
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
    counts.value.tenants += 1;
    tenantName.value = "";
    contactWechat.value = "";
    customInviteCode.value = "";
    showToast("已创建邀请码");
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "创建失败");
  } finally {
    submitting.value = false;
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

function copyText(text: string, message: string) {
  navigator.clipboard.writeText(text);
  showToast(message);
}

function logout() {
  auth.logout();
  router.push("/teacher/login");
}
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-8">
    <div class="header-gradient px-4 pt-12 pb-7">
      <div class="flex items-center justify-between">
        <div class="text-white">
          <div class="text-2xl font-bold">中介邀请码管理</div>
          <div class="text-sm opacity-80 mt-1">给每个中介发放独立随机码</div>
        </div>
        <button class="bg-white/20 rounded-xl px-3 py-2 text-white text-sm" @click="logout">
          退出
        </button>
      </div>
    </div>

    <div class="p-4 space-y-4">
      <div class="grid grid-cols-3 gap-3">
        <div class="bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-2xl font-bold">{{ counts.tenants }}</div>
          <div class="text-xs text-slate-400 mt-1">中介数</div>
        </div>
        <div class="bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-2xl font-bold">{{ counts.teachers }}</div>
          <div class="text-xs text-slate-400 mt-1">教员数</div>
        </div>
        <div class="bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-2xl font-bold">{{ counts.resumes }}</div>
          <div class="text-xs text-slate-400 mt-1">简历数</div>
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
          class="w-full bg-slate-100 text-slate-700 rounded-xl py-3 text-base font-semibold disabled:opacity-50"
          :disabled="seeding"
          @click="seedDemo"
        >
          {{ seeding ? "补充中..." : "补充示例数据" }}
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
            <h3 class="font-semibold">示例教员</h3>
            <span class="text-xs text-slate-400">{{ teachers.length }} 位</span>
          </div>
          <div v-if="teachers.length === 0" class="text-sm text-slate-400">暂无教员数据</div>
          <div v-else class="space-y-3">
            <div v-for="teacher in teachers" :key="teacher.id" class="rounded-xl bg-gray-50 p-3">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="font-semibold">{{ teacher.name }}</div>
                  <div class="text-xs text-slate-400 mt-1">{{ teacher.school }} · {{ teacher.major || "未填写专业" }}</div>
                </div>
                <div class="text-xs text-slate-500">{{ teacher.phone }}</div>
              </div>
              <div class="text-xs text-slate-600 mt-2">
                {{ teacher.teaching_subjects || "暂无科目" }} / {{ teacher.teaching_grades || "暂无年级" }}
              </div>
              <div class="text-xs text-slate-400 mt-1">{{ teacher.highlights || "暂无亮点" }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
