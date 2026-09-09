<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { resumesApi, type TeacherResume, type TeacherResumePayload } from "@/api/resumes";
import { authApi } from "@/api/auth";
import { notificationsApi, type NotificationItem } from "@/api/notifications";
import { financialApi } from "@/api/financial";
import { applicationsApi } from "@/api/applications";
import client from "@/api/client";
import TeacherTabbar from "@/components/TeacherTabbar.vue";
import { loadAMap, locateCurrentPosition } from "@/utils/amap";
import { getLastInviteCode } from "@/utils/inviteCode";
import { showConfirmDialog, showToast } from "vant";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();

const resumes = ref<TeacherResume[]>([]);
const loading = ref(false);
const saving = ref(false);
const editorVisible = ref(false);
const editingId = ref<number | null>(null);

const notifVisible = ref(false);
const notifLoading = ref(false);
const notifUnread = ref(0);
const notifications = ref<NotificationItem[]>([]);

async function openNotifications() {
  notifVisible.value = true;
  notifLoading.value = true;
  try {
    const data = await notificationsApi.mine();
    notifications.value = data.items;
    notifUnread.value = data.unread_count;
  } catch {
    showToast("通知加载失败");
  } finally {
    notifLoading.value = false;
  }
}

async function markAllRead() {
  try {
    await notificationsApi.readAll();
    notifications.value = notifications.value.map((n) => ({ ...n, is_read: true }));
    notifUnread.value = 0;
    showToast("已全部标记为已读");
  } catch {
    showToast("操作失败");
  }
}

// 我的费用结算单
const feesVisible = ref(false);
const feesLoading = ref(false);
const fees = ref<{
  total_paid: number;
  total_refunded: number;
  total_forfeit: number;
  records: {
    id: number;
    order_id: number;
    raw_order_id?: string | null;
    amount: number;
    type: string;
    remark?: string | null;
    created_at: string;
  }[];
} | null>(null);

const feeTypeLabels: Record<string, { label: string; sign: string; cls: string }> = {
  deposit_in: { label: "定金支付", sign: "-", cls: "text-slate-700" },
  balance_in: { label: "尾款支付", sign: "-", cls: "text-slate-700" },
  refund_out: { label: "退款到账", sign: "+", cls: "text-emerald-600" },
  forfeit: { label: "违约没收", sign: "-", cls: "text-red-500" },
};

async function openFees() {
  feesVisible.value = true;
  feesLoading.value = true;
  try {
    fees.value = await financialApi.myFees();
  } catch {
    showToast("费用加载失败");
  } finally {
    feesLoading.value = false;
  }
}

const feesExporting = ref(false);

async function exportFees() {
  feesExporting.value = true;
  try {
    const res = await client.get(financialApi.myFeesExportUrl(), { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = `我的费用_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  } catch {
    showToast("导出失败，请重试");
  } finally {
    feesExporting.value = false;
  }
}

// 收到的评价
const reviewsVisible = ref(false);
const reviewsLoading = ref(false);
const reviews = ref<{ id: number; order_id: number; rating: number; comment?: string | null; created_at: string }[]>([]);
const reviewsAvg = ref<number | null>(null);

async function openReviews() {
  reviewsVisible.value = true;
  reviewsLoading.value = true;
  try {
    reviews.value = await applicationsApi.myReviews();
    reviewCount.value = reviews.value.length;
    reviewsAvg.value = reviews.value.length
      ? Math.round((reviews.value.reduce((s, r) => s + r.rating, 0) / reviews.value.length) * 10) / 10
      : null;
  } catch {
    showToast("评价加载失败");
  } finally {
    reviewsLoading.value = false;
  }
}

const pwVisible = ref(false);
const pwSaving = ref(false);
const pwForm = ref({ oldPassword: "", newPassword: "" });

// 基础资料编辑：注册后仍可修正姓名/院校/微信号，并设置常驻地参与距离推荐
const profileVisible = ref(false);
const profileSaving = ref(false);
const profileForm = ref({
  name: "",
  gender: "male" as "male" | "female",
  wechat_id: "",
  school: "",
  major: "",
  grade: "",
  highlights: "",
  home_area: "",
});
const profileCoords = ref<{ lng: number; lat: number } | null>(null);
const locating = ref(false);

function openProfileEditor() {
  const t = auth.teacher;
  profileForm.value = {
    name: t?.name || "",
    gender: t?.gender === "female" ? "female" : "male",
    wechat_id: t?.wechat_id || "",
    school: t?.school || "",
    major: t?.major || "",
    grade: t?.grade || "",
    highlights: t?.highlights || "",
    home_area: t?.home_area || "",
  };
  profileCoords.value =
    t?.lng != null && t?.lat != null ? { lng: Number(t.lng), lat: Number(t.lat) } : null;
}

async function locateHomeArea() {
  if (locating.value) return;
  locating.value = true;
  try {
    const AMap = await loadAMap();
    const [lng, lat] = await locateCurrentPosition(AMap);
    profileCoords.value = { lng, lat };
    // 逆地理编码取"城市·区"粒度文本，避免暴露精确住址
    await new Promise<void>((resolve) => {
      const geocoder = new AMap.Geocoder();
      geocoder.getAddress([lng, lat], (status: string, result: any) => {
        if (status === "complete" && result?.regeocode) {
          const comp = result.regeocode.addressComponent || {};
          const city = String(comp.city || comp.province || "").replace(/市$/, "");
          const district = comp.district || "";
          profileForm.value.home_area = district ? `${city}·${district}` : String(result.regeocode.formattedAddress || "");
        }
        resolve();
      });
    });
    showToast("已定位当前位置");
  } catch {
    showToast("定位失败，请允许浏览器使用位置信息");
  } finally {
    locating.value = false;
  }
}

async function saveProfile() {
  if (!profileForm.value.name.trim() || !profileForm.value.school.trim() || !profileForm.value.wechat_id.trim()) {
    showToast("姓名、院校和微信号为必填");
    return;
  }
  profileSaving.value = true;
  try {
    const updated = await authApi.updateTeacherProfile({
      name: profileForm.value.name.trim(),
      gender: profileForm.value.gender,
      wechat_id: profileForm.value.wechat_id.trim(),
      school: profileForm.value.school.trim(),
      major: profileForm.value.major.trim() || undefined,
      grade: profileForm.value.grade.trim() || undefined,
      highlights: profileForm.value.highlights.trim() || undefined,
      home_area: profileForm.value.home_area.trim() || undefined,
      ...(profileCoords.value
        ? { lng: profileCoords.value.lng, lat: profileCoords.value.lat }
        : {}),
    });
    auth.setTeacher(updated);
    profileVisible.value = false;
    showToast("资料已更新");
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "保存失败");
  } finally {
    profileSaving.value = false;
  }
}

// 简历完善度：默认简历（或最新一份）的字段填充率
const resumeCompleteness = computed(() => {
  const list = resumes.value;
  if (!list.length) return { percent: 0, missing: ["基本信息"] };
  const target =
    list.find((r) => r.is_default) ??
    [...list].sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0];
  const fields: [string, string | null | undefined][] = [
    ["名称", target.title],
    ["可授科目", target.teaching_subjects],
    ["可授年级", target.teaching_grades],
    ["家教经历", target.experience],
    ["个人优势", target.strengths],
    ["可授课时间", target.availability],
    ["期望课酬", target.expected_rate],
  ];
  const filled = fields.filter(([, v]) => (v || "").trim().length > 0).length;
  const missing = fields.filter(([, v]) => !(v || "").trim().length).map(([label]) => label);
  return { percent: Math.round((filled / fields.length) * 100), missing };
});

function openDefaultResumeEditor() {
  const target =
    resumes.value.find((r) => r.is_default) ??
    (resumes.value.length ? resumes.value[0] : null);
  if (target) {
    openEdit(target);
  } else {
    openCreate();
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
    await authApi.teacherChangePassword(pwForm.value.oldPassword, pwForm.value.newPassword);
    showToast("密码已更新");
    pwVisible.value = false;
    pwForm.value = { oldPassword: "", newPassword: "" };
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "修改失败");
  } finally {
    pwSaving.value = false;
  }
}

const emptyForm = (): TeacherResumePayload => ({
  title: "",
  teaching_subjects: "",
  teaching_grades: "",
  experience: "",
  strengths: "",
  availability: "",
  expected_rate: "",
  is_default: false,
});

const form = ref<TeacherResumePayload>(emptyForm());

// 角标常显：进页面即拉取未读通知数与评价数，而不是等点击后再加载
const reviewCount = ref(0);

async function loadBadges() {
  try {
    const [notif, reviews] = await Promise.all([
      notificationsApi.mine(),
      applicationsApi.myReviews(),
    ]);
    notifUnread.value = Number(notif?.unread_count || 0);
    reviewCount.value = reviews?.length || 0;
  } catch {
    // 角标加载失败不打扰主流程
  }
}

onMounted(async () => {
  if (auth.isLoggedIn) {
    if (!auth.teacher) {
      await auth.fetchMe();
    }
    await loadResumes();
    loadBadges();
    openRequestedEditor();
  }
});

async function loadResumes() {
  loading.value = true;
  try {
    resumes.value = await resumesApi.list();
  } catch {
    showToast("简历加载失败");
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  editingId.value = null;
  form.value = emptyForm();
  form.value.is_default = resumes.value.length === 0;
  editorVisible.value = true;
}

function openRequestedEditor() {
  if (route.query.action === "create") {
    openCreate();
    return;
  }

  const resumeId = Number(route.query.resumeId);
  if (!Number.isFinite(resumeId)) {
    return;
  }

  const target = resumes.value.find((resume) => resume.id === resumeId);
  if (target) {
    openEdit(target);
  }
}

function openEdit(resume: TeacherResume) {
  editingId.value = resume.id;
  form.value = {
    title: resume.title,
    teaching_subjects: resume.teaching_subjects,
    teaching_grades: resume.teaching_grades,
    experience: resume.experience,
    strengths: resume.strengths || "",
    availability: resume.availability || "",
    expected_rate: resume.expected_rate || "",
    is_default: resume.is_default,
  };
  editorVisible.value = true;
}

async function saveResume() {
  if (!form.value.title || !form.value.teaching_subjects || !form.value.teaching_grades || !form.value.experience) {
    showToast("请填写名称、科目、年级和经历");
    return;
  }

  saving.value = true;
  try {
    if (editingId.value) {
      await resumesApi.update(editingId.value, form.value);
      showToast("简历已更新");
    } else {
      await resumesApi.create(form.value);
      showToast("简历已创建");
    }
    editorVisible.value = false;
    await loadResumes();
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function setDefault(resume: TeacherResume) {
  try {
    await resumesApi.setDefault(resume.id);
    showToast("已设为默认简历");
    await loadResumes();
  } catch {
    showToast("设置失败");
  }
}

async function removeResume(resume: TeacherResume) {
  try {
    await showConfirmDialog({
      title: "删除简历",
      message: `确定删除「${resume.title}」吗？`,
    });
  } catch {
    return;
  }

  try {
    await resumesApi.remove(resume.id);
    showToast("已删除");
    await loadResumes();
  } catch {
    showToast("删除失败");
  }
}

function handleLogout() {
  const inviteCode = getLastInviteCode();
  auth.logout();
  router.replace({
    path: "/teacher/login",
    query: { inviteCode },
  });
}
</script>

<template>
  <div class="min-h-screen bg-slate-50 pb-24 mx-auto max-w-2xl">
    <van-nav-bar title="个人中心" left-arrow @click-left="router.back()" />

    <section class="mx-4 mt-3 rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm lg:mx-auto lg:max-w-2xl">
      <div class="flex items-center gap-3">
        <div class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-slate-100">
          <van-icon name="manager-o" size="28" color="#1a365d" />
        </div>
        <div class="min-w-0 flex-1 text-slate-900">
          <div class="text-lg font-bold">{{ auth.teacher?.name || (auth.isLoggedIn ? "已登录" : "未登录") }}</div>
          <div class="truncate text-sm text-slate-500">
            {{ auth.teacher?.school }} · {{ auth.teacher?.grade }}
          </div>
          <div v-if="auth.teacher?.home_area" class="mt-0.5 truncate text-xs text-slate-400">
            常驻地：{{ auth.teacher.home_area }}
          </div>
        </div>
        <button
          class="shrink-0 rounded-lg bg-slate-100 px-3 py-1.5 text-xs text-slate-700"
          @click="openProfileEditor"
        >
          编辑资料
        </button>
      </div>
      <div
        v-if="auth.teacher?.is_985 || auth.teacher?.is_211 || auth.teacher?.is_double_first_class || auth.teacher?.is_985_211"
        class="mt-3 flex flex-wrap gap-2"
      >
        <span v-if="auth.teacher?.is_985" class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">985</span>
        <span v-if="auth.teacher?.is_211" class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">211</span>
        <span v-if="auth.teacher?.is_double_first_class" class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700">双一流</span>
        <span
          v-if="auth.teacher?.is_985_211 && !auth.teacher?.is_985 && !auth.teacher?.is_211"
          class="rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-700"
        >
          985/211
        </span>
      </div>
    </section>

      <div class="p-4 space-y-4">
        <!-- 简历完善度引导 -->
        <div
          v-if="resumes.length > 0 && resumeCompleteness.percent < 100"
          class="mx-4 mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-700"
        >
          简历完善度 {{ resumeCompleteness.percent }}%：补充「{{ resumeCompleteness.missing.join("、") }}」可显著提高成交率。
          <a class="cursor-pointer font-semibold underline" @click="openDefaultResumeEditor">
            去完善 →
          </a>
        </div>

        <section class="rounded-xl bg-white p-4 shadow-sm">
        <div class="mb-4 flex items-center justify-between">
          <div>
            <div class="text-base font-semibold text-slate-950">我的简历库</div>
            <div class="mt-1 text-xs text-slate-500">投递订单时可选择不同版本的简历</div>
          </div>
          <button class="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white" @click="openCreate">
            新增
          </button>
        </div>

        <div v-if="loading" class="flex justify-center py-8">
          <van-loading type="spinner" color="#2563eb" />
        </div>

        <div v-else-if="resumes.length === 0" class="rounded-lg bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
          还没有简历。先创建一份，投递时家长就能看到更完整的信息。
        </div>

        <div v-else class="space-y-3">
          <article v-for="resume in resumes" :key="resume.id" class="rounded-lg border border-slate-200 p-4">
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="font-semibold text-slate-950">{{ resume.title }}</div>
                <div class="mt-1 text-sm text-slate-600">
                  {{ resume.teaching_grades }} · {{ resume.teaching_subjects }}
                </div>
              </div>
              <van-tag v-if="resume.is_default" type="primary" plain>默认</van-tag>
            </div>
            <p class="mt-3 whitespace-pre-line text-sm leading-6 text-slate-600">{{ resume.experience }}</p>
            <p v-if="resume.strengths" class="mt-2 whitespace-pre-line text-xs leading-5 text-slate-500">
              {{ resume.strengths }}
            </p>
            <div class="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-500">
              <div v-if="resume.availability">时间：{{ resume.availability }}</div>
              <div v-if="resume.expected_rate">课酬：{{ resume.expected_rate }}</div>
            </div>
            <div class="mt-4 flex gap-2">
              <button class="rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-700" @click="openEdit(resume)">
                编辑
              </button>
              <button
                v-if="!resume.is_default"
                class="rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-700"
                @click="setDefault(resume)"
              >
                设为默认
              </button>
              <button class="ml-auto rounded-lg bg-red-50 px-3 py-2 text-xs text-red-600" @click="removeResume(resume)">
                删除
              </button>
            </div>
          </article>
        </div>
      </section>

      <section class="rounded-xl bg-white shadow-sm">
        <van-cell title="我的通知" icon="bell" is-link @click="openNotifications">
          <template #value>
            <span v-if="notifUnread > 0" class="admin-notification-badge">{{ notifUnread > 99 ? "99+" : notifUnread }}</span>
          </template>
        </van-cell>
        <van-cell title="我的费用" icon="balance-pay" is-link @click="openFees" />
        <van-cell title="收到的评价" icon="star-o" is-link @click="openReviews">
          <template #value>
            <span v-if="reviewCount > 0" class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">{{ reviewCount }} 条</span>
          </template>
        </van-cell>
        <van-cell title="编辑个人资料" icon="edit" is-link @click="openProfileEditor" />
        <van-cell title="修改登录密码" icon="shield-o" is-link @click="pwVisible = true" />
        <van-cell title="帮助中心" icon="question-o" is-link @click="router.push('/teacher/help')" />
      </section>

      <section class="rounded-xl bg-white shadow-sm">
        <van-cell title="退出登录" icon="revoke" @click="handleLogout" />
      </section>
    </div>

    <van-popup v-model:show="editorVisible" round position="bottom" close-on-click-overlay>
      <div class="max-h-[82vh] overflow-y-auto p-4">
        <div class="mb-3 text-base font-semibold text-slate-950">
          {{ editingId ? "编辑简历" : "新增简历" }}
        </div>

        <van-field v-model="form.title" label="名称" placeholder="如：高中英语主简历" required />
        <van-field v-model="form.teaching_subjects" label="科目" placeholder="如：英语 / 数学" required />
        <van-field v-model="form.teaching_grades" label="年级" placeholder="如：初中 / 高中 / 高三" required />
        <van-field
          v-model="form.experience"
          label="经历"
          type="textarea"
          rows="4"
          autosize
          placeholder="写清过往家教、提分案例、授课风格"
          required
        />
        <van-field
          v-model="form.strengths"
          label="优势"
          type="textarea"
          rows="3"
          autosize
          placeholder="如：耐心、擅长语法体系梳理、可提供讲义"
        />
        <van-field v-model="form.availability" label="时间" placeholder="如：周末全天，工作日晚" />
        <van-field v-model="form.expected_rate" label="课酬" placeholder="如：100-120/小时" />

        <div class="flex items-center justify-between px-4 py-3">
          <span class="text-sm text-slate-600">设为默认简历</span>
          <van-switch v-model="form.is_default" size="22" />
        </div>

        <button
          class="mt-3 w-full rounded-xl bg-blue-600 py-3 text-sm font-semibold text-white disabled:opacity-50"
          :disabled="saving"
          @click="saveResume"
        >
          {{ saving ? "保存中..." : "保存简历" }}
        </button>
      </div>
    </van-popup>
    <van-popup v-model:show="notifVisible" round position="bottom" :style="{ maxHeight: '75vh' }" close-on-click-overlay>
      <div class="flex max-h-[75vh] flex-col p-4">
        <div class="mb-3 flex items-center justify-between">
          <div class="text-base font-semibold text-slate-950">我的通知</div>
          <button
            v-if="notifUnread > 0"
            class="text-sm text-blue-600"
            @click="markAllRead"
          >
            全部已读
          </button>
        </div>
        <div class="overflow-y-auto">
          <div v-if="notifLoading" class="flex justify-center py-8">
            <van-loading type="spinner" color="#2563eb" />
          </div>
          <div v-else-if="notifications.length === 0" class="py-8 text-center text-sm text-slate-400">
            暂无通知。投递进展（候选、定金、试课、成交、退款）都会在这里提醒你。
          </div>
          <div v-else class="space-y-3">
            <article
              v-for="item in notifications"
              :key="item.id"
              class="rounded-lg border p-3"
              :class="item.is_read ? 'border-slate-100 bg-white' : 'border-blue-100 bg-blue-50/40'"
            >
              <div class="flex items-start justify-between gap-2">
                <div class="text-sm font-semibold text-slate-900">
                  {{ item.is_read ? "" : "● " }}{{ item.title }}
                </div>
                <div class="shrink-0 text-xs text-slate-400">
                  {{ new Date(item.created_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) }}
                </div>
              </div>
              <p v-if="item.content" class="mt-1 text-sm leading-5 text-slate-600">{{ item.content }}</p>
              <button
                v-if="item.order_id"
                class="mt-2 text-xs font-medium text-blue-600"
                @click="notifVisible = false; router.push(`/teacher/orders/${item.order_id}`)"
              >
                去查看 →
              </button>
            </article>
          </div>
        </div>
      </div>
    </van-popup>
    <van-popup v-model:show="feesVisible" round position="bottom" :style="{ maxHeight: '75vh' }" close-on-click-overlay>
      <div class="flex max-h-[75vh] flex-col p-4">
        <div class="mb-3 flex items-center justify-between">
          <div class="text-base font-semibold text-slate-950">我的费用</div>
          <button
            v-if="fees && fees.records.length > 0"
            class="text-sm text-blue-600 disabled:opacity-50"
            :disabled="feesExporting"
            @click="exportFees"
          >
            {{ feesExporting ? "导出中..." : "导出 CSV" }}
          </button>
        </div>
        <div class="overflow-y-auto">
          <div v-if="feesLoading" class="flex justify-center py-8">
            <van-loading type="spinner" color="#2563eb" />
          </div>
          <template v-else-if="fees">
            <div class="mb-4 grid grid-cols-3 gap-2 text-center">
              <div class="rounded-xl bg-slate-50 p-3">
                <div class="text-lg font-bold text-slate-900">¥{{ fees.total_paid.toFixed(2) }}</div>
                <div class="mt-0.5 text-xs text-slate-400">累计支付</div>
              </div>
              <div class="rounded-xl bg-slate-50 p-3">
                <div class="text-lg font-bold text-emerald-600">¥{{ fees.total_refunded.toFixed(2) }}</div>
                <div class="mt-0.5 text-xs text-slate-400">累计已退</div>
              </div>
              <div class="rounded-xl bg-slate-50 p-3">
                <div class="text-lg font-bold text-red-500">¥{{ fees.total_forfeit.toFixed(2) }}</div>
                <div class="mt-0.5 text-xs text-slate-400">违约没收</div>
              </div>
            </div>
            <div v-if="fees.records.length === 0" class="py-8 text-center text-sm text-slate-400">
              暂无费用记录。投递成交后，定金与尾款流水会在这里登记。
            </div>
            <div v-else class="space-y-2 pb-4">
              <div
                v-for="record in fees.records"
                :key="record.id"
                class="flex items-center justify-between rounded-lg border border-slate-100 p-3"
              >
                <div class="min-w-0">
                  <div class="text-sm font-medium text-slate-800">
                    {{ feeTypeLabels[record.type]?.label || record.type }}
                    <span class="ml-1 text-xs text-slate-400">
                      订单 {{ record.raw_order_id || `#${record.order_id}` }}
                    </span>
                  </div>
                  <div class="mt-0.5 text-xs text-slate-400">
                    {{ new Date(record.created_at).toLocaleString("zh-CN") }}
                    <span v-if="record.remark"> · {{ record.remark }}</span>
                  </div>
                </div>
                <div
                  class="shrink-0 text-sm font-bold"
                  :class="feeTypeLabels[record.type]?.cls || 'text-slate-700'"
                >
                  {{ feeTypeLabels[record.type]?.sign || "" }}¥{{ Number(record.amount).toFixed(2) }}
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </van-popup>

    <van-popup v-model:show="reviewsVisible" round position="bottom" :style="{ maxHeight: '75vh' }" close-on-click-overlay>
      <div class="flex max-h-[75vh] flex-col p-4">
        <div class="mb-3 flex items-center justify-between">
          <div class="text-base font-semibold text-slate-950">收到的评价</div>
          <span v-if="reviewsAvg != null" class="text-sm text-amber-600">
            均分 {{ reviewsAvg }} ★
          </span>
        </div>
        <div class="overflow-y-auto">
          <div v-if="reviewsLoading" class="flex justify-center py-8">
            <van-loading type="spinner" color="#2563eb" />
          </div>
          <div v-else-if="reviews.length === 0" class="py-8 text-center text-sm text-slate-400">
            暂无评价。完成订单后，中介的评价会在这里展示。
          </div>
          <div v-else class="space-y-3 pb-4">
            <article
              v-for="item in reviews"
              :key="item.id"
              class="rounded-lg border border-slate-100 p-3"
            >
              <div class="flex items-center justify-between">
                <van-rate :model-value="item.rating" readonly :size="14" color="#f59e0b" />
                <span class="text-xs text-slate-400">订单 #{{ item.order_id }}</span>
              </div>
              <p v-if="item.comment" class="mt-2 text-sm leading-5 text-slate-600">{{ item.comment }}</p>
              <div class="mt-1 text-xs text-slate-400">
                {{ new Date(item.created_at).toLocaleString("zh-CN") }}
              </div>
            </article>
          </div>
        </div>
      </div>
    </van-popup>

    <van-popup v-model:show="profileVisible" round position="bottom" close-on-click-overlay>
      <div class="max-h-[82vh] overflow-y-auto p-4">
        <div class="mb-1 text-base font-semibold text-slate-950">编辑个人资料</div>
        <div class="mb-3 text-xs leading-5 text-slate-400">
          填写常驻地后，推荐排序会优先考虑订单与你的距离。
        </div>

        <van-field v-model="profileForm.name" label="姓名" placeholder="真实姓名" required maxlength="20" />
        <van-field label="性别">
          <template #input>
            <van-radio-group v-model="profileForm.gender" direction="horizontal">
              <van-radio name="male">男</van-radio>
              <van-radio name="female">女</van-radio>
            </van-radio-group>
          </template>
        </van-field>
        <van-field v-model="profileForm.wechat_id" label="微信号" placeholder="家长/中介联系用" required maxlength="50" />
        <van-field v-model="profileForm.school" label="院校" placeholder="就读/毕业院校" required maxlength="50" />
        <van-field v-model="profileForm.major" label="专业" placeholder="选填" maxlength="50" />
        <van-field v-model="profileForm.grade" label="年级" placeholder="如：研二 / 大四" maxlength="20" />
        <van-field
          v-model="profileForm.highlights"
          label="个人亮点"
          type="textarea"
          rows="2"
          autosize
          maxlength="200"
          placeholder="如：耐心细致，擅长口语启蒙"
        />
        <van-field
          v-model="profileForm.home_area"
          label="常驻地"
          placeholder="如：成都·武侯区"
          maxlength="100"
        >
          <template #button>
            <button
              class="flex shrink-0 items-center gap-0.5 text-xs font-medium text-blue-600 disabled:opacity-50"
              :disabled="locating"
              @click="locateHomeArea"
            >
              <van-icon name="location-o" />
              {{ locating ? "定位中..." : "定位" }}
            </button>
          </template>
        </van-field>
        <div v-if="profileCoords" class="px-4 pb-1 text-xs text-emerald-600">
          ✓ 已使用定位坐标，推荐将按此计算距离
        </div>

        <button
          class="mt-3 w-full rounded-xl bg-blue-600 py-3 text-sm font-semibold text-white disabled:opacity-50"
          :disabled="profileSaving"
          @click="saveProfile"
        >
          {{ profileSaving ? "保存中..." : "保存资料" }}
        </button>
      </div>
    </van-popup>

    <van-popup v-model:show="pwVisible" round position="bottom" close-on-click-overlay>
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
          class="mt-3 w-full rounded-xl bg-blue-600 py-3 text-sm font-semibold text-white disabled:opacity-50"
          :disabled="pwSaving"
          @click="submitPassword"
        >
          {{ pwSaving ? "提交中..." : "确认修改" }}
        </button>
      </div>
    </van-popup>
    <TeacherTabbar />
  </div>
</template>
