<script setup lang="ts">
import { computed, ref, onMounted } from "vue";
import { formatDateTime } from "@/utils/format";
import { getApiErrorMessage } from "@/utils/apiError";
import { useRouter } from "vue-router";
import { applicationsApi } from "@/api/applications";
import type { ApplicationItem, ApplicationStatus } from "@/api/types";
import { APPLICATION_STATUS_LABELS } from "@/constants/applicationStatus";
import { applicationTone } from "@/constants/statusTone";
import { tenantsApi } from "@/api/tenants";
import { useAsyncAction } from "@/composables/useAsyncAction";
import { usePagedList } from "@/composables/usePagedList";
import { appConfirm } from "@/composables/appConfirm";
import ApplicationStepper from "@/components/business/ApplicationStepper.vue";
import TeacherTabbar from "@/components/TeacherTabbar.vue";
import { getLastInviteCode } from "@/utils/inviteCode";
import { showToast } from "vant";

const router = useRouter();
// 加载更多/去重/到底状态收敛到 usePagedList（后端按 applied_at 倒序返回）
const PAGE_SIZE = 20;
const pagedList = usePagedList<ApplicationItem>(
  (page, pageSize) =>
    applicationsApi.listMine(page, pageSize).then((list) => ({ items: list })),
  { pageSize: PAGE_SIZE }
);
const { items: applications, loading, hasMore, load, loadMore } = pagedList;
// 被中介拉黑记录（教员可见性提示）
const blacklistRecords = ref<{ tenant_name: string; reason?: string | null }[]>([]);

function goBoard() {
  router.push(`/teacher/board/${getLastInviteCode()}`);
}

onMounted(async () => {
  await Promise.all([refresh(), loadBlacklistStatus()]);
});

async function loadBlacklistStatus() {
  try {
    blacklistRecords.value = await tenantsApi.myBlacklistStatus();
  } catch {
    blacklistRecords.value = [];
  }
}

// usePagedList 把异常抛给调用方，由视图决定 toast 文案
async function refresh() {
  try {
    await load();
  } catch {
    showToast("加载失败");
  }
}

async function loadMoreSafe() {
  try {
    await loadMore();
  } catch {
    showToast("加载失败");
  }
}

const [handleCancel, cancelling] = useAsyncAction(async (app: ApplicationItem) => {
  const isDepositPaid = app.status === "deposit_paid";
  const ok = await appConfirm({
    title: isDepositPaid ? "申请退定金并取消？" : "取消投递？",
    message: isDepositPaid
      ? "取消后定金将登记为退款（线下原路退回），订单会重新开放。"
      : "取消后该订单将重新开放给其他教员。",
    confirmText: isDepositPaid ? "取消并退定金" : "确认取消",
    danger: isDepositPaid,
  });
  if (!ok) return; // 用户在底部弹层取消：不提示、不请求
  try {
    await applicationsApi.cancel(app.id);
    showToast(isDepositPaid ? "已取消并登记退定金" : "已取消投递");
    await load();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
});

// 状态文案来自 constants/applicationStatus，配色来自 constants/statusTone
// （全站唯一出口，视图层不再维护自己的状态色表）
const statusMap: Record<string, { label: string; color: string }> = Object.fromEntries(
  (Object.keys(APPLICATION_STATUS_LABELS) as ApplicationStatus[]).map((status) => [
    status,
    {
      label: APPLICATION_STATUS_LABELS[status],
      color: applicationTone(status).chip,
    },
  ]),
);

/** 聚合横幅：只描述已加载投递的真实分布，不编造"审核中" */
const ACTIVE_STATUSES: ApplicationStatus[] = ["pending", "shortlisted", "trial_in_progress", "deposit_paid", "balance_paid"];
const banner = computed(() => {
  const active = applications.value.filter((a) => ACTIVE_STATUSES.includes(a.status));
  const completed = applications.value.filter((a) => a.status === "completed");
  if (active.length > 0) {
    return { title: `你正在推进 ${active.length} 个投递`, desc: "审核结果与资金进展会通过消息通知你" };
  }
  if (completed.length > 0) {
    return { title: `已成交 ${completed.length} 单`, desc: "新的匹配机会在橱窗等你" };
  }
  if (applications.value.length > 0) {
    return { title: "暂无进行中的投递", desc: "可以到橱窗看看新的机会" };
  }
  return null;
});

/** 下一步指引：按状态给教员明确的预期；终态如实说结果 */
const NEXT_STEP_HINTS: Record<ApplicationStatus, { label: string; text: string }> = {
  pending: { label: "下一步", text: "等待中介审核，审核结果将通过消息通知" },
  shortlisted: { label: "下一步", text: "已入选候选，等待中介确认试课安排" },
  trial_in_progress: { label: "下一步", text: "试课进行中——添加中介微信对接试课安排" },
  deposit_paid: { label: "下一步", text: "定金已确认，准备开始试课" },
  balance_paid: { label: "下一步", text: "全款已确认，与中介微信对接上课事宜" },
  completed: { label: "结果", text: "本单已成交，费用明细与评价见订单详情" },
  rejected: { label: "结果", text: "未通过本次审核，可继续投递其他订单" },
  refunded: { label: "结果", text: "定金已退还，订单已重新开放" },
  forfeited: { label: "结果", text: "定金已按规则没收，明细见订单详情" },
};

function nextStep(app: ApplicationItem) {
  return NEXT_STEP_HINTS[app.status] ?? { label: "进展", text: "" };
}

function canCancel(app: ApplicationItem) {
  return ["pending", "shortlisted", "deposit_paid"].includes(app.status);
}

function canWechat(app: ApplicationItem) {
  return ["trial_in_progress", "balance_paid"].includes(app.status);
}
</script>

<template>
  <div class="min-h-screen bg-page pb-24 mx-auto max-w-2xl">
    <van-nav-bar title="我的投递" left-arrow @click-left="router.back()" />

    <van-pull-refresh v-model="loading" @refresh="refresh">
      <div
        v-if="blacklistRecords.length > 0"
        class="mx-4 mt-3 rounded-xl border border-danger-soft bg-danger-soft p-3 text-xs leading-5 text-danger-deep"
      >
        您已被以下中介限制投递：{{
          blacklistRecords.map((r) => r.tenant_name).join("、")
        }}。如有疑问请联系对应中介沟通移除。
      </div>

      <!-- 空态/加载态撑满导航栏与底部标签栏之间的可用高度；
           pt-12 补回 pb-24 预留的一半，使内容落在导航栏与标签栏的视觉正中 -->
      <div v-if="loading && applications.length === 0" class="flex min-h-[calc(100vh-142px)] flex-col items-center justify-center pt-12 text-muted">
        <van-loading type="spinner" size="32" color="#334155" />
        <p class="mt-4 text-sm">加载中...</p>
      </div>

      <div v-else-if="applications.length === 0" class="flex min-h-[calc(100vh-142px)] flex-col items-center justify-center pt-12 text-muted">
        <!-- 显式整行居中：不依赖图标字体的字形宽度，字体回退时也不会偏 -->
        <div class="flex w-full justify-center">
          <van-icon name="notes-o" size="48" />
        </div>
        <p class="mt-5">暂无投递记录</p>
        <!-- 间距挂在外层 div：Vant 的 .van-button margin:0 会覆盖 Tailwind 的 mt-* -->
        <div class="mt-10">
          <van-button type="primary" round size="small" color="#1e3558" @click="goBoard">
            去看看订单
          </van-button>
        </div>
      </div>

      <div v-else class="p-4">
        <!-- 聚合横幅：只描述已加载投递的真实分布 -->
        <div v-if="banner" class="mb-3 flex items-start gap-2.5 rounded-xl bg-info-soft p-3">
          <span class="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-surface text-info-deep">
            <van-icon name="guide-o" size="16" />
          </span>
          <div class="min-w-0 pt-0.5">
            <div class="text-sm font-semibold leading-5 text-info-deep">{{ banner.title }}</div>
            <div class="mt-0.5 text-xs leading-4 text-info-deep/80">{{ banner.desc }}</div>
          </div>
        </div>

        <div class="space-y-3">
          <article
            v-for="app in applications"
            :key="app.id"
            class="cursor-pointer rounded-2xl bg-white p-4 shadow-sm order-card"
            @click="router.push(`/teacher/orders/${app.order_id}`)"
          >
            <!-- 头部：订单标识 + 状态（statusTone 唯一出口配色） -->
            <div class="flex items-center justify-between gap-2">
              <div class="flex min-w-0 items-center gap-2">
                <span class="shrink-0 rounded bg-surface-soft px-1.5 py-0.5 text-[10px] font-medium leading-4 text-muted">订单</span>
                <span class="truncate text-sm font-bold text-primary">#{{ app.raw_order_id || app.order_id }}</span>
              </div>
              <span
                class="shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold"
                :class="statusMap[app.status]?.color || 'bg-surface-soft text-secondary'"
              >
                {{ statusMap[app.status]?.label || app.status }}
              </span>
            </div>

            <!-- 标签行：中性信息用 surface-soft，不占用语义色 -->
            <div class="mt-2.5 flex flex-wrap gap-1.5">
              <span v-if="app.order_grade_subject" class="rounded bg-surface-soft px-1.5 py-0.5 text-[11px] leading-4 text-secondary">
                {{ app.order_grade_subject }}
              </span>
              <span v-if="app.order_price_total" class="rounded bg-surface-soft px-1.5 py-0.5 text-[11px] leading-4 text-secondary">
                {{ app.order_price_total }}
              </span>
            </div>

            <!-- 2×2 字段网格 -->
            <div class="mt-3 grid grid-cols-2 gap-x-3 gap-y-2.5">
              <div class="flex min-w-0 items-start gap-1.5">
                <van-icon name="bookmark-o" size="13" class="mt-0.5 shrink-0 text-muted" />
                <div class="min-w-0">
                  <div class="text-[10px] leading-3 text-muted">学科</div>
                  <div class="mt-0.5 truncate text-xs font-medium leading-4 text-primary">{{ app.order_grade_subject || "—" }}</div>
                </div>
              </div>
              <div class="flex min-w-0 items-start gap-1.5">
                <van-icon name="gold-coin-o" size="13" class="mt-0.5 shrink-0 text-muted" />
                <div class="min-w-0">
                  <div class="text-[10px] leading-3 text-muted">课酬</div>
                  <div class="mt-0.5 truncate text-xs font-medium leading-4 text-primary">{{ app.order_price_total || "—" }}</div>
                </div>
              </div>
              <div class="flex min-w-0 items-start gap-1.5">
                <van-icon name="location-o" size="13" class="mt-0.5 shrink-0 text-muted" />
                <div class="min-w-0">
                  <div class="text-[10px] leading-3 text-muted">授课区域</div>
                  <div class="mt-0.5 truncate text-xs font-medium leading-4 text-primary">{{ app.order_fuzzy_address || "—" }}</div>
                </div>
              </div>
              <div class="flex min-w-0 items-start gap-1.5">
                <van-icon name="shop-o" size="13" class="mt-0.5 shrink-0 text-muted" />
                <div class="min-w-0">
                  <div class="text-[10px] leading-3 text-muted">发布中介</div>
                  <div class="mt-0.5 truncate text-xs font-medium leading-4 text-primary">{{ app.tenant_name || `中介 #${app.tenant_id}` }}</div>
                </div>
              </div>
            </div>

            <!-- 进度步进器：与 B 端共用 timeline.ts 唯一映射 -->
            <div class="mt-3.5">
              <ApplicationStepper :application="app" />
            </div>

            <!-- 下一步指引 -->
            <div class="mt-3 rounded-xl bg-info-soft/60 p-3">
              <div class="flex items-center justify-between gap-2">
                <span class="flex shrink-0 items-center gap-1 text-xs font-semibold text-info-deep">
                  <van-icon name="clock-o" size="12" />
                  {{ nextStep(app).label }}
                </span>
                <span class="truncate text-[10px] text-muted">投递时间 {{ formatDateTime(app.applied_at) }}</span>
              </div>
              <p class="mt-1 text-xs leading-5 text-secondary">{{ nextStep(app).text }}</p>
            </div>

            <!-- 动作行：业务动作按状态出现，微信对接是主循环不能丢 -->
            <div class="mt-3 flex items-center justify-between gap-2 border-t border-default pt-3">
              <span class="flex shrink-0 items-center gap-1 text-xs font-medium text-secondary">
                <van-icon name="notes-o" size="12" />
                查看订单详情
                <van-icon name="arrow" size="10" />
              </span>
              <button
                v-if="canWechat(app)"
                class="flex shrink-0 items-center gap-1 rounded-full border border-success-mid bg-success-soft px-3 py-1 text-xs font-medium text-success-deep"
                @click.stop="router.push(`/teacher/orders/${app.order_id}`)"
              >
                <van-icon name="wechat" size="12" />
                微信联系中介
              </button>
              <button
                v-if="canCancel(app)"
                class="flex shrink-0 items-center gap-1 rounded-full border border-danger-mid px-3 py-1 text-xs font-medium text-danger-deep disabled:opacity-50"
                :disabled="cancelling"
                @click.stop="handleCancel(app)"
              >
                <van-icon name="delete-o" size="12" />
                {{ app.status === 'deposit_paid' ? '取消并退定金' : '取消投递' }}
              </button>
            </div>
          </article>
        </div>

        <button
          v-if="hasMore && !loading"
          class="mt-3 w-full rounded-xl bg-white py-3 text-sm font-medium text-secondary shadow-sm"
          @click="loadMoreSafe"
        >
          加载更多
        </button>
        <div v-if="!hasMore && applications.length > PAGE_SIZE" class="py-2 text-center text-xs text-muted">
          — 已经到底了 —
        </div>
      </div>
    </van-pull-refresh>
    <TeacherTabbar />
  </div>
</template>
