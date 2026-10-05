<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { formatMoney, formatDateTime, todayStr } from "@/utils/format";
import { parseDbTime } from "@/utils/format";
import { useSmartBack } from "@/composables/useSmartBack";
import client from "@/api/client";
import { financialApi, type FinancialFilters, type FinancialTypeFilter } from "@/api/financial";
import type { FinancialRecordItem, FinancialSummaryResponse } from "@/api/types";
import { usePagedList } from "@/composables/usePagedList";
import AdminShell from "@/components/admin/AdminShell.vue";
import { showSuccessToast, showToast } from "vant";

const { goBack } = useSmartBack("/admin/dashboard");
const exporting = ref(false);
const summary = ref<FinancialSummaryResponse>({
  deposit_in: 0,
  balance_in: 0,
  refund_out: 0,
  forfeit: 0,
  net_amount: 0,
  records: [],
});

const typeOptions: { label: string; value: FinancialTypeFilter | null }[] = [
  { label: "定金收入", value: "deposit_in" },
  { label: "尾款收入", value: "balance_in" },
  { label: "退款支出", value: "refund_out" },
  { label: "定金没收", value: "forfeit" },
];
const datePresets = ["全部", "近7天", "近30天", "本月"];

const typeFilter = ref<FinancialTypeFilter | null>(null);
const datePreset = ref("全部");

// 财务对账页必须用本地时区日期：toISOString() 走 UTC，东八区 0-8 点会把"今天"算成昨天
function formatDay(date: Date) {
  return todayStr(date);
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

// 汇总口径只随日期走、不随类型走——四张指标卡要常驻展示四类全额，
// 类型筛选只影响明细列表。因此 summary 单独拉取（date-only filters）。
const summaryFilters = computed<FinancialFilters>(() => {
  const { type: _type, ...dateOnly } = activeFilters.value;
  return dateOnly;
});

async function refreshSummary() {
  const res = await financialApi.list(1, 1, summaryFilters.value);
  summary.value = res;
}

onMounted(() => loadData());

// 明细 fetcher：类型 + 日期全量过滤；summary 由 refreshSummary 单独维护
const pagedList = usePagedList<FinancialRecordItem>(
  (page, pageSize) =>
    financialApi.list(page, pageSize, activeFilters.value).then((res) => ({ items: res.records || [] })),
  { pageSize: 50 }
);
const { items: records, loadingMore, hasMore } = pagedList;
const loading = pagedList.loading;
loading.value = true; // 首屏渲染即展示遮罩，与接入前行为一致

async function loadData() {
  try {
    await Promise.all([pagedList.load(), refreshSummary()]);
  } catch (e) {
    showToast(getApiErrorMessage(e, "加载财务数据失败"));
  }
}

function toggleTypeFilter(value: FinancialTypeFilter) {
  // 拉取期间忽略再点击：防并发响应乱序覆盖（旧遮罩曾靠挡住整页顺带做到这点）
  if (loading.value) return;
  typeFilter.value = typeFilter.value === value ? null : value;
  loadData();
}

function setDatePreset(preset: string) {
  if (loading.value) return;
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
    link.download = `财务流水_${todayStr()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  } catch {
    showToast("导出失败，请重试");
  } finally {
    exporting.value = false;
  }
}

async function loadMore() {
  try {
    await pagedList.loadMore();
  } catch {
    showToast("加载更多失败，请重试");
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

// 金额/时间统一走 utils/format，与全站展示口径一致
const formatAmount = (value: number | string | null | undefined) => formatMoney(value).slice(1);
const formatDate = (value: string) => formatDateTime(value);

// ── 资金三性（与后端注释同口径：没收是性质标注，不计净额）──
type MoneyNature = "income" | "expense" | "note";
function natureOf(type: string): MoneyNature {
  if (type === "refund_out") return "expense";
  if (type === "forfeit") return "note";
  return "income";
}
/** 带符号金额：收入 +、退款 −、没收无符号（琥珀展示，避免与净额对不上） */
function signedAmount(record: FinancialRecordItem): string {
  const nature = natureOf(record.type);
  if (nature === "expense") return `−¥${formatAmount(record.amount)}`;
  if (nature === "note") return `¥${formatAmount(record.amount)}`;
  return `+¥${formatAmount(record.amount)}`;
}
function amountClass(record: FinancialRecordItem): string {
  const nature = natureOf(record.type);
  if (nature === "expense") return "text-danger-deep";
  if (nature === "note") return "text-warning-deep";
  return "text-success-deep";
}

function orderLabel(record: FinancialRecordItem) {
  return record.order_subject
    ? `${record.order_subject} · #${record.order_id}`
    : `订单 #${record.order_id}`;
}

function operatorLabel(record: FinancialRecordItem) {
  return record.operator_role === "tenant_admin"
    ? "中介管理员"
    : record.operator_role === "super_admin"
      ? "平台老板"
      : "教员本人";
}

// ── 按日分组账本：日小计 = 收入 − 退款（没收不计，与净额口径一致）──
const groupedByDay = computed(() => {
  const groups: { day: string; label: string; weekday: string; count: number; subtotal: number; records: FinancialRecordItem[] }[] = [];
  const index = new Map<string, number>();
  for (const record of records.value) {
    const t = parseDbTime(record.created_at);
    const day = formatDay(t);
    let gi = index.get(day);
    if (gi === undefined) {
      gi = groups.length;
      index.set(day, gi);
      const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
      groups.push({
        day,
        label: `${t.getMonth() + 1}月${t.getDate()}日`,
        weekday: weekdays[t.getDay()],
        count: 0,
        subtotal: 0,
        records: [],
      });
    }
    const g = groups[gi];
    g.records.push(record);
    g.count += 1;
    const nature = natureOf(record.type);
    if (nature === "income") g.subtotal += Number(record.amount);
    if (nature === "expense") g.subtotal -= Number(record.amount);
  }
  return groups;
});

function subtotalLabel(subtotal: number): string {
  if (subtotal > 0) return `+¥${formatAmount(subtotal)}`;
  if (subtotal < 0) return `−¥${formatAmount(Math.abs(subtotal))}`;
  return `¥${formatAmount(0)}`;
}
function subtotalClass(subtotal: number): string {
  if (subtotal > 0) return "text-success-deep";
  if (subtotal < 0) return "text-danger-deep";
  return "text-muted";
}

/** 净收入卡上的范围标注：与 datePreset 对应的真实起止 */
const rangeLabel = computed(() => {
  const f = summaryFilters.value;
  if (!f.start_date && !f.end_date) return "全部时间";
  return `${f.start_date ?? "…"} – ${f.end_date ?? "…"}`;
});

// 指标卡即筛选项：选中反色；again summary 是"全部类型"口径，金额不受选中影响
function metricCardClass(value: FinancialTypeFilter): string {
  return typeFilter.value === value
    ? "bg-brand-900 text-white border-brand-900"
    : "bg-surface text-primary border-default";
}

function metricNote(value: FinancialTypeFilter): string {
  if (value === "forfeit") return "性质标注 · 不计净额";
  if (value === "deposit_in" || value === "balance_in") {
    const income = Number(summary.value.deposit_in) + Number(summary.value.balance_in);
    const share = income > 0 ? Math.round((Number(summary.value[value]) / income) * 100) : 0;
    return `占收入 ${share}%`;
  }
  const expense = Number(summary.value.refund_out);
  const share = expense > 0 ? Math.round((Number(summary.value.refund_out) / expense) * 100) : 0;
  return `占支出 ${share}%`;
}

// ── 收款凭证：上传 + 预览（半线上化对账增强）；行内只留一个回形针入口 ──
const receiptPreviewVisible = ref(false);
const receiptPreviewUrl = ref("");
const receiptUploadingId = ref<number | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);
const receiptTargetId = ref<number | null>(null);

function paperclipClass(record: FinancialRecordItem): string {
  if (receiptUploadingId.value === record.id) return "text-muted";
  return record.has_receipt ? "text-brand-700" : "text-muted";
}

function onPaperclip(record: FinancialRecordItem) {
  if (receiptUploadingId.value === record.id) return;
  if (record.has_receipt) {
    void openReceipt(record);
  } else {
    pickReceipt(record);
  }
}

async function openReceipt(record: FinancialRecordItem) {
  try {
    // 图片需鉴权：axios 附 token 取 blob，再交给预览弹层
    const res = await client.get(financialApi.receiptUrl(record.id), { responseType: "blob" });
    receiptPreviewUrl.value = URL.createObjectURL(res.data);
    receiptPreviewVisible.value = true;
  } catch {
    showToast("凭证加载失败");
  }
}

function pickReceipt(record: FinancialRecordItem) {
  receiptTargetId.value = record.id;
  fileInput.value?.click();
}

async function onReceiptChosen(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = ""; // 允许重复选择同一文件
  if (!file || receiptTargetId.value == null) return;
  if (file.size > 5 * 1024 * 1024) {
    showToast("凭证不能超过 5MB");
    return;
  }
  receiptUploadingId.value = receiptTargetId.value;
  try {
    const updated = await financialApi.uploadReceipt(receiptTargetId.value, file);
    const target = records.value.find((r) => r.id === updated.id);
    if (target) target.has_receipt = true;
    showSuccessToast("凭证已保存");
  } catch (e) {
    showToast(getApiErrorMessage(e, "凭证上传失败"));
  } finally {
    receiptUploadingId.value = null;
    receiptTargetId.value = null;
  }
}
</script>

<template>
  <AdminShell fluid>
    <van-nav-bar title="财务流水" left-arrow @click-left="goBack">
      <template #right>
        <button
          class="text-xs font-medium text-secondary disabled:opacity-50"
          :disabled="exporting"
          @click="exportCsv"
        >
          {{ exporting ? "导出中..." : "导出" }}
        </button>
      </template>
    </van-nav-bar>

    <main class="finance-content">
      <!-- 净收入卡：范围常驻 + 日期切换即时更新 -->
      <section class="finance-overview">
        <div class="finance-overview__heading">
          <div>
            <h1>净收入</h1>
            <span class="finance-range">
              <van-icon name="clock-o" size="11" />
              {{ rangeLabel }}
            </span>
          </div>
          <button class="finance-refresh" :disabled="loading" @click="loadData">
            <van-icon name="replay" size="15" />
          </button>
        </div>
        <div class="finance-net-amount">¥{{ formatAmount(summary.net_amount) }}</div>
        <div class="finance-net-split">
          <span>收入 <b class="text-success-deep">¥{{ formatAmount(Number(summary.deposit_in) + Number(summary.balance_in)) }}</b></span>
          <span aria-hidden="true">–</span>
          <span>支出 <b class="text-danger-deep">¥{{ formatAmount(summary.refund_out) }}</b></span>
          <span class="finance-net-note">没收不计</span>
        </div>
        <div class="finance-date-chips">
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
      </section>

      <!-- 指标卡 = 筛选项：选中反色，金额常驻全额口径 -->
      <section class="finance-metrics" aria-label="财务指标（点击筛选明细）">
        <button
          v-for="opt in typeOptions"
          :key="opt.value ?? 'all'"
          class="finance-metric"
          :class="metricCardClass(opt.value!)"
          @click="toggleTypeFilter(opt.value!)"
        >
          <span>{{ opt.label }}</span>
          <strong class="font-bold">¥{{ formatAmount(summary[opt.value as FinancialTypeFilter]) }}</strong>
          <span
            class="finance-metric__note"
            :class="typeFilter === opt.value ? 'text-white/60' : 'text-muted'"
          >
            {{ metricNote(opt.value!) }}
          </span>
        </button>
      </section>

      <div class="finance-section-heading">
        <div>
          <h2>流水明细</h2>
          <span>{{ records.length }} 笔 · 按日分组</span>
        </div>
      </div>

      <!-- 首屏加载：明细区行内转圈（本页自 v2 起禁用全屏遮罩——从空态筛选切出时它就是黑闪源） -->
      <div v-if="loading && records.length === 0" class="flex justify-center py-16">
        <van-loading type="spinner" size="28" />
      </div>

      <div v-else-if="records.length === 0" class="finance-empty">
        <van-icon name="balance-list-o" size="42" />
        <p class="mt-3 text-sm">暂无流水</p>
      </div>

      <!-- 移动端/窄屏：按日分组账本（数据原子替换，卡片反色已是点击反馈，不再做透明度脉动） -->
      <div v-else class="space-y-4 lg:hidden">
        <section
          v-for="group in groupedByDay"
          :key="group.day"
        >
          <div class="mb-1.5 flex items-baseline justify-between">
            <h3 class="text-emphasis font-bold text-primary">
              {{ group.label }} <span class="text-muted">{{ group.weekday }}</span>
              <span class="ml-1 text-caption font-normal text-muted">· {{ group.count }} 笔</span>
            </h3>
            <span
              class="text-emphasis font-bold tabular-nums"
              :class="subtotalClass(group.subtotal)"
            >
              {{ subtotalLabel(group.subtotal) }}
            </span>
          </div>
          <div class="overflow-hidden rounded-2xl border border-default bg-surface shadow-card">
            <div
              v-for="record in group.records"
              :key="record.id"
              class="border-b border-dashed border-default px-4 py-3 last:border-b-0"
            >
              <div class="flex items-baseline justify-between gap-3">
                <span class="min-w-0 truncate text-title font-bold text-primary">
                  {{ orderLabel(record) }}
                </span>
                <span
                  class="shrink-0 text-headline font-bold tabular-nums"
                  :class="amountClass(record)"
                >
                  {{ signedAmount(record) }}
                </span>
              </div>
              <div class="mt-1 flex items-center justify-between gap-2">
                <span class="flex min-w-0 flex-wrap items-center gap-x-1.5 text-body leading-5 text-secondary">
                  <span :class="typeClasses[record.type]">{{ typeLabels[record.type] || record.type }}</span>
                  <span v-if="record.teacher_name" class="truncate">{{ record.teacher_name }}</span>
                  <span>{{ formatDate(record.created_at).slice(11, 16) }}</span>
                  <span v-if="record.operator_role">· {{ operatorLabel(record) }}</span>
                </span>
                <button
                  class="shrink-0"
                  :class="paperclipClass(record)"
                  :aria-label="record.has_receipt ? '看凭证' : '传凭证'"
                  @click="onPaperclip(record)"
                >
                  <van-icon name="description-o" size="15" />
                </button>
              </div>
              <div v-if="record.remark" class="mt-0.5 truncate text-caption text-muted">
                {{ record.remark }}
              </div>
            </div>
          </div>
        </section>
      </div>

      <!-- 宽屏 ≥1024px：六列表格（同一数据源，口径与移动端一致） -->
      <div v-if="records.length !== 0" class="hidden lg:block">
        <div class="overflow-hidden rounded-2xl border border-default bg-surface shadow-card">
          <table class="w-full text-left text-sm">
            <thead>
              <tr class="border-b border-default text-caption text-muted">
                <th class="px-4 py-2.5 font-medium">类型</th>
                <th class="px-2 py-2.5 font-medium">订单</th>
                <th class="px-2 py-2.5 font-medium">教员</th>
                <th class="px-2 py-2.5 font-medium">备注 / 登记人</th>
                <th class="px-2 py-2.5 font-medium">时间</th>
                <th class="px-4 py-2.5 text-right font-medium">金额</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="record in records"
                :key="record.id"
                class="border-b border-dashed border-default last:border-b-0 hover:bg-surface-soft/60"
              >
                <td class="px-4 py-2.5">
                  <span :class="typeClasses[record.type]">{{ typeLabels[record.type] || record.type }}</span>
                </td>
                <td class="max-w-[220px] truncate px-2 py-2.5 text-body text-primary">
                  {{ orderLabel(record) }}
                  <span class="mono block text-caption text-muted">{{ record.order_raw_id || "" }}</span>
                </td>
                <td class="px-2 py-2.5 text-body text-secondary">
                  {{ record.teacher_name || `教员 #${record.teacher_id}` }}
                </td>
                <td class="max-w-[200px] px-2 py-2.5 text-body-sm text-muted">
                  <span class="block truncate">{{ record.remark || "无备注" }}</span>
                  <span class="block">{{ operatorLabel(record) }}</span>
                </td>
                <td class="px-2 py-2.5 text-body-sm text-muted">{{ formatDate(record.created_at) }}</td>
                <td class="px-4 py-2.5 text-right">
                  <span
                    class="text-emphasis font-bold tabular-nums"
                    :class="amountClass(record)"
                  >{{ signedAmount(record) }}</span>
                  <button
                    class="ml-2 align-middle"
                    :class="paperclipClass(record)"
                    :aria-label="record.has_receipt ? '看凭证' : '传凭证'"
                    @click="onPaperclip(record)"
                  >
                    <van-icon name="description-o" size="14" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <button
          v-if="hasMore"
          class="finance-more-btn"
          :disabled="loadingMore"
          @click="loadMore"
        >
          {{ loadingMore ? "加载中..." : "加载更多记录" }}
        </button>
      </div>

      <button
        v-if="hasMore && records.length !== 0"
        class="finance-more-btn lg:hidden"
        :disabled="loadingMore"
        @click="loadMore"
      >
        {{ loadingMore ? "加载中..." : "加载更多记录" }}
      </button>
    </main>

    <!-- v2：本页不再有任何全屏遮罩（空态筛选切出时它就是黑闪源）；首屏转圈在明细区行内 -->
    <!-- 收款凭证预览 -->
    <van-image-preview v-model:show="receiptPreviewVisible" :images="receiptPreviewUrl ? [receiptPreviewUrl] : []" />

    <!-- 隐藏的文件选择器：凭证上传走系统相册/文件 -->
    <input
      ref="fileInput"
      type="file"
      accept="image/png,image/jpeg,image/webp"
      class="hidden"
      @change="onReceiptChosen"
    >
  </AdminShell>
</template>

<style scoped>
.finance-content {
  width: min(100%, 720px);
  margin: 0 auto;
  padding: 12px 16px 32px;
}

@media (min-width: 1024px) {
  .finance-content {
    width: min(100%, 1100px);
  }
}

.finance-overview {
  padding: 14px 16px;
  border: 1px solid var(--st-border);
  border-radius: 14px;
  background: var(--st-surface);
}

.finance-overview__heading,
.finance-section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.finance-overview__heading > div {
  display: flex;
  align-items: center;
  gap: 8px;
}

.finance-range {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--st-text-secondary);
  font-size: var(--st-text-caption);
}

.finance-section-heading span {
  color: var(--st-text-secondary);
  font-size: var(--st-text-body-sm);
}

.finance-overview h1,
.finance-section-heading h2 {
  margin: 0;
  color: var(--st-text-primary);
  font-size: var(--st-text-emphasis);
  font-weight: 700;
}

.finance-refresh {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--st-text-secondary);
  font-size: var(--st-text-body);
}

.finance-net-amount {
  margin-top: 6px;
  color: var(--st-text-primary);
  font-size: 32px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.03em;
}

.finance-net-split {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--st-border);
  color: var(--st-text-secondary);
  font-size: var(--st-text-body-sm);
}

.finance-net-split b {
  font-variant-numeric: tabular-nums;
}

.finance-net-note {
  margin-left: auto;
}

.finance-date-chips {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  padding: 3px;
  border-radius: 10px;
  background: var(--st-surface-soft);
}

.finance-chip {
  flex: 1;
  padding: 6px 0;
  border-radius: 8px;
  font-size: var(--st-text-body-sm);
  color: var(--st-text-secondary);
  white-space: nowrap;
}

.finance-chip--active {
  background: var(--st-surface);
  color: var(--st-text-primary);
  font-weight: 600;
  box-shadow: var(--st-shadow-sm);
}

.finance-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.finance-metric {
  min-width: 0;
  padding: 12px 14px;
  border: 1px solid var(--st-border);
  border-radius: 14px;
  text-align: left;
}

.finance-metric span:first-child {
  display: block;
  color: var(--st-text-secondary);
  font-size: var(--st-text-body-sm);
}

.finance-metric strong {
  display: block;
  margin-top: 4px;
  font-size: var(--st-text-title);
  font-variant-numeric: tabular-nums;
}

.finance-metric__note {
  display: block;
  margin-top: 2px;
  font-size: var(--st-text-caption);
}

@media (min-width: 1024px) {
  .finance-metrics {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}

.finance-section-heading {
  margin: 22px 0 10px;
}

.finance-tag {
  display: inline-flex;
  align-items: center;
  padding: 3px 9px;
  border-radius: 4px;
  font-size: var(--st-text-body);
  font-weight: 600;
}

.finance-tag--deposit { color: var(--st-brand-700); background: var(--st-brand-50); }
.finance-tag--balance { color: var(--st-success-deep); background: var(--st-success-soft); }
.finance-tag--refund { color: var(--st-danger-deep); background: var(--st-danger-soft); }
.finance-tag--forfeit { color: var(--st-warning-deep); background: var(--st-warning-soft); }

.finance-more-btn {
  display: block;
  width: 100%;
  margin-top: 12px;
  padding: 10px 0;
  border: 1px solid var(--st-border);
  border-radius: 10px;
  background: var(--st-surface);
  color: var(--st-text-secondary);
  font-size: var(--st-text-body);
}

.finance-empty {
  padding: 64px 16px;
  border: 1px solid var(--st-border);
  border-radius: 14px;
  background: var(--st-surface);
  color: var(--st-text-muted);
  text-align: center;
}
</style>
