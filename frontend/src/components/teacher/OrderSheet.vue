<script setup lang="ts">
/**
 * 订单操作面板（自 Board.vue 拆出，P1-1）：
 * 地图标记点击后弹出的订单摘要与动作（查看详情 / 一键投递）。
 */
const props = defineProps<{
  show: boolean;
  order: any | null;
}>();

const emit = defineEmits<{
  (e: "update:show", value: boolean): void;
  (e: "view", order: any): void;
  (e: "apply", order: any): void;
}>();

function close() {
  emit("update:show", false);
}
</script>

<template>
  <van-action-sheet
    :show="show"
    :title="order?.grade_subject || ''"
    :description="order ? `${order.fuzzy_address}${order.subway_remark ? ' · ' + order.subway_remark : ''}` : ''"
    @update:show="(value: boolean) => emit('update:show', value)"
  >
    <div v-if="order" class="p-4">
      <div class="bg-gray-50 rounded-xl p-3 mb-3 text-sm">
        <template v-if="order.needs_manual_price">自带价 · 报价后可算</template>
        <template v-else>
          信息费
          <span class="text-primary-600 font-bold text-lg ml-2">¥{{ order.calculated_info_fee }}</span>
          <div class="text-xs text-gray-400 mt-1">
            定金 ¥{{ order.deposit_amount }} + 尾款 ¥{{ order.balance_amount }}
          </div>
        </template>
      </div>
      <button
        class="w-full bg-gray-50 rounded-xl py-3 mb-2 text-sm font-medium"
        @click="close(); emit('view', order)"
      >
        查看详情
      </button>
      <button
        class="w-full header-gradient text-white rounded-xl py-3 text-sm font-semibold"
        @click="close(); emit('apply', order)"
      >
        一键投递
      </button>
    </div>
  </van-action-sheet>
</template>
