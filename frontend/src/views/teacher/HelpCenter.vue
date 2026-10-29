<script setup lang="ts">
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { showToast } from "vant";
import { copyToClipboard } from "@/utils/clipboard";
import { useAuthStore } from "@/stores/auth";
import { useOrderStore } from "@/stores/order";
import { aiApi, type TeacherAssistantAnswer } from "@/api/ai";
import { getApiErrorMessage } from "@/utils/apiError";
import TeacherTabbar from "@/components/TeacherTabbar.vue";
import AppButton from "@/components/ui/AppButton.vue";
import { getLastInviteCode } from "@/utils/inviteCode";

const router = useRouter();
const auth = useAuthStore();
const orderStore = useOrderStore();
const activeFaqs = ref<number[]>([]);

// 教员可联系的中介微信：优先当前浏览的橱窗中介，其次登录时的中介
const agentWechat = computed(
  () => orderStore.boardContactWechat || auth.tenant?.contact_wechat || "",
);

async function copyAgentWechat() {
  showToast((await copyToClipboard(agentWechat.value)) ? "微信号已复制" : "复制失败，请手动复制");
}

function goBoard() {
  router.push(`/teacher/board/${getLastInviteCode()}`);
}

// ── AI 助手：按当前橱窗中介的知识库回答规则/流程问题 ──
// 当前中介 = 最近浏览的橱窗邀请码，其次登录时绑定的中介
const inviteCode = getLastInviteCode() || auth.tenant?.invite_code || "";
const aiQuestion = ref("");
const aiAnswer = ref<TeacherAssistantAnswer | null>(null);
const aiLoading = ref(false);
const aiError = ref("");

const SAMPLE_QUESTIONS = [
  "信息费和定金是怎么算的？",
  "试课失败怎么退费？",
  "什么时候能解锁家长联系方式？",
  "简历通过后多久安排试课？",
];

async function askAi(question?: string) {
  const q = (question ?? aiQuestion.value).trim();
  if (!q || aiLoading.value) return;
  if (!inviteCode) {
    showToast("请先从中介的橱窗链接进入后再提问");
    return;
  }
  aiLoading.value = true;
  aiError.value = "";
  aiAnswer.value = null;
  try {
    aiAnswer.value = await aiApi.teacherAssistant(q, inviteCode);
  } catch (e) {
    aiError.value = getApiErrorMessage(e, "AI 问答暂时不可用，请稍后再试");
  } finally {
    aiLoading.value = false;
  }
}

const faqs = [
  {
    question: "接单的完整流程是什么？",
    answer:
      "确认订单适合后先投递简历，并支付 100 元定金；简历通过后补齐信息费尾款，再与对接中介微信沟通试课时间。建议投递前先确认时间、地点、科目和课酬，避免通过简历后无法到岗。",
    actionLabel: "查看我的投递",
    action: () => router.push("/teacher/applications"),
  },
  {
    question: "定金为什么是 100 元？",
    answer:
      "100 元定金用于确认老师的投递意愿，避免中介与家长确认安排后老师单方面不去。定金是信息费的一部分，不会额外多收；简历未通过会全额退回。若在投递中或简历通过后因老师个人原因放弃，定金不予退还。",
  },
  {
    question: "信息费怎么计算？",
    answer:
      "信息费 = 周课时费 × 频次倍率，周课时费 = 单次课酬 × 每周次数。频次倍率：每周 1 次为 1.5 倍、2 次为 1.0 倍、3 次及以上为 0.8 倍；线上单一律按周课时费的 1.5 倍收取。举例：每周 1 次、每次 2 小时、80 元/小时的单子，周课时费 160 元，信息费 160 × 1.5 = 240 元，已付的 100 元定金会计入这笔费用。定金固定 100 元，不随课酬浮动。",
  },
  {
    question: "什么时候能知道简历结果？",
    answer:
      "中介查看并回复简历后就会有结果，具体速度会因安排不同而变化。若长时间没有进展，你可以在「我的投递」中取消投递：已付定金会登记退款并由中介原路退回。如遇中介未及时处理，可直接联系中介微信跟进。",
    actionLabel: "查看投递进度",
    action: () => router.push("/teacher/applications"),
  },
  {
    question: "简历未通过、试课失败，费用怎么处理？",
    answer:
      "简历未通过时，100 元定金全额退回。试课未能达成后续合作时，会按照平台规则退还相应的信息费（退费 = 信息费 − 收到的试课费用 × 50%，试课没有费用则信息费全退）；信息费只收取一次，已支付的定金会直接抵扣信息费，不会重复收费。",
    actionLabel: "查看投递记录",
    action: () => router.push("/teacher/applications"),
  },
  {
    question: "订单显示“自带价”怎么办？",
    answer:
      "“自带价”订单暂未标注固定课酬，投递时请填写自己的期望课酬，后续会据此进行审核和沟通。提交前请结合授课时间、地点和自身经验谨慎报价。",
    actionLabel: "去找订单",
    action: goBoard,
  },
];
</script>

<template>
  <div class="min-h-screen bg-page pb-24 mx-auto max-w-2xl">
    <van-nav-bar title="帮助中心" left-arrow @click-left="router.back()" />

    <!-- AI 助手：按当前中介的知识库回答规则/流程问题，FAQ 作为静态兜底 -->
    <section class="mx-4 mt-3 rounded-xl border border-ai bg-ai-soft/40 px-4 py-4 shadow-sm lg:mx-auto lg:max-w-2xl">
      <div class="flex items-center gap-2">
        <span class="inline-flex items-center gap-1 rounded-full bg-ai-soft px-2 py-0.5 text-caption font-semibold text-ai-deep">
          <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-ai" />
          智派 AI 助手
        </span>
        <span class="text-xs text-muted">回答基于当前中介的知识库，附来源</span>
      </div>

      <div class="mt-3 flex items-center gap-2">
        <input
          v-model="aiQuestion"
          type="text"
          maxlength="200"
          placeholder="例如：信息费和定金是怎么算的？"
          class="min-w-0 flex-1 rounded-lg border border-default bg-white px-3 py-2 text-sm text-primary outline-none focus:border-ai focus:ring-2 focus:ring-ai-soft"
          @keyup.enter="askAi()"
        />
        <AppButton size="sm" :disabled="aiLoading || !aiQuestion.trim()" @click="askAi()">
          {{ aiLoading ? "思考中…" : "提问" }}
        </AppButton>
      </div>

      <div class="mt-2 flex flex-wrap gap-1.5">
        <button
          v-for="q in SAMPLE_QUESTIONS"
          :key="q"
          class="rounded-full bg-white px-2.5 py-1 text-caption text-secondary border border-default transition-colors active:bg-surface-soft"
          @click="askAi(q)"
        >
          {{ q }}
        </button>
      </div>

      <div v-if="aiLoading" class="mt-3 flex items-center gap-2 text-caption text-muted">
        <van-loading size="14" />
        正在检索当前中介的知识库…
      </div>

      <div v-else-if="aiError" class="mt-3 rounded-lg bg-warning-soft px-3 py-2 text-caption leading-5 text-warning-deep">
        {{ aiError }}
      </div>

      <div v-else-if="aiAnswer" class="mt-3 rounded-lg bg-white px-3 py-3">
        <div class="whitespace-pre-line text-sm leading-6 text-primary">{{ aiAnswer.answer }}</div>
        <div v-if="aiAnswer.citations.length" class="mt-3 border-t border-dashed border-default pt-2">
          <div class="text-caption font-medium text-muted">来源</div>
          <div v-for="c in aiAnswer.citations" :key="c.index" class="mt-1 text-caption leading-4 text-muted">
            [{{ c.index }}] {{ c.title }} · {{ c.snippet }}…
          </div>
        </div>
        <div class="mt-2 text-right text-caption text-muted">
          回答仅供参考，以中介确认为准
        </div>
      </div>
    </section>

    <section class="mx-4 mt-4 rounded-xl border border-default bg-white px-4 py-4 shadow-sm lg:mx-auto lg:max-w-2xl">
      <div class="text-lg font-semibold text-primary">接单常见问题</div>
      <div class="mt-1 text-sm leading-6 text-secondary">
        投递前先确认规则，费用和流程都更清楚。
      </div>

      <van-collapse v-model="activeFaqs" class="mt-4">
        <van-collapse-item v-for="(item, index) in faqs" :key="item.question" :name="index">
          <template #title>
            <div class="pr-3 text-left text-sm font-medium text-primary">
              {{ item.question }}
            </div>
          </template>
          <div class="text-sm leading-7 text-secondary">
            {{ item.answer }}
          </div>
          <button
            v-if="item.actionLabel"
            class="mt-3 text-sm font-medium text-secondary"
            @click.stop="item.action?.()"
          >
            {{ item.actionLabel }}
          </button>
        </van-collapse-item>
      </van-collapse>
    </section>

    <section
      v-if="agentWechat"
      class="mx-4 mt-4 rounded-xl border border-default bg-white px-4 py-4 shadow-sm lg:mx-auto lg:max-w-2xl"
    >
      <div class="text-sm font-medium text-primary">联系中介</div>
      <div class="mt-1 text-sm leading-6 text-secondary">
        退定金、改约试课或其他问题，可直接添加中介微信沟通。
      </div>
      <div class="mt-3 flex items-center justify-between gap-3 rounded-lg bg-surface-soft px-3 py-2">
        <div class="min-w-0">
          <div class="text-xs text-muted">中介微信</div>
          <div class="truncate font-mono text-sm text-primary">{{ agentWechat }}</div>
        </div>
        <button class="shrink-0 text-sm font-medium text-secondary" @click="copyAgentWechat">
          复制
        </button>
      </div>
    </section>

    <section class="mx-4 mt-4 rounded-xl border border-default bg-white px-4 py-4 shadow-sm lg:mx-auto lg:max-w-2xl">
      <div class="text-sm font-medium text-primary">投递前再确认一次</div>
      <div class="mt-2 text-sm leading-6 text-secondary">
        请在订单详情中确认授课需求、时间地点、课酬以及信息费金额，确认能稳定安排再投递。
      </div>
      <AppButton size="md" class="mt-4" @click="goBoard">
        去找订单
      </AppButton>
    </section>

    <TeacherTabbar />
  </div>
</template>
