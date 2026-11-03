<script setup lang="ts">
import { ref, watch } from "vue";
import AppButton from "@/components/ui/AppButton.vue";
import { copyContact } from "@/utils/clipboard";
import { liteApi, type LiteOrderDetail } from "@/lite/api";

/**
 * 订单详情底部弹层：拉取公开脱敏详情，展示原文/要求/费用三分，
 * 转化动作只有「复制中介微信」——轻薄版不提供投递与家长联系方式。
 */
const props = defineProps<{
  inviteCode: string;
  orderId: number | null;
  fallbackWechat: string | null;
}>();

const emit = defineEmits<{ (e: "show-on-map", order: LiteOrderDetail): void }>();

const visible = defineModel<boolean>("visible", { default: false });

const detail = ref<LiteOrderDetail | null>(null);
const loading = ref(false);
const loadFailed = ref(false);

watch(
  () => [props.orderId, visible.value] as const,
  async ([id, show], [prevId]) => {
    if (!show || id == null) return;
    if (detail.value && prevId === id) return;
    loading.value = true;
    loadFailed.value = false;
    try {
      detail.value = await liteApi.getOrderDetail(props.inviteCode, id);
    } catch {
      loadFailed.value = true;
    } finally {
      loading.value = false;
    }
  },
);

watch(visible, (show) => {
  if (!show) {
    detail.value = null;
    loadFailed.value = false;
  }
});

const wechat = () => detail.value?.contact_wechat || props.fallbackWechat || "";

function priceUnit(priceTotal: string) {
  return String(priceTotal || "").includes("小时") ? "小时" : "次";
}

function copyWechat() {
  const target = wechat();
  if (!target) return;
  void copyContact(target, "已复制中介微信，添加时说明想看的订单");
}
</script>

<template>
  <van-popup v-model:show="visible" position="bottom" round class="max-h-[80vh]">
    <div class="flex flex-col gap-3 overflow-y-auto px-4 pb-[calc(20px+env(safe-area-inset-bottom))] pt-4">
      <template v-if="loading">
        <van-skeleton title :row="4" />
      </template>

      <template v-else-if="loadFailed || !detail">
        <p class="py-8 text-center text-sm text-secondary">详情加载失败，请稍后重试</p>
      </template>

      <template v-else>
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <h3 class="truncate text-base font-semibold text-ink">{{ detail.grade_subject }}</h3>
            <p class="mt-0.5 text-xs text-muted">
              {{ detail.fuzzy_address }}<template v-if="detail.subway_remark"> · {{ detail.subway_remark }}</template>
            </p>
          </div>
          <p class="flex-none text-base font-semibold" :class="detail.needs_manual_price ? 'text-secondary' : 'text-accent'">
            {{ detail.needs_manual_price ? "自带价" : `¥${Number(detail.base_price)}/${priceUnit(detail.price_total)}` }}
          </p>
        </div>

        <div class="grid grid-cols-3 gap-2 rounded-2xl bg-surface-soft p-3 text-center">
          <div>
            <p class="text-[11px] text-muted">信息费</p>
            <p class="mt-0.5 text-sm font-semibold text-ink">¥{{ Number(detail.calculated_info_fee) }}</p>
          </div>
          <div>
            <p class="text-[11px] text-muted">定金</p>
            <p class="mt-0.5 text-sm font-semibold text-ink">¥{{ Number(detail.deposit_amount) }}</p>
          </div>
          <div>
            <p class="text-[11px] text-muted">尾款</p>
            <p class="mt-0.5 text-sm font-semibold text-ink">¥{{ Number(detail.balance_amount) }}</p>
          </div>
        </div>

        <div class="rounded-2xl border border-default p-3">
          <p class="text-[11px] font-medium text-muted">订单信息</p>
          <p class="mt-1 whitespace-pre-wrap text-xs leading-5 text-secondary">{{ detail.raw_text }}</p>
        </div>

        <div v-if="detail.requirements" class="rounded-2xl border border-default p-3">
          <p class="text-[11px] font-medium text-muted">教员要求</p>
          <p class="mt-1 whitespace-pre-wrap text-xs leading-5 text-secondary">{{ detail.requirements }}</p>
        </div>

        <p class="text-[11px] leading-4 text-muted">
          每周 {{ detail.weekly_frequency }} 次 · 家长联系方式由中介线下对接，感兴趣请直接联系中介微信
        </p>

        <div class="flex gap-3">
          <AppButton
            v-if="Number.isFinite(Number(detail.lng)) && Number.isFinite(Number(detail.lat))"
            variant="secondary"
            block
            @click="emit('show-on-map', detail)"
          >
            <van-icon name="location-o" class="mr-1" /> 在地图上查看
          </AppButton>
          <AppButton v-if="wechat()" block @click="copyWechat">复制微信（{{ wechat() }}）</AppButton>
          <AppButton v-else variant="secondary" block disabled>该中介暂未提供联系微信</AppButton>
        </div>
      </template>
    </div>
  </van-popup>
</template>
