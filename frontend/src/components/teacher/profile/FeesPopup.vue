<script setup lang="ts">
/**
 * 我的费用结算单弹层（自 Profile.vue 拆出）：汇总三项金额 + 流水列表 + CSV 导出。
 */
import { ref, watch } from "vue";
import { formatMoney, todayStr } from "@/utils/format";
import { financialApi } from "@/api/financial";
import client from "@/api/client";
import { showToast } from "vant";

const show = defineModel<boolean>("show", { default: false });

const feesLoading = ref(false);
// 与 api/types.ts 的 FinancialRecordItem 保持同构（本地内联避免循环依赖的历史原因）
const fees = ref<{
  total_paid: number;
  total_refunded: number;
  total_forfeit: number;
  records: {
    id: number;
    order_id: number;
    raw_order_id?: string | null;
    amount: number;
    type: string;
    remark?: string | null;
    created_at: string;
    has_receipt?: boolean;
  }[];
} | null>(null);

const feeTypeLabels: Record<string, { label: string; sign: string; cls: string }> = {
  deposit_in: { label: "定金支付", sign: "-", cls: "text-slate-700" },
  balance_in: { label: "尾款支付", sign: "-", cls: "text-slate-700" },
  refund_out: { label: "退款到账", sign: "+", cls: "text-emerald-600" },
  forfeit: { label: "违约没收", sign: "-", cls: "text-red-500" },
};

watch(
  show,
  async (visible) => {
    if (!visible) return;
    feesLoading.value = true;
    try {
      // 后端已按页返回：循环取完所有页（硬上限 500 条，防御流水膨胀）；
      // 顶部三项汇总由后端 SQL 聚合，不受分页影响
      fees.value = await fetchAllFees();
    } catch {
      showToast("费用加载失败");
    } finally {
      feesLoading.value = false;
    }
  },
  { immediate: true }
);

const PAGE_SIZE = 50;
const MAX_RECORDS = 500;

// 凭证预览（后端按"流水归属教员本人"鉴权；blob 方式带 token 拉取）
const receiptPreviewVisible = ref(false);
const receiptPreviewUrl = ref("");

async function viewReceipt(recordId: number) {
  try {
    const res = await client.get(financialApi.receiptUrl(recordId), { responseType: "blob" });
    receiptPreviewUrl.value = URL.createObjectURL(res.data);
    receiptPreviewVisible.value = true;
  } catch {
    showToast("凭证加载失败");
  }
}

async function fetchAllFees(): Promise<NonNullable<typeof fees.value>> {
  const records: NonNullable<typeof fees.value>["records"] = [];
  let summary: NonNullable<typeof fees.value> | null = null;
  for (let page = 1; records.length < MAX_RECORDS; page++) {
    const res = await financialApi.myFees(page, PAGE_SIZE);
    summary = res;
    records.push(...res.records);
    if (res.records.length < PAGE_SIZE) break;
  }
  return summary ? { ...summary, records: records.slice(0, MAX_RECORDS) } : { total_paid: 0, total_refunded: 0, total_forfeit: 0, records: [] };
}

const feesExporting = ref(false);

async function exportFees() {
  feesExporting.value = true;
  try {
    const res = await client.get(financialApi.myFeesExportUrl(), { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = `我的费用_${todayStr()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  } catch {
    showToast("导出失败，请重试");
  } finally {
    feesExporting.value = false;
  }
}
</script>

<template>
  <van-popup v-model:show="show" round position="bottom" :style="{ maxHeight: '75vh' }" close-on-click-overlay>
    <div class="flex max-h-[75vh] flex-col p-4">
      <div class="mb-3 flex items-center justify-between">
        <div class="text-base font-semibold text-slate-950">我的费用</div>
        <button
          v-if="fees && fees.records.length > 0"
          class="text-sm text-blue-600 disabled:opacity-50"
          :disabled="feesExporting"
          @click="exportFees"
        >
          {{ feesExporting ? "导出中..." : "导出 CSV" }}
        </button>
      </div>
      <div class="overflow-y-auto">
        <div v-if="feesLoading" class="flex justify-center py-8">
          <van-loading type="spinner" color="#2563eb" />
        </div>
        <template v-else-if="fees">
          <div class="mb-4 grid grid-cols-3 gap-2 text-center">
            <div class="rounded-xl bg-slate-50 p-3">
              <div class="text-lg font-bold text-slate-900">{{ formatMoney(fees.total_paid) }}</div>
              <div class="mt-0.5 text-xs text-slate-400">累计支付</div>
            </div>
            <div class="rounded-xl bg-slate-50 p-3">
              <div class="text-lg font-bold text-emerald-600">{{ formatMoney(fees.total_refunded) }}</div>
              <div class="mt-0.5 text-xs text-slate-400">累计已退</div>
            </div>
            <div class="rounded-xl bg-slate-50 p-3">
              <div class="text-lg font-bold text-red-500">{{ formatMoney(fees.total_forfeit) }}</div>
              <div class="mt-0.5 text-xs text-slate-400">违约没收</div>
            </div>
          </div>
          <div v-if="fees.records.length === 0" class="py-8 text-center text-sm text-slate-400">
            暂无费用记录。投递成交后，定金与尾款流水会在这里登记。
          </div>
          <div v-else class="space-y-2 pb-4">
            <div
              v-for="record in fees.records"
              :key="record.id"
              class="flex items-center justify-between rounded-lg border border-slate-100 p-3"
            >
              <div class="min-w-0">
                <div class="text-sm font-medium text-slate-800">
                  {{ feeTypeLabels[record.type]?.label || record.type }}
                  <span class="ml-1 text-xs text-slate-400">
                    订单 {{ record.raw_order_id || `#${record.order_id}` }}
                  </span>
                </div>
                <div class="mt-0.5 text-xs text-slate-400">
                  {{ new Date(record.created_at).toLocaleString("zh-CN") }}
                  <span v-if="record.remark"> · {{ record.remark }}</span>
                </div>
                <button
                  v-if="record.has_receipt"
                  class="mt-1 text-xs font-medium text-blue-600"
                  @click="viewReceipt(record.id)"
                >
                  查看收款凭证 →
                </button>
              </div>
              <div
                class="shrink-0 text-sm font-bold"
                :class="feeTypeLabels[record.type]?.cls || 'text-slate-700'"
              >
                {{ feeTypeLabels[record.type]?.sign || "" }}{{ formatMoney(record.amount) }}
              </div>
            </div>
          </div>
        </template>
      </div>
    </div>
  </van-popup>

  <!-- 凭证图片预览（鉴权 blob） -->
  <van-image-preview v-model:show="receiptPreviewVisible" :images="receiptPreviewUrl ? [receiptPreviewUrl] : []" />
</template>
