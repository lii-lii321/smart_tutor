<script setup lang="ts">
/**
 * 订单状态机横条（B 端桌面工作台）。
 *
 * 与 components/business/OrderTimeline.vue 的分工：
 *   OrderTimeline  纵向、带时间线与说明，适配详情页纵向阅读（C 端订单详情）
 *   本组件        横向、只表达"走到第几步"，适配审核页顶部常驻，中介随时知道
 *                 当前订单处在候选→试课→成交的哪一环、按钮该点哪个
 *
 * 阶段口径来自 constants/orderStatus.ts + 产品说明 §2.1，不新增后端不存在的状态；
 * archived 是旁支终态（可能发生在任意阶段），如实单列不假装它走过主链。
 */
import { computed } from "vue";
import type { OrderStatus } from "@/api/types";

const props = defineProps<{ status: OrderStatus }>();

const STAGES: { key: Exclude<OrderStatus, "archived">; label: string }[] = [
  { key: "recruiting", label: "招聘中" },
  { key: "trial_in_progress", label: "试课中" },
  { key: "completed", label: "已成交" },
];

const currentIndex = computed(() => STAGES.findIndex((s) => s.key === props.status));
const archived = computed(() => props.status === "archived");
</script>

<template>
  <div v-if="archived" class="flex items-center gap-2 text-[12px] text-muted">
    <span class="h-1.5 w-1.5 rounded-full bg-muted" />
    订单已归档，不在橱窗展示
  </div>
  <ol v-else class="flex items-center gap-1.5">
    <template v-for="(stage, i) in STAGES" :key="stage.key">
      <li v-if="i > 0" class="h-px w-5 shrink-0" :class="i <= currentIndex ? 'bg-brand-300' : 'bg-default'" />
      <li class="flex shrink-0 items-center gap-1.5">
        <span
          class="grid h-4 w-4 place-items-center rounded-full text-[9px] font-bold"
          :class="
            i < currentIndex
              ? 'bg-brand-200 text-brand-800'
              : i === currentIndex
                ? 'bg-brand-800 text-white'
                : 'bg-surface-soft text-muted'
          "
        >
          <template v-if="i < currentIndex">✓</template>
          <template v-else>{{ i + 1 }}</template>
        </span>
        <span
          class="text-[12px] leading-4"
          :class="i === currentIndex ? 'font-semibold text-brand-800' : 'text-muted'"
        >{{ stage.label }}</span>
      </li>
    </template>
  </ol>
</template>
