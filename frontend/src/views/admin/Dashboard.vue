<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { ordersApi } from "@/api/orders";
import type { OrderBrief, ApplicationSummaryResponse } from "@/api/types";
import { applicationsApi } from "@/api/applications";
import { tenantsApi, type TenantRoiSummary } from "@/api/tenants";
import { formatMoney } from "@/utils/format";
import AdminShell from "@/components/admin/AdminShell.vue";
import AppStatusBadge from "@/components/ui/AppStatusBadge.vue";
import { showToast } from "vant";

const router = useRouter();
const auth = useAuthStore();

// 行动队列：三条都是"现在就要动手"的事，数字全部取自真实 API total
const stats = ref({ recruiting: 0, trial: 0 });
const recentOrders = ref<OrderBrief[]>([]);
const appSummary = ref<ApplicationSummaryResponse | null>(null);
const loading = ref(true);
const loadError = ref(false);

// 「本月经营」：加载失败静默隐藏，不干扰主流程
const roi = ref<TenantRoiSummary | null>(null);

async function loadRoi() {
  try {
    roi.value = await tenantsApi.roiSummary();
  } catch {
    roi.value = null;
  }
}

const pendingApplications = computed(() => Number(appSummary.value?.total_applications || 0));

/**
 * 待审投递的等待时长。数据源是后端 summary.last_application_at
 * （每单最新一条 pending 投递时间），不是前端估算。
 */
const oldestWaitHours = computed(() => {
  const map = appSummary.value?.last_application_at;
  if (!map) return null;
  const stamps = Object.values(map)
    .filter((v): v is string => !!v)
    .map((v) => new Date(v).getTime());
  if (!stamps.length) return null;
  return Math.floor((Date.now() - Math.min(...stamps)) / 3_600_000);
});

/** 投递 → 成交的转化。后端没有中间态分组，只做这两段真实数据，不硬凑漏斗。 */
const conversionPct = computed(() => {
  const received = roi.value?.applications_received ?? 0;
  if (received <= 0) return 0;
  return Math.min(100, Math.round(((roi.value?.deals_completed ?? 0) / received) * 100));
});

/** 投递覆盖：收到投递份数摊到在招单上的比例（两个真实计数的比值） */
const coveragePct = computed(() => {
  const recruiting = stats.value.recruiting;
  const received = roi.value?.applications_received ?? 0;
  if (recruiting <= 0) return 0;
  return Math.min(100, Math.round((received / recruiting) * 100));
});

/**
 * 本月资金四行。口径与后端一致（tenants.py roi 注释 / financial_records.py:89）：
 * 净额 = 定金 + 尾款 − 退款；没收只是资金性质标注（那笔钱确认定金时已计入收入），
 * 不带正负号、不计入净额，展示为琥珀"不计净额"。
 */
const moneyRows = computed(() => {
  if (!roi.value) return [];
  return [
    { label: "定金入账", value: roi.value.deposit_in, nature: "income" as const },
    { label: "尾款入账", value: roi.value.balance_in, nature: "income" as const },
    { label: "退款", value: roi.value.refund_out, nature: "expense" as const },
    { label: "没收", value: roi.value.forfeit, nature: "note" as const },
  ];
});

function greetingByTime(): string {
  const hour = new Date().getHours();
  if (hour < 11) return "早上好";
  if (hour < 14) return "中午好";
  if (hour < 18) return "下午好";
  return "晚上好";
}
const greeting = computed(
  () => `${greetingByTime()}，${auth.tenant?.tenant_name || (auth.role === "super_admin" ? "老板" : "中介老板")}`,
);

const subGreeting = computed(() => {
  const n = pendingApplications.value;
  if (n > 0) {
    const wait = oldestWaitHours.value;
    return `${n} 份投递待审${wait != null ? `，最久已等 ${wait} 小时` : ""}`;
  }
  if (stats.value.trial > 0) return `有 ${stats.value.trial} 单在试课中，需要跟进反馈`;
  return "今天暂时没有待处理的投递";
});

onMounted(async () => {
  await loadData();
  loadRoi();
});

async function loadData() {
  loading.value = true;
  try {
    // 最近订单只取 8 条；待办数字用后端 total，避免从第一页 filter 导致的口径错误
    const [recent, recruitingRes, trialRes, appSummaryRes] = await Promise.all([
      ordersApi.listOrders(1, 8),
      ordersApi.listOrders(1, 1, "recruiting"),
      ordersApi.listOrders(1, 1, "trial_in_progress"),
      applicationsApi.summary().catch(() => null),
    ]);
    recentOrders.value = recent.items || [];
    stats.value = {
      recruiting: recruitingRes?.total ?? 0,
      trial: trialRes?.total ?? 0,
    };
    appSummary.value = appSummaryRes;
  } catch {
    showToast("数据加载失败，请点击重试");
    loadError.value = true;
  } finally {
    loading.value = false;
  }
}

/** 行动队列（严格按新版工作台的三行清单：紧急项红底置顶） */
const queue = computed(() => [
  {
    key: "applications",
    title: `待审投递 ${pendingApplications.value} 份`,
    count: pendingApplications.value,
    to: "/admin/applications",
    desc:
      oldestWaitHours.value == null
        ? "教员在等审核结果，拖延易流失"
        : `最久一份已等 ${oldestWaitHours.value} 小时 · 教员在等回音`,
    urgent: pendingApplications.value > 0,
    action: "去审核",
  },
  {
    key: "recruiting",
    title: `招聘中 ${stats.value.recruiting} 单`,
    count: stats.value.recruiting,
    to: "/admin/orders?status=recruiting",
    desc: "为这些订单挑选并邀约合适教员",
    urgent: false,
    action: "去找人",
  },
  {
    key: "trial",
    title: `试课中 ${stats.value.trial} 单`,
    count: stats.value.trial,
    to: "/admin/orders?status=trial_in_progress",
    desc: "跟进试课反馈，推进定金与成交",
    urgent: false,
    action: "去跟进",
  },
]);
</script>

<template>
  <AdminShell fluid>
    <div class="mx-auto w-full max-w-3xl px-4">
      <!-- 页头：问候 + 今日概况 -->
      <div class="flex flex-wrap items-end justify-between gap-3">
        <div class="min-w-0">
          <h1 class="text-xl font-bold leading-tight text-primary lg:text-2xl">{{ greeting }}</h1>
          <p class="mt-1 text-[13px] text-muted">{{ subGreeting }}</p>
        </div>
        <button
          class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-default px-3 text-[13px] text-secondary transition-colors hover:bg-surface-soft"
          @click="loadData"
        >
          <van-icon name="replay" size="15" />
          刷新
        </button>
      </div>

      <!-- 行动队列：紧急项红底置顶，其余白底，右缘动作直达 -->
      <section class="mt-4 overflow-hidden rounded-2xl border border-default bg-surface shadow-card">
        <button
          v-for="(item, i) in queue"
          :key="item.key"
          class="flex w-full items-center justify-between gap-3 px-4 py-3.5 text-left transition-colors hover:bg-surface-soft/60"
          :class="[item.urgent ? 'bg-danger-soft' : 'bg-surface', i > 0 ? 'border-t border-default' : '']"
          @click="router.push(item.to)"
        >
          <span class="flex min-w-0 items-center gap-2.5">
            <span
              class="h-1.5 w-1.5 shrink-0 rounded-full"
              :class="item.urgent && item.count > 0 ? 'bg-danger' : 'bg-muted'"
            />
            <span class="min-w-0">
              <span
                class="block truncate text-[14px] font-bold leading-5"
                :class="item.urgent && item.count > 0 ? 'text-danger-deep' : 'text-primary'"
              >
                {{ item.title }}
              </span>
              <span
                class="mt-0.5 block truncate text-[11.5px] leading-4"
                :class="item.urgent && item.count > 0 ? 'text-danger-deep/80' : 'text-muted'"
              >
                {{ item.desc }}
              </span>
            </span>
          </span>
          <span
            class="inline-flex shrink-0 items-center gap-0.5 text-[12.5px] font-semibold"
            :class="item.urgent && item.count > 0 ? 'text-danger-deep' : 'text-primary'"
          >
            {{ item.action }}
            <van-icon name="arrow" size="12" />
          </span>
        </button>
      </section>

      <!-- 本月经营：三数字 + 覆盖/成交率进度 + 净入账/教员库 -->
      <section v-if="roi" class="mt-3 rounded-2xl border border-default bg-surface shadow-card">
        <header class="flex items-center justify-between px-4 pt-4">
          <h2 class="text-[15px] font-bold text-primary">本月经营</h2>
          <span class="text-[11px] text-muted">{{ roi.month }}</span>
        </header>

        <div class="mt-3 grid grid-cols-3 gap-2 px-4">
          <div>
            <div class="price-highlight text-[26px] font-bold leading-8 text-primary">{{ roi.orders_imported }}</div>
            <div class="text-[11px] text-muted">录单</div>
          </div>
          <div>
            <div class="price-highlight text-[26px] font-bold leading-8 text-primary">{{ roi.applications_received }}</div>
            <div class="text-[11px] text-muted">收到投递</div>
          </div>
          <div>
            <div class="price-highlight text-[26px] font-bold leading-8 text-danger-deep">{{ roi.deals_completed }}</div>
            <div class="text-[11px] text-muted">成交</div>
          </div>
        </div>

        <div class="mt-3 px-4">
          <div class="h-1.5 overflow-hidden rounded-full bg-surface-soft">
            <div
              class="h-full rounded-full bg-brand-700 transition-[width] duration-500"
              :style="{ width: `${coveragePct}%` }"
            />
          </div>
          <div class="mt-1.5 flex items-baseline justify-between text-[11px] text-muted">
            <span>投递覆盖 {{ coveragePct }}% 的在招单</span>
            <span>成交率 {{ conversionPct }}%</span>
          </div>
        </div>

        <div class="mt-3 grid grid-cols-2 border-t border-default">
          <button class="border-r border-default px-4 py-3 text-left" @click="router.push('/admin/financial-records')">
            <div class="price-highlight text-xl font-bold leading-6 text-success-deep">
              {{ formatMoney(roi.net_amount) }}
            </div>
            <div class="mt-0.5 text-[11px] text-muted">净入账</div>
          </button>
          <button class="flex w-full items-center justify-between px-4 py-3 text-left" @click="router.push('/admin/teachers')">
            <span>
              <span class="price-highlight block text-xl font-bold leading-6 text-primary">{{ roi.teacher_pool }}</span>
              <span class="mt-0.5 block text-[11px] text-muted">我的教员库</span>
            </span>
            <van-icon name="arrow" size="14" class="text-muted" />
          </button>
        </div>
      </section>

      <!-- 本月资金：四项明细 + 净额，全部来自资金台账 -->
      <section v-if="roi" class="mt-3 rounded-2xl border border-default bg-surface shadow-card">
        <header class="flex items-center justify-between px-4 pt-4">
          <h2 class="text-[15px] font-bold text-primary">本月资金</h2>
          <span class="text-[11px] text-muted">全部来自资金台账</span>
        </header>

        <div class="mt-2 px-4 pb-1">
          <div
            v-for="row in moneyRows"
            :key="row.label"
            class="flex items-center justify-between border-b border-dashed border-default py-2.5 text-[13px]"
          >
            <span class="text-secondary">{{ row.label }}</span>
            <span v-if="row.nature === 'note'" class="text-warning-deep tabular-nums">
              ¥{{ formatMoney(row.value).slice(1) }}
              <span class="ml-1 text-[10px] text-muted">不计净额</span>
            </span>
            <span
              v-else
              class="tabular-nums"
              :class="row.value > 0 ? (row.nature === 'income' ? 'text-success-deep' : 'text-danger-deep') : 'text-muted'"
            >
              {{ row.value > 0 ? `${row.nature === 'income' ? '+' : '−'}${formatMoney(row.value)}` : formatMoney(0) }}
            </span>
          </div>
          <div class="flex items-center justify-between py-3 text-[15px] font-bold">
            <span class="text-primary">净额</span>
            <span class="price-highlight tabular-nums text-success-deep">{{ formatMoney(roi.net_amount) }}</span>
          </div>
        </div>
      </section>

      <!-- 从微信群批量录单：暖米色低压力入口（不再用大面积深蓝横幅） -->
      <section
        class="mt-3 flex items-center justify-between gap-3 rounded-2xl border border-default bg-surface-warm px-4 py-3.5"
      >
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface text-secondary">
          <van-icon name="notes-o" size="17" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block text-[14px] font-bold leading-5 text-primary">从微信群批量录单</span>
          <span class="mt-0.5 block truncate text-[11.5px] leading-4 text-muted">
            粘需求 → AI 解析 → 逐单确认 → 一键上架
          </span>
        </span>
        <button
          class="shrink-0 rounded-lg border border-default bg-surface px-4 py-2 text-[13px] font-bold text-primary shadow-sm transition-colors hover:bg-surface-soft"
          @click="router.push('/admin/batch-import')"
        >
          去录单
        </button>
      </section>

      <!-- 最近订单：行卡（整行可点），虚线分隔 -->
      <section class="mt-3 mb-2 rounded-2xl border border-default bg-surface shadow-card">
        <header class="flex items-center justify-between px-4 pt-4">
          <h2 class="text-[15px] font-bold text-primary">最近订单</h2>
          <button class="text-[12px] font-medium text-brand-700" @click="router.push('/admin/orders')">
            全部订单 →
          </button>
        </header>

        <div v-if="recentOrders.length === 0" class="px-4 py-14 text-center">
          <template v-if="loadError">
            <p class="text-sm text-muted">数据加载失败</p>
            <button class="mt-3 rounded-lg border border-default px-4 py-2 text-[13px] text-secondary" @click="loadData">
              重试
            </button>
          </template>
          <template v-else>
            <p class="text-sm text-muted">还没有订单</p>
            <button
              class="mt-3 rounded-lg bg-brand-800 px-4 py-2 text-[13px] font-medium text-white"
              @click="router.push('/admin/batch-import')"
            >
              去批量录单
            </button>
          </template>
        </div>

        <div v-else class="mt-1 px-4 pb-2">
          <button
            v-for="order in recentOrders"
            :key="order.id"
            class="flex w-full items-center justify-between gap-3 border-b border-dashed border-default py-3 text-left last:border-b-0"
            @click="router.push(`/admin/orders/${order.id}`)"
          >
            <span class="min-w-0">
              <span class="flex items-center gap-2">
                <span class="truncate text-[14px] font-semibold text-primary">{{ order.grade_subject }}</span>
                <AppStatusBadge :status="order.status" />
              </span>
              <span class="mt-0.5 block truncate text-[11px] text-muted">
                #{{ order.raw_id }} · {{ order.fuzzy_address }}
              </span>
            </span>
            <span class="shrink-0 text-right">
              <span class="price-highlight block text-[15px] font-bold leading-5 text-primary">
                ¥{{ order.calculated_info_fee }}
              </span>
              <span class="block text-[10px] leading-3 text-muted">信息费</span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <van-overlay :show="loading">
      <div class="flex h-full items-center justify-center">
        <van-loading type="spinner" size="32" />
      </div>
    </van-overlay>
  </AdminShell>
</template>
