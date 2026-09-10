<script setup lang="ts">
import { computed } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { copyContact } from "@/utils/clipboard";
import type { ApplicationItem } from "@/api/types";
import { tenantsApi } from "@/api/tenants";
import { APPLICATION_STATUS_LABELS } from "@/constants/applicationStatus";
import { showToast, showSuccessToast, showConfirmDialog } from "vant";

const props = defineProps<{
  application: ApplicationItem | null;
  show: boolean;
}>();

const emit = defineEmits<{
  (e: "update:show", value: boolean): void;
  /** 拉黑成功后通知父级刷新投递列表 */
  (e: "blacklisted"): void;
}>();

function close() {
  emit("update:show", false);
}

// ── 进度时间线：把投递各节点时间可视化为追踪轨迹 ──
function fmtFlowTime(value?: string | null) {
  if (!value) return "";
  return new Date(value).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function daysSince(value?: string | null) {
  if (!value) return 0;
  return Math.max(1, Math.floor((Date.now() - new Date(value).getTime()) / 86400000));
}

type TimelineNode = {
  label: string;
  time: string | null;
  done: boolean;
  state: "done" | "current" | "pending" | "skipped" | "terminal";
};

const appTimeline = computed(() => {
  const app = props.application;
  if (!app) return [];
  const terminalMap: Record<string, { label: string; time: string | null }> = {
    rejected: { label: "已拒绝", time: app.rejected_at },
    refunded: { label: "已退款", time: app.refunded_at },
    forfeited: { label: "定金已没收", time: null },
  };
  const isTerminal = !!terminalMap[app.status];
  const nodes: TimelineNode[] = [
    { label: "投递简历", time: app.applied_at as string | null, done: true, state: "done" },
    { label: "进入候选", time: app.shortlisted_at, done: !!app.shortlisted_at, state: "pending" },
    { label: "确认定金", time: app.deposit_paid_at, done: !!app.deposit_paid_at, state: "pending" },
    // 试课没有独立时间戳：进行中标记为当前阶段
    { label: "开始试课", time: null, done: ["balance_paid", "completed"].includes(app.status), state: "pending" },
    { label: "确认尾款", time: app.balance_paid_at, done: !!app.balance_paid_at, state: "pending" },
    { label: "成交完成", time: app.status === "completed" ? app.balance_paid_at : null, done: app.status === "completed", state: "pending" },
  ];
  const result: TimelineNode[] = nodes.map((node, i) => {
    let state: TimelineNode["state"] = node.done ? "done" : "pending";
    if (isTerminal && !node.done) {
      state = "skipped";
    } else if (!node.done && nodes.slice(0, i).every((p) => p.done)) {
      state = "current";
    }
    return { ...node, state };
  });
  if (terminalMap[app.status]) {
    result.push({ ...terminalMap[app.status], done: true, state: "terminal" });
  }
  return result;
});

function nodeTimeLabel(node: { label: string; time: string | null; state: string }) {
  if (node.state === "current" && node.label === "开始试课") {
    const days = daysSince(props.application?.deposit_paid_at);
    return days ? `进行中 · 第 ${days} 天` : "进行中";
  }
  return node.time ? fmtFlowTime(node.time) : node.state === "skipped" ? "—" : "";
}

async function quickBlacklist(app: ApplicationItem) {
  try {
    await showConfirmDialog({
      title: "拉黑该教员？",
      message: `拉黑「${app.teacher?.name || `#${app.teacher_id}`}」后：其待审投递将被拒绝，且无法再投递本中介订单（仅对本中介生效）。`,
    });
  } catch {
    return;
  }
  try {
    await tenantsApi.blacklist(app.teacher_id, "审核页快捷拉黑");
    showSuccessToast("已拉黑");
    close();
    emit("blacklisted");
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
}
</script>

<template>
  <van-popup :show="show" position="bottom" round @update:show="(value: boolean) => emit('update:show', value)">
    <div v-if="application" class="max-h-[78vh] overflow-y-auto p-5">
      <div class="mb-4 flex items-start justify-between gap-3">
        <div>
          <div class="text-xl font-bold break-all">
            {{ application.teacher?.name || `教员 #${application.teacher_id}` }}
          </div>
          <div class="mt-1 text-xs text-gray-400">投递详情</div>
        </div>
        <span class="shrink-0 rounded-full bg-yellow-100 px-2 py-1 text-xs text-yellow-700">
          {{ application ? APPLICATION_STATUS_LABELS[application.status] || application.status : "" }}
        </span>
      </div>

      <div class="mb-3 rounded-xl bg-blue-50 p-3 text-sm text-blue-700">
        <div class="break-all">订单编号：<span class="font-semibold">{{ application.raw_order_id || `#${application.order_id}` }}</span></div>
      </div>

      <!-- 进度时间线 -->
      <div class="mb-3 rounded-xl border border-gray-100 p-3">
        <div class="mb-2 text-sm font-semibold text-gray-700">进度时间线</div>
        <div>
          <div v-for="(node, i) in appTimeline" :key="node.label" class="flex gap-3">
            <div class="flex flex-col items-center">
              <span
                class="mt-1 h-2 w-2 shrink-0 rounded-full"
                :class="{
                  'bg-emerald-500': node.state === 'done',
                  'bg-blue-500': node.state === 'current',
                  'bg-gray-200': node.state === 'pending',
                  'bg-gray-100': node.state === 'skipped',
                  'bg-red-400': node.state === 'terminal',
                }"
              ></span>
              <span
                v-if="i < appTimeline.length - 1"
                class="my-0.5 w-px flex-1"
                :class="node.state === 'done' ? 'bg-emerald-300' : 'bg-gray-100'"
              ></span>
            </div>
            <div class="flex flex-1 items-center justify-between gap-2 pb-2.5">
              <span
                class="text-xs"
                :class="{
                  'text-gray-700': node.state === 'done',
                  'font-semibold text-blue-600': node.state === 'current',
                  'text-gray-400': node.state === 'pending',
                  'text-gray-300 line-through': node.state === 'skipped',
                  'font-semibold text-red-500': node.state === 'terminal',
                }"
              >
                {{ node.label }}
              </span>
              <span class="shrink-0 text-[11px] text-gray-400">{{ nodeTimeLabel(node) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="application.teacher" class="space-y-3 rounded-xl bg-gray-50 p-3 text-sm text-gray-600">
        <div><span class="text-gray-400">学校：</span>{{ application.teacher.school || "未填写" }}</div>
        <div><span class="text-gray-400">专业：</span>{{ application.teacher.major || "未填写" }}</div>
        <div><span class="text-gray-400">年级：</span>{{ application.teacher.grade || "未填写" }}</div>
        <div><span class="text-gray-400">性别：</span>{{ application.teacher.gender === "female" ? "女" : "男" }}</div>
        <div><span class="text-gray-400">个人优势：</span>{{ application.teacher.highlights || "未填写" }}</div>
        <div v-if="application.teacher.phone || application.teacher.wechat_id" class="space-y-1 border-t border-gray-200 pt-2">
          <div v-if="application.teacher.phone" class="flex items-center justify-between gap-2">
            <span><span class="text-gray-400">手机：</span>{{ application.teacher.phone }}</span>
            <button
              class="text-xs text-primary-600"
              @click="copyContact(application.teacher.phone, '手机号已复制')"
            >
              复制
            </button>
          </div>
          <div v-if="application.teacher.wechat_id" class="flex items-center justify-between gap-2">
            <span><span class="text-gray-400">微信：</span>{{ application.teacher.wechat_id }}</span>
            <button
              class="text-xs text-primary-600"
              @click="copyContact(application.teacher.wechat_id, '微信号已复制')"
            >
              复制
            </button>
          </div>
          <div class="text-xs text-gray-400">确认候选后可线下联系教员收取定金</div>
        </div>
      </div>

      <button
        class="mt-3 w-full rounded-lg bg-red-50 py-2 text-xs font-semibold text-red-500"
        @click="quickBlacklist(application)"
      >
        拉黑该教员（仅对本中介生效）
      </button>

      <div v-if="application.resume" class="mt-3 rounded-xl border border-gray-100 p-3">
        <div class="mb-2 flex items-center justify-between">
          <span class="text-sm font-semibold text-gray-700">投递简历</span>
          <span class="text-xs text-gray-400 break-all">{{ application.resume.title }}</span>
        </div>
        <div class="space-y-2 text-sm text-gray-600">
          <div>
            <span class="text-gray-400">可授科目：</span>{{ application.resume.teaching_subjects || "未填写" }}
          </div>
          <div>
            <span class="text-gray-400">可授年级：</span>{{ application.resume.teaching_grades || "未填写" }}
          </div>
          <div>
            <span class="text-gray-400">家教经历：</span>{{ application.resume.experience || "未填写" }}
          </div>
          <div v-if="application.resume.strengths">
            <span class="text-gray-400">个人优势：</span>{{ application.resume.strengths }}
          </div>
          <div v-if="application.resume.availability">
            <span class="text-gray-400">可授课时间：</span>{{ application.resume.availability }}
          </div>
          <div v-if="application.resume.expected_rate">
            <span class="text-gray-400">期望课酬：</span>{{ application.resume.expected_rate }}
          </div>
        </div>
      </div>
      <div v-else class="mt-3 rounded-xl bg-gray-50 p-3 text-xs text-gray-400">
        该教员投递时未选择简历（使用默认资料）
      </div>

      <div class="mt-3 space-y-1 text-sm text-gray-500">
        <div>投递时间：{{ new Date(application.applied_at).toLocaleString("zh-CN") }}</div>
        <div v-if="application.proposed_price != null">教员报价：¥{{ application.proposed_price }}/次</div>
      </div>
    </div>
  </van-popup>
</template>
