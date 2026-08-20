<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { resumesApi, type TeacherResume, type TeacherResumePayload } from "@/api/resumes";
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
</script>

<template>
  <div class="min-h-screen bg-slate-50 pb-24">
    <van-nav-bar title="个人中心" left-arrow @click-left="router.back()" />

    <section class="bg-[#1a365d] px-6 pb-8 pt-6">
      <div class="flex items-center gap-4">
        <div class="flex h-16 w-16 items-center justify-center rounded-full bg-white/15 text-3xl text-white">
          🎓
        </div>
        <div class="text-white">
          <div class="text-lg font-bold">{{ auth.teacher?.name || (auth.isLoggedIn ? "已登录" : "未登录") }}</div>
          <div class="text-sm text-white/75">
            {{ auth.teacher?.school }} · {{ auth.teacher?.grade }}
          </div>
        </div>
      </div>
      <div
        v-if="auth.teacher?.is_985 || auth.teacher?.is_211 || auth.teacher?.is_double_first_class || auth.teacher?.is_985_211"
        class="mt-3 flex flex-wrap gap-2"
      >
        <span v-if="auth.teacher?.is_985" class="rounded-full bg-white/15 px-3 py-1 text-xs text-white">985</span>
        <span v-if="auth.teacher?.is_211" class="rounded-full bg-white/15 px-3 py-1 text-xs text-white">211</span>
        <span v-if="auth.teacher?.is_double_first_class" class="rounded-full bg-white/15 px-3 py-1 text-xs text-white">双一流</span>
        <span
          v-if="auth.teacher?.is_985_211 && !auth.teacher?.is_985 && !auth.teacher?.is_211"
          class="rounded-full bg-white/15 px-3 py-1 text-xs text-white"
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
        <van-cell title="我的投递" icon="notes-o" is-link @click="router.push('/teacher/applications')" />
        <van-cell title="帮助中心" icon="question-o" is-link />
      </section>

      <section class="rounded-xl bg-white shadow-sm">
        <van-cell title="退出登录" icon="revoke" @click="auth.logout(); router.push('/')" />
      </section>
    </div>

    <van-popup v-model:show="editorVisible" round position="bottom">
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
    <TeacherTabbar />
  </div>
</template>
