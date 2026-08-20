<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ordersApi } from "@/api/orders";
import { applicationsApi } from "@/api/applications";
import { resumesApi, type TeacherResume } from "@/api/resumes";
import { showConfirmDialog, showToast } from "vant";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const order = ref<any>(null);
const resumes = ref<TeacherResume[]>([]);
const loading = ref(true);
const applying = ref(false);
const unlocking = ref(false);
const resumePickerVisible = ref(false);
const selectedResumeId = ref<number | null>(null);
const proposedPrice = ref<number | null>(null);
const unlockedContact = ref<{ exact_address?: string | null; parent_phone?: string | null } | null>(null);

const selectedResume = computed(() =>
  resumes.value.find((resume) => resume.id === selectedResumeId.value) || null
);

const selectedResumeCheck = computed(() =>
  selectedResume.value ? checkResumeFit(selectedResume.value) : { ok: false, reasons: ["请选择投递简历"] }
);

const canApply = computed(() => order.value?.status === "recruiting");

function normalizeText(value?: string | null) {
  return (value || "").replace(/\s+/g, "").toLowerCase();
}

function extractOrderGrade() {
  const text = normalizeText(`${order.value?.grade_subject || ""}${order.value?.requirements || ""}${order.value?.raw_text || ""}`);
  const gradeTokens = ["高三", "高二", "高一", "高中", "初三", "初二", "初一", "初中", "小学"];
  return gradeTokens.find((token) => text.includes(token)) || "";
}

function extractOrderSubject() {
  const text = normalizeText(`${order.value?.grade_subject || ""}${order.value?.requirements || ""}${order.value?.raw_text || ""}`);
  const subjectTokens = ["英语", "数学", "物理", "化学", "语文", "生物", "历史", "地理", "政治"];
  return subjectTokens.find((token) => text.includes(token)) || "";
}

function isGradeCompatible(orderGrade: string, resumeText: string) {
  if (!orderGrade) return true;
  if (resumeText.includes(orderGrade)) return true;
  if (orderGrade.startsWith("高") && resumeText.includes("高中")) return true;
  if (orderGrade.startsWith("初") && resumeText.includes("初中")) return true;
  return false;
}

function checkResumeFit(resume: TeacherResume) {
  const orderGrade = extractOrderGrade();
  const orderSubject = extractOrderSubject();
  const resumeGradeText = normalizeText(`${resume.title}${resume.teaching_grades}${resume.experience}${resume.strengths}`);
  const resumeSubjectText = normalizeText(`${resume.title}${resume.teaching_subjects}${resume.experience}${resume.strengths}`);
  const reasons: string[] = [];

  if (orderSubject && !resumeSubjectText.includes(orderSubject)) {
    reasons.push(`订单要求「${orderSubject}」，这份简历未体现可授该科目。`);
  }
  if (!isGradeCompatible(orderGrade, resumeGradeText)) {
    reasons.push(`订单年级为「${orderGrade}」，这份简历未体现匹配年级。`);
  }

  return { ok: reasons.length === 0, reasons };
}

function goEditResume(resume: TeacherResume) {
  router.push(`/teacher/profile?resumeId=${resume.id}`);
}

function goCreateResume() {
  router.push("/teacher/profile?action=create");
}

onMounted(async () => {
  await loadOrder();
  if (auth.isLoggedIn) {
    await loadResumes();
  }
});

async function loadOrder() {
  loading.value = true;
  try {
    const id = Number(route.params.id);
    order.value = await ordersApi.getOrder(id);
  } catch {
    order.value = null;
  } finally {
    loading.value = false;
  }
}

async function loadResumes() {
  try {
    resumes.value = await resumesApi.list();
    selectedResumeId.value =
      resumes.value.find((resume) => resume.is_default)?.id || resumes.value[0]?.id || null;
  } catch {
    resumes.value = [];
  }
}

async function openResumePicker() {
  if (!auth.isLoggedIn) {
    router.push("/teacher/login");
    return;
  }

  if (order.value.needs_manual_price && (!proposedPrice.value || proposedPrice.value <= 0)) {
    showToast("请填写您的报价");
    return;
  }

  await loadResumes();
  if (resumes.value.length === 0) {
    try {
      await showConfirmDialog({
        title: "还没有简历",
        message: "请先到个人中心创建一份简历，再投递给家长查看。",
        confirmButtonText: "去创建",
      });
      router.push("/teacher/profile");
    } catch {
      return;
    }
    return;
  }

  resumePickerVisible.value = true;
}

async function handleApply() {
  if (!selectedResume.value) {
    showToast("请选择投递简历");
    return;
  }

  if (!selectedResumeCheck.value.ok) {
    return;
  }

  const confirmMsg = order.value.needs_manual_price
    ? `将使用「${selectedResume.value.title}」投递，报价 ¥${proposedPrice.value}/次。确定继续？`
    : `将使用「${selectedResume.value.title}」投递，需支付 ¥${order.value.deposit_amount} 定金锁定订单。确定继续？`;

  try {
    await showConfirmDialog({ title: "确认投递", message: confirmMsg });
  } catch {
    return;
  }

  applying.value = true;
  try {
    await applicationsApi.apply(order.value.id, proposedPrice.value ?? undefined, selectedResume.value.id);
    showToast("投递成功");
    resumePickerVisible.value = false;
    router.push("/teacher/applications");
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "投递失败");
  } finally {
    applying.value = false;
  }
}

async function unlockContact() {
  if (!order.value) return;
  unlocking.value = true;
  try {
    unlockedContact.value = await ordersApi.addressUnlock(order.value.id);
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "暂不能查看联系方式");
  } finally {
    unlocking.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen bg-slate-50 pb-24">
    <van-nav-bar title="订单详情" left-arrow @click-left="router.back()" />

    <div v-if="loading" class="flex justify-center py-20">
      <van-loading type="spinner" color="#2563eb" />
    </div>

    <div v-else-if="order" class="p-4 space-y-4">
      <section class="rounded-xl bg-white p-5 shadow-sm">
        <div class="flex items-start gap-3">
          <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-[#1a365d] text-lg text-white">
            📚
          </div>
          <div class="min-w-0 flex-1">
            <div class="text-lg font-bold text-slate-950">{{ order.grade_subject }}</div>
            <div class="mt-1 text-sm text-slate-500">
              {{ order.price_total }}
              <span v-if="order.needs_manual_price" class="ml-1 text-amber-600">自带价</span>
            </div>
          </div>
        </div>

        <div class="mt-5 space-y-3 text-sm">
          <div class="flex justify-between gap-4">
            <span class="text-slate-500">授课频率</span>
            <span class="font-medium text-slate-950">每周 {{ order.weekly_frequency }} 次</span>
          </div>
          <div class="flex justify-between gap-4">
            <span class="text-slate-500">地点</span>
            <span class="max-w-[68%] text-right font-medium text-slate-950">{{ order.fuzzy_address }}</span>
          </div>
          <div v-if="order.subway_remark" class="flex justify-between gap-4">
            <span class="text-slate-500">交通补充</span>
            <span class="max-w-[68%] text-right font-medium text-slate-950">{{ order.subway_remark }}</span>
          </div>
          <div class="flex justify-between gap-4">
            <span class="text-slate-500">订单编号</span>
            <span class="font-medium text-slate-950">{{ order.raw_id }}</span>
          </div>
        </div>
      </section>

      <section class="rounded-xl bg-white p-5 shadow-sm">
        <div class="mb-3 text-sm font-semibold text-slate-700">教学要求</div>
        <p class="whitespace-pre-line text-sm leading-6 text-slate-700">
          {{ order.requirements || "暂无额外要求" }}
        </p>
      </section>

      <section class="rounded-xl bg-white p-5 shadow-sm">
        <div class="mb-3 text-sm font-semibold text-slate-700">原始完整信息</div>
        <p class="whitespace-pre-line rounded-lg bg-slate-50 p-3 text-sm leading-6 text-slate-700">
          {{ order.raw_text }}
        </p>
      </section>

      <section v-if="!order.needs_manual_price" class="rounded-xl bg-white p-5 shadow-sm">
        <div class="mb-3 text-sm font-semibold text-slate-700">费用明细</div>
        <div class="space-y-2 text-sm">
          <div class="flex justify-between">
            <span>全额信息费</span>
            <span class="text-lg font-bold text-blue-600">¥{{ order.calculated_info_fee }}</span>
          </div>
          <div class="flex justify-between text-slate-500">
            <span>预付定金</span>
            <span>¥{{ order.deposit_amount }}</span>
          </div>
          <div class="flex justify-between text-slate-500">
            <span>需补尾款</span>
            <span>¥{{ order.balance_amount }}</span>
          </div>
        </div>
      </section>

      <section v-else class="rounded-xl border border-amber-200 bg-amber-50 p-5">
        <div class="mb-3 text-sm text-amber-700">该订单为自带价，请填写您的期望课酬。</div>
        <div class="flex items-center gap-3">
          <span class="text-sm text-slate-500">¥ / 次</span>
          <input
            v-model.number="proposedPrice"
            type="number"
            class="flex-1 rounded-lg border border-amber-300 bg-white px-4 py-3 text-lg font-bold focus:border-amber-500 focus:outline-none"
            placeholder="如 200"
          />
        </div>
        <div v-if="proposedPrice && proposedPrice > 0" class="mt-3 text-xs text-slate-500">
          参考信息费约 ¥{{ Math.round(proposedPrice * 1.5) }}
        </div>
      </section>

      <section
        v-if="!canApply"
        class="rounded-xl bg-white p-5 shadow-sm"
      >
        <div class="mb-3 text-sm font-semibold text-slate-700">家长联系方式</div>
        <div v-if="unlockedContact" class="space-y-3 text-sm">
          <div class="flex justify-between gap-4">
            <span class="text-slate-500">真实地址</span>
            <span class="max-w-[68%] text-right font-medium text-slate-950">
              {{ unlockedContact.exact_address || "暂未填写" }}
            </span>
          </div>
          <div class="flex justify-between gap-4">
            <span class="text-slate-500">联系电话</span>
            <span class="font-medium text-slate-950">
              {{ unlockedContact.parent_phone || "暂未填写" }}
            </span>
          </div>
        </div>
        <button
          v-else
          class="w-full rounded-xl border border-blue-200 bg-blue-50 py-3 text-sm font-semibold text-blue-700 disabled:opacity-50"
          :disabled="unlocking"
          @click="unlockContact"
        >
          {{ unlocking ? "查看中..." : "查看家长联系方式" }}
        </button>
      </section>

      <button
        v-if="canApply"
        class="w-full rounded-xl bg-blue-600 py-4 text-base font-semibold text-white shadow-lg shadow-blue-500/20 disabled:opacity-50"
        :disabled="applying"
        @click="openResumePicker"
      >
        {{ applying ? "投递中..." : "选择简历并投递" }}
      </button>
    </div>

    <div v-else class="flex flex-col items-center justify-center py-20 text-slate-400">
      <van-icon name="warning-o" size="48" />
      <p class="mt-4">订单不存在</p>
    </div>

    <van-popup v-model:show="resumePickerVisible" round position="bottom">
      <div class="max-h-[75vh] overflow-y-auto p-4">
        <div class="mb-4 flex items-center justify-between">
          <div>
            <div class="text-base font-semibold text-slate-950">选择投递简历</div>
            <div class="mt-1 text-xs text-slate-500">家长会看到这份简历的完整内容</div>
          </div>
          <button class="text-sm text-blue-600" @click="router.push('/teacher/profile')">管理简历</button>
        </div>

        <div class="space-y-3">
          <div
            v-for="resume in resumes"
            :key="resume.id"
            class="w-full rounded-xl border bg-white p-4 text-left"
            :class="[
              selectedResumeId === resume.id ? 'border-blue-600 ring-1 ring-blue-600' : 'border-slate-200',
              !checkResumeFit(resume).ok ? 'bg-red-50/50' : '',
            ]"
            @click="selectedResumeId = resume.id"
          >
            <div class="flex items-center justify-between gap-3">
              <div class="font-semibold text-slate-950">{{ resume.title }}</div>
              <div class="flex shrink-0 items-center gap-2">
                <van-tag v-if="!checkResumeFit(resume).ok" type="danger" plain>不匹配</van-tag>
                <van-tag v-if="resume.is_default" type="primary" plain>默认</van-tag>
              </div>
            </div>
            <div class="mt-2 text-sm text-slate-600">
              {{ resume.teaching_grades }} · {{ resume.teaching_subjects }}
            </div>
            <div class="mt-2 line-clamp-2 text-xs leading-5 text-slate-500">
              {{ resume.experience }}
            </div>
            <div v-if="!checkResumeFit(resume).ok" class="mt-3 rounded-lg bg-red-50 p-3 text-xs leading-5 text-red-700">
              <div v-for="reason in checkResumeFit(resume).reasons" :key="reason">{{ reason }}</div>
              <div class="mt-3 flex gap-2">
                <button class="rounded-lg bg-white px-3 py-2 font-medium text-red-700" @click.stop="goEditResume(resume)">
                  修改这份简历
                </button>
                <button class="rounded-lg bg-white px-3 py-2 font-medium text-blue-700" @click.stop="goCreateResume">
                  新增简历
                </button>
              </div>
            </div>
          </div>
        </div>

        <div
          v-if="selectedResume && !selectedResumeCheck.ok"
          class="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm leading-6 text-red-700"
        >
          <div class="font-semibold">暂不能投递这份简历</div>
          <div v-for="reason in selectedResumeCheck.reasons" :key="reason">{{ reason }}</div>
        </div>

        <button
          class="mt-4 w-full rounded-xl bg-blue-600 py-3 text-sm font-semibold text-white disabled:opacity-50"
          :disabled="applying || !selectedResume || !selectedResumeCheck.ok"
          @click="handleApply"
        >
          确认投递
        </button>
      </div>
    </van-popup>
  </div>
</template>
