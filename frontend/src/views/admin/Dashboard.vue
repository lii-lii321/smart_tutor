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

const savedMinutes = computed(() => (roi.value?.orders_imported ?? 0) * 3);

function formatSaved(minutes: number): string {
  if (minutes <= 0) return "0 分钟";
  if (minutes < 60) return `${minutes} 分钟`;
  const hours = minutes / 60;
  return `${Number.isInteger(hours) ? hours : hours.toFixed(1)} 小时`;
}

const pendingApplications = computed(() => Number(appSummary.value?.total_applications || 0));

/**
 * 待审投递的等待时长。数据源是后端 summary.last_application_at
 * （每单最新一条 pending 投递时间），不是前端估算。
 * 这批投递卡在 pending 状态，中介不处理就一直是这个数。
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

/** 超过 24 小时未处理的订单数——用和产品现有"一周没反应就凸显"同一量级的临期口径 */
const staleOrderCount = computed(() => {
  const map = appSummary.value?.last_application_at;
  if (!map) return 0;
  const cutoff = Date.now() - 24 * 3_600_000;
  return Object.values(map).filter((v) => !!v && new Date(v as string).getTime() < cutoff).length;
});

/** 投递 → 成交的转化。后端没有中间态（候选/定金/试课）分组，
 *  所以只做这两段真实数据，不硬凑五段漏斗。 */
const conversionPct = computed(() => {
  const received = roi.value?.applications_received ?? 0;
  if (received <= 0) return 0;
  return Math.min(100, Math.round(((roi.value?.deals_completed ?? 0) / received) * 100));
});

/** 本月资金流向：定金 + 尾款 − 退款 − 没收 = 净额，四项都是后端口径 */
const moneyRows = computed(() => {
  if (!roi.value) return [];
  return [
    { label: "定金入账", value: roi.value.deposit_in, sign: "+" },
    { label: "尾款入账", value: roi.value.balance_in, sign: "+" },
    { label: "退款", value: roi.value.refund_out, sign: "−" },
    { label: "没收", value: roi.value.forfeit, sign: "−" },
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
  if (n > 0) return `有 ${n} 份投递等你处理${staleOrderCount.value > 0 ? `，其中 ${staleOrderCount.value} 单已超过 24 小时未响应` : ""}`;
  if (stats.value.trial > 0) return `有 ${stats.value.trial} 单在试课中，需要跟进反馈`;
  return "今天暂时没有待处理的投递";
});

// 通知角标/轮询/铃铛已上移到 AdminShell（属全局 chrome，不该只有首页有入口）

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

const queue = computed(() => [
  {
    key: "applications",
    label: "待审核投递",
    count: pendingApplications.value,
    to: "/admin/applications",
    hint:
      oldestWaitHours.value == null
        ? "教员在等审核结果，拖延易流失"
        : `最久一份已等 ${oldestWaitHours.value} 小时`,
    urgent: pendingApplications.value > 0,
    action: "去审核",
  },
  {
    key: "recruiting",
    label: "招聘中的订单",
    count: stats.value.recruiting,
    to: "/admin/orders?status=recruiting",
    hint: "为这些订单挑选并邀约合适教员",
    urgent: false,
    action: "去配教员",
  },
  {
    key: "trial",
    label: "试课中的订单",
    count: stats.value.trial,
    to: "/admin/orders?status=trial_in_progress",
    hint: "跟进试课反馈，推进定金与成交",
    urgent: false,
    action: "去跟进",
  },
]);
</script>

<template>
  <AdminShell fluid>
    <!-- 页头：问候 + 今天要处理什么 -->
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div class="min-w-0">
        <h1 class="text-xl font-bold leading-tight text-primary lg:text-2xl">{{ greeting }}</h1>
        <p class="mt-1 text-[13px] text-muted">{{ subGreeting }}</p>
      </div>
      <div class="flex shrink-0 gap-2">
        <button
          class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-default px-3 text-[13px] text-secondary transition-colors hover:bg-surface-soft"
          @click="router.push('/admin/financial-records')"
        >
          <van-icon name="balance-list-o" size="15" />
          资金流水
        </button>
        <button
          class="inline-flex h-9 items-center gap-1.5 rounded-lg border border-default px-3 text-[13px] text-secondary transition-colors hover:bg-surface-soft"
          @click="loadData"
        >
          <van-icon name="replay" size="15" />
          刷新
        </button>
      </div>
    </div>

    <!-- 行动队列：一屏最上面直接回答"现在该做什么" -->
    <div class="mt-4 grid gap-3 sm:grid-cols-3">
      <button
        v-for="item in queue"
        :key="item.key"
        class="st-card--interactive rounded-2xl border bg-surface p-4 text-left shadow-card transition-colors hover:border-strong"
        :class="item.urgent ? 'border-danger-mid' : 'border-default'"
        @click="router.push(item.to)"
      >
        <div class="flex items-baseline justify-between gap-2">
          <span class="text-[12.5px] text-secondary">{{ item.label }}</span>
          <span
            class="price-highlight text-3xl font-bold leading-none tracking-tight"
            :class="item.count > 0 ? (item.urgent ? 'text-danger-deep' : 'text-primary') : 'text-muted'"
          >{{ item.count }}</span>
        </div>
        <p class="mt-2 truncate text-[11px]" :class="item.urgent ? 'text-danger-deep' : 'text-muted'">
          {{ item.hint }}
        </p>
        <span class="mt-2 inline-flex items-center gap-0.5 text-[12px] font-medium text-brand-700">
          {{ item.action }}
          <van-icon name="arrow" size="11" />
        </span>
      </button>
    </div>

    <!-- AI 批量录单：产品最高频的动作，给一整条横幅而不是图标格 -->
    <div
      class="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-brand-900 px-5 py-4 text-white"
    >
      <div class="min-w-0">
        <p class="text-[15px] font-semibold">把微信群里的需求粘进来，直接变成可上架订单</p>
        <p class="mt-1 text-xs text-white/60">
          AI 自动解析科目、薪资、地址、频次 → 你逐单确认 → 一键上架
          <span v-if="savedMinutes > 0" class="ml-1 text-white/45">
            · 本月已省约 {{ formatSaved(savedMinutes) }} 手工录入
          </span>
        </p>
      </div>
      <button
        class="shrink-0 rounded-xl bg-white px-5 py-2.5 text-[13px] font-bold text-brand-900"
        @click="router.push('/admin/batch-import')"
      >
        开始批量录单
      </button>
    </div>

    <!-- 经营面板 + 待处理订单：桌面两栏并排，移动端上下堆叠 -->
    <div class="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:items-start">
      <section v-if="roi" class="rounded-2xl border border-default bg-surface shadow-card">
        <header class="flex items-center justify-between px-4 pt-4">
          <h2 class="text-[15px] font-bold text-primary">本月经营</h2>
          <span class="text-[11px] text-muted">{{ roi.month }}</span>
        </header>

        <div class="mt-3 grid grid-cols-2 gap-3 px-4">
          <div>
            <div class="price-highlight text-2xl font-bold text-primary">{{ roi.orders_imported }}</div>
            <div class="text-[11px] text-muted">录单（条）</div>
          </div>
          <div>
            <div class="price-highlight text-2xl font-bold text-primary">{{ roi.deals_completed }}</div>
            <div class="text-[11px] text-muted">成交（单）</div>
          </div>
          <div>
            <div class="price-highlight text-2xl font-bold text-success-deep">
              {{ formatMoney(roi.net_amount) }}
            </div>
            <div class="text-[11px] text-muted">净入账</div>
          </div>
          <div>
            <div class="price-highlight text-2xl font-bold text-primary">{{ roi.teacher_pool }}</div>
            <div class="text-[11px] text-muted">我的教员库</div>
          </div>
        </div>

        <!-- 投递 → 成交：只做有数据的两段 -->
        <div class="mt-4 px-4">
          <div class="flex items-baseline justify-between">
            <span class="text-[11px] text-muted">投递成交率</span>
            <span class="text-[11px] text-secondary">
              收到投递 {{ roi.applications_received }} · 成交 {{ roi.deals_completed }}
            </span>
          </div>
          <div class="mt-1.5 h-2 overflow-hidden rounded-full bg-surface-soft">
            <div
              class="h-full rounded-full bg-brand-700 transition-[width] duration-500"
              :style="{ width: `${conversionPct}%` }"
            />
          </div>
          <div class="mt-1 text-[11px] text-muted">
            {{ roi.applications_received > 0 ? `成交率 ${conversionPct}%` : "本月还没有收到投递" }}
          </div>
        </div>

        <!-- 资金流向：中介老板真正关心的四项 -->
        <div class="mt-4 border-t border-default px-4 py-3">
          <div class="mb-2 text-[11px] text-muted">本月资金流向</div>
          <div v-for="row in moneyRows" :key="row.label" class="flex justify-between py-0.5 text-[12px]">
            <span class="text-secondary">{{ row.label }}</span>
            <span class="tabular-nums" :class="row.sign === '+' ? 'text-primary' : 'text-muted'">
              {{ row.sign }}{{ formatMoney(row.value) }}
            </span>
          </div>
          <div class="mt-1.5 flex justify-between border-t border-default pt-2 text-[13px] font-bold">
            <span class="text-primary">净额</span>
            <span class="price-highlight tabular-nums text-success-deep">{{ formatMoney(roi.net_amount) }}</span>
          </div>
        </div>
      </section>

      <section class="rounded-2xl border border-default bg-surface shadow-card">
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

        <div v-else class="mt-2 overflow-x-auto">
          <table class="w-full min-w-[520px] text-left">
            <thead>
              <tr class="border-b border-default text-[11px] text-muted">
                <th class="px-4 py-2 font-medium">订单</th>
                <th class="px-2 py-2 font-medium">状态</th>
                <th class="px-2 py-2 font-medium">地址</th>
                <th class="px-2 py-2 text-right font-medium">信息费</th>
                <th class="px-4 py-2" />
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="order in recentOrders"
                :key="order.id"
                class="border-b border-default transition-colors last:border-0 hover:bg-surface-soft"
              >
                <td class="max-w-[220px] px-4 py-2.5">
                  <button
                    class="block w-full truncate text-left text-[13px] font-medium text-primary"
                    @click="router.push(`/admin/orders/${order.id}`)"
                  >
                    {{ order.grade_subject }}
                  </button>
                  <span class="mono text-[10.5px] text-muted">#{{ order.raw_id }}</span>
                </td>
                <td class="px-2 py-2.5">
                  <AppStatusBadge :status="order.status" />
                </td>
                <td class="max-w-[180px] truncate px-2 py-2.5 text-[12px] text-secondary">
                  {{ order.fuzzy_address }}
                </td>
                <td class="price-highlight px-2 py-2.5 text-right text-[13px] font-bold text-brand-800">
                  ¥{{ order.calculated_info_fee }}
                </td>
                <td class="px-4 py-2.5 text-right">
                  <span class="inline-flex items-center gap-0.5 text-[12px] font-medium text-brand-700">
                    打开
                    <van-icon name="arrow" size="11" />
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
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
