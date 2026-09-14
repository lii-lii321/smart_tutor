<script setup lang="ts">
/**
 * 试课失败 · 退费精算弹层（自 ApplicationsReview.vue 拆出）。
 * 金额口径以后端下发的投递 fee 快照为准；退费公式仅作展示预览，最终以后端精算为准。
 */
import { computed, ref, watch } from "vue";
import type { ApplicationItem } from "@/api/types";
import { applicationsApi } from "@/api/applications";
import { getApiErrorMessage } from "@/utils/apiError";
import { showSuccessToast, showToast } from "vant";

const show = defineModel<boolean>("show", { default: false });

const props = defineProps<{
  app: ApplicationItem | null;
}>();

const emit = defineEmits<{ (e: "confirmed"): void }>();

const trialPaidByParent = ref("");
const isTeacherViolated = ref(false);
const manualRefund = ref("");
const submitting = ref(false);

watch(show, (visible) => {
  if (visible) {
    trialPaidByParent.value = "";
    isTeacherViolated.value = false;
    manualRefund.value = "";
  }
});

function paidAmountFor(app: ApplicationItem): { paid: number; deposit: number; balance: number } {
  const fee = app.fee ?? { total_info_fee: 0, deposit: 0, balance: 0 };
  const deposit = Number(fee.deposit) || 0;
  const balance = Number(fee.balance) || 0;
  const paid = deposit + (app.status === "balance_paid" ? balance : 0);
  return { paid: Math.round(paid * 100) / 100, deposit, balance };
}

const trialRefundPreview = computed(() => {
  if (!props.app) return null;
  const { paid } = paidAmountFor(props.app);
  if (isTeacherViolated.value) return 0;
  const trialPaid = Number(trialPaidByParent.value) || 0;
  // 退费系数 0.7 与后端 services/calculator.py::calculate_refund 一致（仅为展示预览，最终以后端精算为准）
  if (trialPaid > 0) return Math.max(0, Math.round((paid - trialPaid * 0.7) * 100) / 100);
  return Math.max(0, Math.round((Number(manualRefund.value) || 0) * 100) / 100);
});

async function confirmTrialFailed() {
  const app = props.app;
  if (!app) return;
  submitting.value = true;
  try {
    await applicationsApi.trialFailed(
      app.id,
      Number(manualRefund.value) || 0,
      Number(trialPaidByParent.value) || 0,
      isTeacherViolated.value,
    );
    showSuccessToast("订单已重新开放");
    show.value = false;
    emit("confirmed");
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  } finally {
    submitting.value = false;
  }
}
</script>

<template>
  <van-popup
    v-model:show="show"
    position="bottom"
    round
  >
    <div
      v-if="app"
      class="max-h-[80vh] overflow-y-auto p-5"
    >
      <div class="mb-4 text-lg font-bold">
        试课失败 · 退费精算
      </div>

      <div class="mb-3 rounded-xl bg-gray-50 p-3 text-sm text-gray-600 space-y-1">
        <div>教员：<span class="font-medium">{{ app.teacher?.name || `教员 #${app.teacher_id}` }}</span></div>
        <div>已收信息费：<span class="font-medium text-gray-800">¥{{ paidAmountFor(app).paid }}</span></div>
        <div class="text-xs text-gray-400">
          定金 ¥{{ paidAmountFor(app).deposit }}<template v-if="app.status === 'balance_paid'">
            + 尾款 ¥{{ paidAmountFor(app).balance }}
          </template>
        </div>
      </div>

      <div class="space-y-3 text-sm">
        <div>
          <div class="mb-1 text-gray-600">
            家长已支付给教员的试课酬（元，选填）
          </div>
          <van-field
            v-model="trialPaidByParent"
            type="number"
            placeholder="填写后按公式自动精算退款"
            class="rounded-lg border border-gray-200"
          />
        </div>
        <div v-if="!trialPaidByParent">
          <div class="mb-1 text-gray-600">
            或手动指定退款金额（元）
          </div>
          <van-field
            v-model="manualRefund"
            type="number"
            placeholder="不填则默认 0 元退款"
            class="rounded-lg border border-gray-200"
          />
        </div>
        <div class="flex items-center justify-between rounded-lg bg-orange-50 p-3">
          <span class="text-gray-700">教员违约（没收全部信息费）</span>
          <van-switch
            v-model="isTeacherViolated"
            size="22px"
          />
        </div>
        <div class="rounded-lg bg-blue-50 p-3 text-blue-700">
          预计退款：<span class="text-lg font-bold">¥{{ trialRefundPreview ?? 0 }}</span>
          <div class="mt-1 text-xs text-blue-400">
            精算公式：退款 = max(0, 已收信息费 − 家长试课酬 × 70%)；实际以平台记录为准
          </div>
        </div>
      </div>

      <div class="mt-4 grid grid-cols-2 gap-3">
        <button
          class="rounded-lg bg-gray-100 py-2.5 text-sm font-medium text-gray-600"
          @click="show = false"
        >
          取消
        </button>
        <button
          class="rounded-lg bg-red-500 py-2.5 text-sm font-semibold text-white"
          :disabled="submitting"
          @click="confirmTrialFailed"
        >
          确认试课失败
        </button>
      </div>
    </div>
  </van-popup>
</template>
