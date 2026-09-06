<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { resumesApi, type TeacherResume, type TeacherResumePayload } from "@/api/resumes";
import { authApi } from "@/api/auth";
import { notificationsApi, type NotificationItem } from "@/api/notifications";
import TeacherTabbar from "@/components/TeacherTabbar.vue";
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

const pwVisible = ref(false);
const pwSaving = ref(false);
const pwForm = ref({ oldPassword: "", newPassword: "" });

async function submitPassword() {
  if (pwForm.value.oldPassword.length < 6 || pwForm.value.newPassword.length < 6) {
    showToast("密码至少 6 位");
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

onMounted(async () => {
  if (auth.isLoggedIn) {
    if (!auth.teacher) {
      await auth.fetchMe();
    }
    await loadResumes();
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

function getLastInviteCode() {
  try {
    const savedAgents = JSON.parse(localStorage.getItem("teacher_agent_invite_codes") || "[]");
    if (Array.isArray(savedAgents) && savedAgents[0]) {
      return String(savedAgents[0]);
    }
  } catch {
  }
  return "tx886";
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
  <div class="min-h-screen bg-slate-50 pb-24">
    <van-nav-bar title="个人中心" left-arrow @click-left="router.back()" />

    <section class="mx-4 mt-3 rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm lg:mx-auto lg:max-w-2xl">
      <div class="flex items-center gap-3">
        <div class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-slate-100 text-2xl">
          🎓
        </div>
        <div class="min-w-0 text-slate-900">
          <div class="text-lg font-bold">{{ auth.teacher?.name || (auth.isLoggedIn ? "已登录" : "未登录") }}</div>
          <div class="truncate text-sm text-slate-500">
            {{ auth.teacher?.school }} · {{ auth.teacher?.grade }}
          </div>
        </div>
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
            <van-badge v-if="notifUnread > 0" :content="notifUnread > 99 ? '99+' : notifUnread" />
          </template>
        </van-cell>
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
            </article>
          </div>
        </div>
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
          placeholder="至少 6 位"
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
