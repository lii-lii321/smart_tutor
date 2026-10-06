<script setup lang="ts">
import { formatDateTime } from "@/utils/format";
import { getApiErrorMessage } from "@/utils/apiError";
import { copyContact } from "@/utils/clipboard";
import type { ApplicationItem } from "@/api/types";
import { tenantsApi } from "@/api/tenants";
import { APPLICATION_STATUS_LABELS } from "@/constants/applicationStatus";
import { applicationTone } from "@/constants/statusTone";
import { showToast, showSuccessToast } from "vant";
import { useAsyncAction } from "@/composables/useAsyncAction";
import { appConfirm } from "@/composables/appConfirm";
import ApplicationStageTrail from "@/components/business/ApplicationStageTrail.vue";

defineProps<{
  application: ApplicationItem | null;
  show: boolean;
}>();

const emit = defineEmits<{
  (e: "update:show", value: boolean): void;
  /** 拉黑成功后通知父级刷新投递列表 */
  (e: "blacklisted"): void;
}>();

function close() {
  emit("update:show", false);
}

const [quickBlacklist, blacklisting] = useAsyncAction(async (app: ApplicationItem) => {
  const ok = await appConfirm({
    title: "拉黑该教员？",
    message: `拉黑「${app.teacher?.name || `#${app.teacher_id}`}」后：其待审投递将被拒绝，且无法再投递本中介订单（仅对本中介生效）。`,
    confirmText: "确认拉黑",
    danger: true,
  });
  if (!ok) return;
  try {
    await tenantsApi.blacklist(app.teacher_id, "审核页快捷拉黑");
    showSuccessToast("已拉黑");
    close();
    emit("blacklisted");
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
});
</script>

<template>
  <van-popup
    :show="show"
    position="bottom"
    round
    close-on-click-overlay
    @update:show="(value: boolean) => emit('update:show', value)"
  >
    <div v-if="application" class="max-h-[78vh] overflow-y-auto p-5">
      <div class="mb-4 flex items-start justify-between gap-3">
        <div>
          <div class="text-xl font-bold break-all">
            {{ application.teacher?.name || `教员 #${application.teacher_id}` }}
          </div>
          <div class="mt-1 text-xs text-muted">投递详情</div>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <span
            class="rounded-full px-2 py-1 text-xs"
            :class="applicationTone(application.status).chip"
          >
            {{ application ? APPLICATION_STATUS_LABELS[application.status] || application.status : "" }}
          </span>
          <button
            class="flex h-8 w-8 items-center justify-center rounded-lg bg-surface-soft text-secondary"
            aria-label="关闭"
            @click="close()"
          >
            <van-icon name="cross" />
          </button>
        </div>
      </div>

      <div class="mb-3 rounded-xl bg-surface-soft p-3 text-sm text-secondary">
        <div class="break-all">订单编号：<span class="font-semibold">{{ application.raw_order_id || `#${application.order_id}` }}</span></div>
      </div>

      <!-- 进度时间线：复用全站唯一投递步骤映射（与审核卡/我的投递同源） -->
      <div class="mb-3 rounded-xl border border-default p-3">
        <div class="mb-2 text-sm font-semibold text-primary">进度时间线</div>
        <ApplicationStageTrail :application="application" />
      </div>

      <div v-if="application.teacher" class="space-y-3 rounded-xl bg-surface-soft p-3 text-sm text-secondary">
        <div><span class="text-muted">学校：</span>{{ application.teacher.school || "未填写" }}</div>
        <div><span class="text-muted">专业：</span>{{ application.teacher.major || "未填写" }}</div>
        <div><span class="text-muted">年级：</span>{{ application.teacher.grade || "未填写" }}</div>
        <div><span class="text-muted">性别：</span>{{ application.teacher.gender === "female" ? "女" : "男" }}</div>
        <div><span class="text-muted">个人优势：</span>{{ application.teacher.highlights || "未填写" }}</div>
        <div v-if="application.teacher.phone || application.teacher.wechat_id" class="space-y-1 border-t border-default pt-2">
          <div v-if="application.teacher.phone" class="flex items-center justify-between gap-2">
            <span><span class="text-muted">手机：</span>{{ application.teacher.phone }}</span>
            <button
              class="text-xs text-brand-800"
              @click="copyContact(application.teacher.phone, '手机号已复制')"
            >
              复制
            </button>
          </div>
          <div v-if="application.teacher.wechat_id" class="flex items-center justify-between gap-2">
            <span><span class="text-muted">微信：</span>{{ application.teacher.wechat_id }}</span>
            <button
              class="text-xs text-brand-800"
              @click="copyContact(application.teacher.wechat_id, '微信号已复制')"
            >
              复制
            </button>
          </div>
          <div class="text-xs text-muted">确认候选后可线下联系教员收取定金</div>
        </div>
      </div>

      <button
        class="mt-3 w-full rounded-lg bg-danger-soft py-2 text-xs font-semibold text-danger-deep disabled:opacity-50"
        :disabled="blacklisting"
        @click="quickBlacklist(application)"
      >
        {{ blacklisting ? "处理中..." : "拉黑该教员（仅对本中介生效）" }}
      </button>

      <div v-if="application.resume" class="mt-3 rounded-xl border border-default p-3">
        <div class="mb-2 flex items-center justify-between">
          <span class="text-sm font-semibold text-primary">投递简历</span>
          <span class="text-xs text-muted break-all">{{ application.resume.title }}</span>
        </div>
        <div class="space-y-2 text-sm text-secondary">
          <div>
            <span class="text-muted">可授科目：</span>{{ application.resume.teaching_subjects || "未填写" }}
          </div>
          <div>
            <span class="text-muted">可授年级：</span>{{ application.resume.teaching_grades || "未填写" }}
          </div>
          <div>
            <span class="text-muted">家教经历：</span>{{ application.resume.experience || "未填写" }}
          </div>
          <div v-if="application.resume.strengths">
            <span class="text-muted">个人优势：</span>{{ application.resume.strengths }}
          </div>
          <div v-if="application.resume.availability">
            <span class="text-muted">可授课时间：</span>{{ application.resume.availability }}
          </div>
          <div v-if="application.resume.expected_rate">
            <span class="text-muted">期望课酬：</span>{{ application.resume.expected_rate }}
          </div>
        </div>
      </div>
      <div v-else class="mt-3 rounded-xl bg-surface-soft p-3 text-xs text-muted">
        该教员投递时未选择简历（使用默认资料）
      </div>

      <div class="mt-3 space-y-1 text-sm text-secondary">
        <div>投递时间：{{ formatDateTime(application.applied_at) }}</div>
        <div v-if="application.proposed_price != null">教员报价：¥{{ application.proposed_price }}/次</div>
      </div>
    </div>
  </van-popup>
</template>
