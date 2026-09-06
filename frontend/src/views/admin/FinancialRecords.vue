<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import client from "@/api/client";
import { financialApi, type FinancialFilters, type FinancialTypeFilter } from "@/api/financial";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast } from "vant";

const router = useRouter();
const loading = ref(true);
const loadingMore = ref(false);
const exporting = ref(false);
const page = ref(1);
const pageSize = 50;
const summary = ref<any>({
  deposit_in: 0,
  balance_in: 0,
  refund_out: 0,
  forfeit: 0,
  net_amount: 0,
  records: [],
});

const typeOptions: { label: string; value: FinancialTypeFilter }[] = [
  { label: "定金收入", value: "deposit_in" },
  { label: "尾款收入", value: "balance_in" },
  { label: "退款支出", value: "refund_out" },
  { label: "定金没收", value: "forfeit" },
];
const datePresets = ["全部", "近7天", "近30天", "本月"];

const typeFilter = ref<FinancialTypeFilter | null>(null);
const datePreset = ref("全部");

function formatDay(date: Date) {
  return date.toISOString().slice(0, 10);
}

const activeFilters = computed<FinancialFilters>(() => {
  const filters: FinancialFilters = {};
  if (typeFilter.value) filters.type = typeFilter.value;
  const today = new Date();
  if (datePreset.value === "近7天") {
    filters.start_date = formatDay(new Date(today.getTime() - 6 * 86400000));
    filters.end_date = formatDay(today);
  } else if (datePreset.value === "近30天") {
    filters.start_date = formatDay(new Date(today.getTime() - 29 * 86400000));
    filters.end_date = formatDay(today);
  } else if (datePreset.value === "本月") {
    filters.start_date = formatDay(new Date(today.getFullYear(), today.getMonth(), 1));
    filters.end_date = formatDay(today);
  }
  return filters;
});

onMounted(() => loadData());

async function loadData() {
  loading.value = true;
  page.value = 1;
  try {
    summary.value = await financialApi.list(1, pageSize, activeFilters.value);
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "加载财务数据失败");
  } finally {
    loading.value = false;
  }
}

function setTypeFilter(value: FinancialTypeFilter) {
  typeFilter.value = typeFilter.value === value ? null : value;
  loadData();
}

function setDatePreset(preset: string) {
  datePreset.value = preset;
  loadData();
}

async function exportCsv() {
  exporting.value = true;
  try {
    const res = await client.get(financialApi.exportUrl(activeFilters.value), {
      responseType: "blob",
    });
    const url = URL.createObjectURL(res.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = `财务流水_${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  } catch {
    showToast("导出失败，请重试");
  } finally {
    exporting.value = false;
  }
}

const records = computed(() => summary.value.records || []);
const hasMore = computed(() => records.value.length >= page.value * pageSize);

async function loadMore() {
  if (loadingMore.value || !hasMore.value) return;
  loadingMore.value = true;
  try {
    const next = page.value + 1;
    const res = await financialApi.list(next, pageSize, activeFilters.value);
    const known = new Set(records.value.map((r: any) => r.id));
    summary.value = {
      ...res,
      records: [...records.value, ...((res.records || []).filter((r: any) => !known.has(r.id)))],
    };
    page.value = next;
  } catch {
    showToast("加载更多失败，请重试");
  } finally {
    loadingMore.value = false;
  }
}

const typeLabels: Record<string, string> = {
  deposit_in: "定金收入",
  balance_in: "尾款收入",
  refund_out: "退款支出",
  forfeit: "定金没收",
};

const typeClasses: Record<string, string> = {
  deposit_in: "finance-tag finance-tag--deposit",
  balance_in: "finance-tag finance-tag--balance",
  refund_out: "finance-tag finance-tag--refund",
  forfeit: "finance-tag finance-tag--forfeit",
};

function formatAmount(value: unknown) {
  return Number(value || 0).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatDate(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
</script>

<template>
  <div class="finance-page min-h-screen bg-slate-50 pb-20">
    <van-nav-bar title="财务流水" left-arrow @click-left="router.push('/admin/dashboard')" />

    <main class="finance-content">
      <section class="finance-overview">
        <div class="finance-overview__heading">
          <div>
            <div class="finance-eyebrow">本期财务概览</div>
            <h1>净收入</h1>
          </div>
          <button class="finance-refresh" :disabled="loading" @click="loadData">
            <van-icon name="replay" size="15" />
            刷新
          </button>
        </div>
        <div class="finance-net-amount">¥{{ formatAmount(summary.net_amount) }}</div>
        <div class="finance-overview__note">收入合计扣除退款支出</div>
      </section>

      <section class="finance-metrics" aria-label="财务指标">
        <div class="finance-metric">
          <span>定金收入</span>
          <strong class="text-blue-700">¥{{ formatAmount(summary.deposit_in) }}</strong>
        </div>
        <div class="finance-metric">
          <span>尾款收入</span>
          <strong class="text-emerald-700">¥{{ formatAmount(summary.balance_in) }}</strong>
        </div>
        <div class="finance-metric">
          <span>退款支出</span>
          <strong class="text-red-600">¥{{ formatAmount(summary.refund_out) }}</strong>
        </div>
        <div class="finance-metric">
          <span>定金没收</span>
          <strong class="text-amber-700">¥{{ formatAmount(summary.forfeit) }}</strong>
        </div>
      </section>

      <div class="finance-section-heading" style="margin-top: 16px">
        <div>
          <h2>流水明细</h2>
          <span>{{ records.length }} 笔记录</span>
        </div>
        <button
          class="rounded-lg bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-600 disabled:opacity-50"
          :disabled="exporting"
          @click="exportCsv"
        >
          {{ exporting ? "导出中..." : "导出 CSV" }}
        </button>
      </div>

      <div class="finance-filter-bar">
        <div class="finance-filter-chips">
          <button
            v-for="option in typeOptions"
            :key="option.value"
            class="finance-chip"
            :class="{ 'finance-chip--active': typeFilter === option.value }"
            @click="setTypeFilter(option.value)"
          >
            {{ option.label }}
          </button>
        </div>
        <div class="finance-filter-chips">
          <button
            v-for="preset in datePresets"
            :key="preset"
            class="finance-chip"
            :class="{ 'finance-chip--active': datePreset === preset }"
            @click="setDatePreset(preset)"
          >
            {{ preset }}
          </button>
        </div>
      </div>

      <div v-if="records.length === 0" class="finance-empty">
        <van-icon name="balance-list-o" size="42" />
        <p class="mt-3 text-sm">暂无流水</p>
      </div>

      <div v-else class="finance-ledger">
        <div
          v-for="record in records"
          :key="record.id"
          class="finance-ledger-row"
        >
          <div class="finance-ledger-main">
            <span :class="typeClasses[record.type]">
              {{ typeLabels[record.type] || record.type }}
            </span>
            <strong :class="record.type === 'refund_out' ? 'text-red-600' : 'text-slate-900'">
              {{ record.type === 'refund_out' ? '-' : '+' }}¥{{ formatAmount(record.amount) }}
            </strong>
          </div>
          <div class="finance-ledger-meta">
            <span>订单 #{{ record.order_id }}</span>
            <span>教员 #{{ record.teacher_id }}</span>
            <span>{{ record.remark || "无备注" }}</span>
          </div>
          <div class="finance-ledger-date">
            {{ formatDate(record.created_at) }}
          </div>
        </div>
      </div>

      <button
        v-if="hasMore"
        class="finance-more-btn"
        :disabled="loadingMore"
        @click="loadMore"
      >
        {{ loadingMore ? "加载中..." : "加载更多记录" }}
      </button>
    </main>

    <van-overlay :show="loading">
      <div class="flex items-center justify-center h-full">
        <van-loading type="spinner" size="32" color="#2563eb" />
      </div>
    </van-overlay>
    <AdminTabbar />
  </div>
</template>

<style scoped>
.finance-filter-bar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.finance-filter-chips {
  display: flex;
  gap: 8px;
  overflow-x: auto;
}

.finance-chip {
  padding: 4px 12px;
  border-radius: 9999px;
  font-size: 12px;
  background: #fff;
  border: 1px solid #dbe3ec;
  color: #475569;
  white-space: nowrap;
}

.finance-chip--active {
  background: #1a365d;
  border-color: #1a365d;
  color: #fff;
}

.finance-content {
  width: min(100%, 720px);
  margin: 0 auto;
  padding: 20px 16px 32px;
}

.finance-overview {
  padding: 14px 16px;
  border: 1px solid #dbe3ec;
  border-radius: 10px;
  background: #fff;
}

.finance-overview__heading,
.finance-section-heading,
.finance-ledger-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.finance-eyebrow,
.finance-overview__note,
.finance-section-heading span,
.finance-metric span,
.finance-ledger-date {
  color: #64748b;
  font-size: 12px;
}

.finance-overview h1,
.finance-section-heading h2 {
  margin: 2px 0 0;
  color: #172b4d;
  font-size: 18px;
  font-weight: 700;
}

.finance-refresh {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #2563eb;
  font-size: 13px;
}

.finance-net-amount {
  margin-top: 10px;
  color: #172b4d;
  font-size: 32px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.03em;
}

.finance-overview__note {
  margin-top: 4px;
}

.finance-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-top: 12px;
  overflow: hidden;
  border: 1px solid #dbe3ec;
  border-radius: 10px;
  background: #fff;
}

.finance-metric {
  min-width: 0;
  padding: 12px;
  border-right: 1px solid #e7edf3;
}

.finance-metric:last-child {
  border-right: 0;
}

.finance-metric strong {
  display: block;
  margin-top: 4px;
  font-size: 16px;
  font-variant-numeric: tabular-nums;
  white-space: normal;
}

.finance-section-heading {
  margin: 28px 0 10px;
}

.finance-ledger {
  overflow: hidden;
  border: 1px solid #dbe3ec;
  border-radius: 10px;
  background: #fff;
}

.finance-ledger-row {
  padding: 15px 16px;
  border-bottom: 1px solid #e7edf3;
}

.finance-ledger-row:last-child {
  border-bottom: 0;
}

.finance-ledger-main strong {
  font-size: 16px;
  font-variant-numeric: tabular-nums;
}

.finance-ledger-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 16px;
  margin-top: 10px;
  color: #334155;
  font-size: 13px;
}

.finance-ledger-date {
  margin-top: 6px;
}

.finance-tag {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.finance-tag--deposit { color: #1d4ed8; background: #eff6ff; }
.finance-tag--balance { color: #047857; background: #ecfdf5; }
.finance-tag--refund { color: #b91c1c; background: #fef2f2; }
.finance-tag--forfeit { color: #a16207; background: #fefce8; }

.finance-more-btn {
  display: block;
  width: 100%;
  margin-top: 12px;
  padding: 10px 0;
  border: 1px solid #dbe3ec;
  border-radius: 10px;
  background: #fff;
  color: #2563eb;
  font-size: 13px;
}

.finance-empty {
  padding: 64px 16px;
  border: 1px solid #dbe3ec;
  border-radius: 10px;
  background: #fff;
  color: #94a3b8;
  text-align: center;
}

@media (max-width: 520px) {
  .finance-content {
    padding: 14px 12px 28px;
  }

  .finance-overview {
    padding: 12px 14px;
  }

  .finance-net-amount {
    margin-top: 8px;
    font-size: 30px;
  }

  .finance-metric {
    padding: 11px 12px;
  }

  .finance-metric strong {
    font-size: 15px;
  }

  .finance-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .finance-metric:nth-child(2) {
    border-right: 0;
  }

  .finance-metric:nth-child(-n + 2) {
    border-bottom: 1px solid #e7edf3;
  }
}
</style>
