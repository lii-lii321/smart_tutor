<script setup lang="ts">
/**
 * 找教员弹层（一期·订单找教员）：为招聘中订单展示匹配教员（评分排序），
 * 中介可逐个"邀约"——教员收到站内通知后自行投递，联系方式不提前暴露。
 */
import { computed, ref, watch } from "vue";
import { ordersApi } from "@/api/orders";
import type { RecommendedTeacher } from "@/api/types";
import { getApiErrorMessage } from "@/utils/apiError";
import { appConfirm } from "@/composables/appConfirm";
import { buildRecommendationExplanation } from "@/components/business/recommendation";
import RecommendationExplainCard from "@/components/business/RecommendationExplainCard.vue";
import { showToast } from "vant";

const props = defineProps<{
  show: boolean;
  orderId: number | null;
  subject: string;
}>();

const emit = defineEmits<{
  (e: "update:show", value: boolean): void;
  (e: "invited"): void;
}>();

const loading = ref(false);
const teachers = ref<RecommendedTeacher[]>([]);
const invitedIds = ref<Set<number>>(new Set());
const loadFailed = ref(false);

watch(
  () => [props.show, props.orderId] as const,
  async ([visible]) => {
    const orderId = props.orderId;
    if (!visible || orderId == null) return;
    loading.value = true;
    loadFailed.value = false;
    teachers.value = [];
    invitedIds.value = new Set();
    try {
      teachers.value = await ordersApi.recommendedTeachers(orderId);
    } catch {
      loadFailed.value = true;
    } finally {
      loading.value = false;
    }
  },
  { immediate: true }
);

const isEmpty = computed(() => !loading.value && !loadFailed.value && teachers.value.length === 0);

// 行视图 = 候选 + 解释（OB-7）：breakdown 来自接口，缺失时 explanation 为 null、卡片不渲染
const matchRows = computed(() =>
  teachers.value.map((item) => ({ item, explanation: buildRecommendationExplanation(item) }))
);

async function invite(teacher: RecommendedTeacher) {
  if (props.orderId == null) return;
  const ok = await appConfirm({
    title: "邀约教员？",
    message: `将向「${teacher.name}」发送「${props.subject}」订单邀约，教员确认后即可投递。`,
    confirmText: "发送邀约",
  });
  if (!ok) return;
  try {
    await ordersApi.inviteTeacher(props.orderId, teacher.teacher_id);
    invitedIds.value = new Set([...invitedIds.value, teacher.teacher_id]);
    showToast("已发送邀约，教员可在消息中心查看");
    emit("invited");
  } catch (e) {
    showToast(getApiErrorMessage(e, "邀约失败"));
  }
}
</script>

<template>
  <van-popup :show="show" position="bottom" round @update:show="(v: boolean) => emit('update:show', v)">
    <div class="max-h-[75vh] overflow-y-auto p-4">
      <div class="mb-1 flex items-center justify-between">
        <div class="text-base font-semibold text-primary">找教员</div>
        <span class="text-xs text-muted">{{ subject }}</span>
      </div>
      <div class="mb-3 text-xs leading-5 text-muted">
        匹配度 = 科目 45% + 年级 20% + 信用 20% + 距离 15%，由教员简历与订单要求实时算出。
        邀约后教员会收到站内通知，确认后即可投递；联系方式在教员投递后可见。
      </div>

      <div v-if="loading" class="flex justify-center py-8">
        <van-loading type="spinner" color="#334155" />
      </div>
      <div v-else-if="loadFailed" class="py-8 text-center text-sm text-muted">
        匹配教员加载失败：网络或服务暂时不可用，请关闭后重新打开
      </div>
      <div v-else-if="isEmpty" class="py-8 text-center text-sm text-muted">
        暂无匹配教员。可以到教员橱窗提升订单曝光，或稍后再试。
      </div>
      <div v-else class="space-y-2 pb-2">
        <div
          v-for="row in matchRows"
          :key="row.item.teacher_id"
          class="space-y-2 rounded-xl border border-default bg-white p-3"
        >
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-1.5">
                <span class="text-sm font-semibold text-primary">{{ row.item.name }}</span>
                <span
                  v-if="row.item.subject_matched"
                  class="rounded-full bg-success-soft px-1.5 py-0.5 text-caption text-success-deep"
                >科目匹配</span>
                <span
                  v-if="row.item.violation_count > 0"
                  class="rounded-full bg-danger-soft px-1.5 py-0.5 text-caption text-danger-deep"
                >违约 {{ row.item.violation_count }}</span>
              </div>
              <div class="mt-0.5 truncate text-xs text-secondary">
                {{ [row.item.school, row.item.major, row.item.grade].filter(Boolean).join(" · ") || "—" }}
              </div>
              <div class="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-muted">
                <span v-if="row.item.home_area">{{ row.item.home_area }}</span>
                <span v-if="row.item.distance_km != null">距 {{ row.item.distance_km }} km</span>
                <span>成交 {{ row.item.completed_count }}</span>
                <span v-if="row.item.avg_rating != null">评分 {{ row.item.avg_rating }} ★</span>
              </div>
            </div>
            <button
              class="shrink-0 rounded-lg bg-brand-800 px-3 py-1.5 text-xs font-medium text-white disabled:bg-surface-soft disabled:text-muted"
              :disabled="invitedIds.has(row.item.teacher_id)"
              @click="invite(row.item)"
            >
              {{ invitedIds.has(row.item.teacher_id) ? "已邀约" : "邀约" }}
            </button>
          </div>
          <!-- OB-7：为什么推荐 TA——四维分与权重来自接口，前端不复算 -->
          <RecommendationExplainCard
            v-if="row.explanation"
            :explanation="row.explanation"
            compact
            heading="推荐理由"
          />
        </div>
      </div>
    </div>
  </van-popup>
</template>
