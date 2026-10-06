<script setup lang="ts">
/**
 * 投递卡片（自 ApplicationsReview.vue 拆出）：
 * 教员信息 + 状态徽标 + 按状态渲染的动作按钮。纯展示组件，动作通过事件交回父级编排。
 */
import { copyContact } from "@/utils/clipboard";
import { formatDateTime } from "@/utils/format";
import type { ApplicationItem } from "@/api/types";
import { APPLICATION_STATUS_LABELS } from "@/constants/applicationStatus";
import { applicationTone } from "@/constants/statusTone";
import ApplicationStageTrail from "@/components/business/ApplicationStageTrail.vue";
import AppButton from "@/components/ui/AppButton.vue";

const props = defineProps<{
  app: ApplicationItem;
  /** 仅招聘中的订单可恢复误拒投递（终态订单的落选不可回退） */
  canRestore: boolean;
  /** 本卡动作 in-flight：禁用卡片全部按钮，防止连点重复提交 */
  busy?: boolean;
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
          class="px-1.5 py-0.5 rounded-full text-caption bg-surface-soft text-secondary shrink-0"
        >
          985
        </span>
        <span
          v-if="app.teacher?.is_211"
          class="px-1.5 py-0.5 rounded-full text-caption bg-surface-soft text-secondary shrink-0"
        >
          211
        </span>
        <span
          v-if="app.teacher?.is_double_first_class"
          class="px-1.5 py-0.5 rounded-full text-caption bg-surface-soft text-secondary shrink-0"
        >
          双一流
        </span>
        <span
          v-if="app.teacher?.is_985_211 && !app.teacher?.is_985 && !app.teacher?.is_211"
          class="px-1.5 py-0.5 rounded-full text-caption bg-surface-soft text-secondary shrink-0"
        >
          985/211
        </span>
      </div>
      <span
        class="shrink-0 whitespace-nowrap rounded-full px-1.5 py-0.5 text-caption leading-4"
        :class="applicationTone(app.status).chip"
      >
        {{ APPLICATION_STATUS_LABELS[app.status] || app.status }}
      </span>
    </div>

    <!-- 投递流转横条：放在任何动作按钮之前，让中介先看到"卡在哪一环"，
         再决定点哪个按钮；步骤映射复用 timeline.ts 的唯一口径 -->
    <div class="mb-2">
      <ApplicationStageTrail :application="app" />
    </div>

    <div
      v-if="app.teacher"
      class="text-xs text-secondary bg-surface-soft rounded-lg p-2 mb-2 space-y-1"
    >
      <div class="font-medium text-primary">
        {{ app.teacher.school }}
        <span
          v-if="app.teacher.major"
          class="text-muted"
        > · {{ app.teacher.major }}</span>
        <span
          v-if="app.teacher.grade"
          class="text-muted"
        > · {{ app.teacher.grade }}</span>
      </div>
      <div class="text-secondary">
        {{ app.teacher.gender === 'female' ? '女' : '男' }}
        <span v-if="app.teacher.highlights"> · {{ app.teacher.highlights }}</span>
      </div>
      <div class="flex flex-wrap items-center gap-2 pt-0.5">
        <span class="text-success-deep">成交 {{ app.teacher.completed_count ?? 0 }} 单</span>
        <span
          :class="(app.teacher.violation_count ?? 0) > 0 ? 'text-danger-deep' : 'text-muted'"
        >
          违约 {{ app.teacher.violation_count ?? 0 }} 次
        </span>
        <span
          v-if="app.teacher.avg_rating != null"
          class="text-warning-deep"
        >
          评分 {{ app.teacher.avg_rating }} ★
        </span>
      </div>
      <div
        v-if="app.teacher.phone || app.teacher.wechat_id"
        class="flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-default pt-1"
      >
        <template v-if="app.teacher.phone">
          <span class="text-secondary">手机 {{ app.teacher.phone }}</span>
          <button
            class="text-brand-800 disabled:opacity-50"
            :disabled="busy"
            @click.stop="copyContact(app.teacher.phone, '手机号已复制')"
          >
            复制
          </button>
        </template>
        <template v-if="app.teacher.wechat_id">
          <span class="text-secondary">微信 {{ app.teacher.wechat_id }}</span>
          <button
            class="text-brand-800 disabled:opacity-50"
            :disabled="busy"
            @click.stop="copyContact(app.teacher.wechat_id, '微信号已复制')"
          >
            复制
          </button>
        </template>
      </div>
    </div>

    <div class="text-xs text-muted mb-2">
      <div class="break-all">
        订单编号：<span class="text-secondary font-medium">{{ app.raw_order_id || `#${app.order_id}` }}</span>
      </div>
      投递于 {{ formatDateTime(app.applied_at) }}
      <div
        v-if="app.proposed_price != null"
        class="mt-1 text-warning-deep font-medium"
      >
        教员报价：¥{{ app.proposed_price }}/次
      </div>
    </div>

    <div
      v-if="app.status === 'pending'"
      class="grid grid-cols-2 gap-2"
    >
      <AppButton
        size="sm"
        :disabled="busy"
        @click.stop="emit('shortlist', app.id)"
      >
        加入候选队列
      </AppButton>
      <AppButton
        size="sm"
        variant="secondary"
        :disabled="busy"
        @click.stop="emit('reject', app.id)"
      >
        拒绝
      </AppButton>
    </div>

    <div
      v-if="app.status === 'shortlisted'"
      class="space-y-2"
    >
      <AppButton
        block
        size="sm"
        :disabled="busy"
        @click.stop="emit('confirm-deposit', app.id)"
      >
        确认定金
      </AppButton>
      <AppButton
        block
        size="sm"
        variant="secondary"
        :disabled="busy"
        @click.stop="emit('reject', app.id)"
      >
        拒绝
      </AppButton>
    </div>

    <AppButton
      v-if="app.status === 'deposit_paid'"
      block
      size="sm"
      class="mb-2"
      :disabled="busy"
      @click.stop="emit('start-trial', app.id)"
    >
      开始试课
    </AppButton>

    <div
      v-if="app.status === 'trial_in_progress'"
      class="space-y-2"
    >
      <div class="text-xs text-success-deep bg-success-soft rounded-lg p-2">
        当前教员正在试课，可查看家长联系方式
      </div>
      <div class="grid grid-cols-2 gap-2">
        <AppButton
          size="sm"
          variant="danger-soft"
          :disabled="busy"
          @click.stop="emit('trial-failed', app.id)"
        >
          试课失败
        </AppButton>
        <AppButton
          size="sm"
          :disabled="busy"
          @click.stop="emit('confirm-balance', app.id)"
        >
          确认尾款
        </AppButton>
      </div>
    </div>

    <AppButton
      v-if="['deposit_paid', 'trial_in_progress', 'balance_paid'].includes(app.status)"
      block
      size="sm"
      variant="danger-soft"
      class="mt-2"
      :disabled="busy"
      @click.stop="emit('forfeit', app.id)"
    >
      没收定金（教员违约）
    </AppButton>

    <div
      v-if="app.status === 'balance_paid'"
      class="space-y-2"
    >
      <div class="text-xs text-success-deep bg-success-soft rounded-lg p-2">
        教员已付全款，可解锁联系方式
      </div>
      <AppButton
        block
        size="sm"
        :disabled="busy"
        @click.stop="emit('complete', app.id)"
      >
        确认完成
      </AppButton>
    </div>

    <AppButton
      v-if="app.status === 'completed'"
      block
      size="sm"
      variant="warning-soft"
      class="mt-2"
      :disabled="busy"
      @click.stop="emit('review', app)"
    >
      {{ app.teacher?.avg_rating != null ? "修改评价" : "评价教员" }}
    </AppButton>

    <AppButton
      v-if="app.status === 'completed' && app.teacher"
      block
      size="sm"
      variant="info-soft"
      class="mt-2"
      :disabled="busy"
      @click.stop="openScorecard"
    >
      查看成绩单（转发给家长） →
    </AppButton>

    <button
      v-if="app.status === 'rejected' && canRestore"
      class="w-full border border-default bg-white text-secondary rounded-lg py-2 text-xs font-semibold mt-2 disabled:opacity-50"
      :disabled="busy"
      @click.stop="emit('restore', app.id)"
    >
      恢复待审核（误拒绝回退）
    </button>
  </div>
</template>
