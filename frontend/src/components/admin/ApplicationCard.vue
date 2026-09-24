<script setup lang="ts">
/**
 * 投递卡片（自 ApplicationsReview.vue 拆出）：
 * 教员信息 + 状态徽标 + 按状态渲染的动作按钮。纯展示组件，动作通过事件交回父级编排。
 */
import { copyContact } from "@/utils/clipboard";
import { formatDateTime } from "@/utils/format";
import type { ApplicationItem } from "@/api/types";
import { APPLICATION_STATUS_LABELS } from "@/constants/applicationStatus";

const props = defineProps<{
  app: ApplicationItem;
  /** 仅招聘中的订单可恢复误拒投递（终态订单的落选不可回退） */
  canRestore: boolean;
}>();

/** 公开成绩单新窗口打开：中介可直接转发链接给家长 */
function openScorecard() {
  if (props.app.teacher) {
    window.open(`/public/teacher/${props.app.teacher.id}/scorecard`, "_blank");
  }
}

const emit = defineEmits<{
  (e: "open-detail", app: ApplicationItem): void;
  (e: "shortlist", appId: number): void;
  (e: "reject", appId: number): void;
  (e: "confirm-deposit", appId: number): void;
  (e: "start-trial", appId: number): void;
  (e: "trial-failed", appId: number): void;
  (e: "confirm-balance", appId: number): void;
  (e: "complete", appId: number): void;
  (e: "forfeit", appId: number): void;
  (e: "review", app: ApplicationItem): void;
  (e: "restore", appId: number): void;
}>();
</script>

<template>
  <div
    class="cursor-pointer bg-white rounded-xl p-3 shadow-sm"
    @click="emit('open-detail', app)"
  >
    <div class="flex items-center justify-between mb-2">
      <div class="flex min-w-0 flex-1 flex-wrap items-center gap-1.5 pr-2">
        <span class="font-semibold text-sm break-all">
          {{ app.teacher?.name || `教员 #${app.teacher_id}` }}
        </span>
        <span
          v-if="app.teacher?.is_985"
          class="px-1.5 py-0.5 rounded-full text-[10px] bg-slate-100 text-slate-600 shrink-0"
        >
          985
        </span>
        <span
          v-if="app.teacher?.is_211"
          class="px-1.5 py-0.5 rounded-full text-[10px] bg-sky-50 text-sky-700 shrink-0"
        >
          211
        </span>
        <span
          v-if="app.teacher?.is_double_first_class"
          class="px-1.5 py-0.5 rounded-full text-[10px] bg-emerald-50 text-emerald-700 shrink-0"
        >
          双一流
        </span>
        <span
          v-if="app.teacher?.is_985_211 && !app.teacher?.is_985 && !app.teacher?.is_211"
          class="px-1.5 py-0.5 rounded-full text-[10px] bg-slate-100 text-slate-600 shrink-0"
        >
          985/211
        </span>
      </div>
      <span
        class="shrink-0 whitespace-nowrap rounded-full px-1.5 py-0.5 text-[11px] leading-4"
        :class="{
          'bg-yellow-100 text-yellow-700': app.status === 'pending',
          'bg-slate-200 text-slate-700': app.status === 'shortlisted',
          'bg-cyan-100 text-cyan-700': app.status === 'deposit_paid',
          'bg-emerald-100 text-emerald-700': app.status === 'trial_in_progress',
          'bg-green-100 text-green-700': app.status === 'balance_paid',
          'bg-emerald-600 text-white': app.status === 'completed',
          'bg-amber-100 text-amber-700': app.status === 'forfeited',
          'bg-gray-100 text-gray-500': ['rejected', 'refunded'].includes(app.status),
        }"
      >
        {{ APPLICATION_STATUS_LABELS[app.status] || app.status }}
      </span>
    </div>

    <div
      v-if="app.teacher"
      class="text-xs text-gray-500 bg-gray-50 rounded-lg p-2 mb-2 space-y-1"
    >
      <div class="font-medium text-gray-700">
        {{ app.teacher.school }}
        <span
          v-if="app.teacher.major"
          class="text-gray-400"
        > · {{ app.teacher.major }}</span>
        <span
          v-if="app.teacher.grade"
          class="text-gray-400"
        > · {{ app.teacher.grade }}</span>
      </div>
      <div class="text-gray-500">
        {{ app.teacher.gender === 'female' ? '女' : '男' }}
        <span v-if="app.teacher.highlights"> · {{ app.teacher.highlights }}</span>
      </div>
      <div class="flex flex-wrap items-center gap-2 pt-0.5">
        <span class="text-emerald-700">成交 {{ app.teacher.completed_count ?? 0 }} 单</span>
        <span
          :class="(app.teacher.violation_count ?? 0) > 0 ? 'text-red-500' : 'text-gray-400'"
        >
          违约 {{ app.teacher.violation_count ?? 0 }} 次
        </span>
        <span
          v-if="app.teacher.avg_rating != null"
          class="text-amber-600"
        >
          评分 {{ app.teacher.avg_rating }} ★
        </span>
      </div>
      <div
        v-if="app.teacher.phone || app.teacher.wechat_id"
        class="flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-gray-100 pt-1"
      >
        <template v-if="app.teacher.phone">
          <span class="text-gray-600">手机 {{ app.teacher.phone }}</span>
          <button
            class="text-brand-800"
            @click.stop="copyContact(app.teacher.phone, '手机号已复制')"
          >
            复制
          </button>
        </template>
        <template v-if="app.teacher.wechat_id">
          <span class="text-gray-600">微信 {{ app.teacher.wechat_id }}</span>
          <button
            class="text-brand-800"
            @click.stop="copyContact(app.teacher.wechat_id, '微信号已复制')"
          >
            复制
          </button>
        </template>
      </div>
    </div>

    <div class="text-xs text-gray-400 mb-2">
      <div class="break-all">
        订单编号：<span class="text-gray-600 font-medium">{{ app.raw_order_id || `#${app.order_id}` }}</span>
      </div>
      投递于 {{ formatDateTime(app.applied_at) }}
      <div
        v-if="app.proposed_price != null"
        class="mt-1 text-orange-600 font-medium"
      >
        教员报价：¥{{ app.proposed_price }}/次
      </div>
    </div>

    <div
      v-if="app.status === 'pending'"
      class="grid grid-cols-2 gap-2"
    >
      <button
        class="header-gradient text-white rounded-lg py-2 text-xs font-semibold"
        @click.stop="emit('shortlist', app.id)"
      >
        加入候选队列
      </button>
      <button
        class="bg-red-50 text-red-500 rounded-lg py-2 text-xs font-semibold"
        @click.stop="emit('reject', app.id)"
      >
        拒绝
      </button>
    </div>

    <div
      v-if="app.status === 'shortlisted'"
      class="space-y-2"
    >
      <button
        class="w-full bg-brand-800 text-white rounded-lg py-2 text-xs font-semibold"
        @click.stop="emit('confirm-deposit', app.id)"
      >
        确认定金
      </button>
      <button
        class="w-full bg-red-50 text-red-500 rounded-lg py-2 text-xs font-semibold"
        @click.stop="emit('reject', app.id)"
      >
        拒绝
      </button>
    </div>

    <button
      v-if="app.status === 'deposit_paid'"
      class="w-full bg-emerald-600 text-white rounded-lg py-2 text-xs font-semibold mb-2"
      @click.stop="emit('start-trial', app.id)"
    >
      开始试课
    </button>

    <div
      v-if="app.status === 'trial_in_progress'"
      class="space-y-2"
    >
      <div class="text-xs text-emerald-700 bg-emerald-50 rounded-lg p-2">
        当前教员正在试课，可查看家长联系方式
      </div>
      <div class="grid grid-cols-2 gap-2">
        <button
          class="bg-red-50 text-red-500 rounded-lg py-2 text-xs font-semibold"
          @click.stop="emit('trial-failed', app.id)"
        >
          试课失败
        </button>
        <button
          class="bg-green-600 text-white rounded-lg py-2 text-xs font-semibold"
          @click.stop="emit('confirm-balance', app.id)"
        >
          确认尾款
        </button>
      </div>
    </div>

    <button
      v-if="['deposit_paid', 'trial_in_progress', 'balance_paid'].includes(app.status)"
      class="w-full bg-orange-50 text-orange-600 rounded-lg py-2 text-xs font-semibold mt-2"
      @click.stop="emit('forfeit', app.id)"
    >
      没收定金（教员违约）
    </button>

    <div
      v-if="app.status === 'balance_paid'"
      class="space-y-2"
    >
      <div class="text-xs text-green-600 bg-green-50 rounded-lg p-2">
        教员已付全款，可解锁联系方式
      </div>
      <button
        class="w-full bg-gray-900 text-white rounded-lg py-2 text-xs font-semibold"
        @click.stop="emit('complete', app.id)"
      >
        确认完成
      </button>
    </div>

    <button
      v-if="app.status === 'completed'"
      class="w-full bg-amber-50 text-amber-600 rounded-lg py-2 text-xs font-semibold mt-2"
      @click.stop="emit('review', app)"
    >
      {{ app.teacher?.avg_rating != null ? "修改评价" : "评价教员" }}
    </button>

    <button
      v-if="app.status === 'completed' && app.teacher"
      class="w-full bg-sky-50 text-sky-700 rounded-lg py-2 text-xs font-semibold mt-2"
      @click.stop="openScorecard"
    >
      查看成绩单（转发给家长） →
    </button>

    <button
      v-if="app.status === 'rejected' && canRestore"
      class="w-full border border-slate-200 bg-white text-slate-600 rounded-lg py-2 text-xs font-semibold mt-2"
      @click.stop="emit('restore', app.id)"
    >
      恢复待审核（误拒绝回退）
    </button>
  </div>
</template>
