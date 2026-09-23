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
    } catch (e) {
      (window as unknown as Record<string, unknown>).__matchErr = String(e);
      loadFailed.value = true;
    } finally {
      loading.value = false;
    }
  },
  { immediate: true }
);

const isEmpty = computed(() => !loading.value && !loadFailed.value && teachers.value.length === 0);

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
        <div class="text-base font-semibold text-slate-950">找教员</div>
        <span class="text-xs text-slate-400">{{ subject }}</span>
      </div>
      <div class="mb-3 text-xs leading-5 text-slate-400">
        按科目/年级/距离/信用综合排序。邀约后教员会收到站内通知，确认后即可投递；联系方式在教员投递后可见。
      </div>

      <div v-if="loading" class="flex justify-center py-8">
        <van-loading type="spinner" color="#334155" />
      </div>
      <div v-else-if="loadFailed" class="py-8 text-center text-sm text-slate-400">
        加载失败，请关闭后重试
      </div>
      <div v-else-if="isEmpty" class="py-8 text-center text-sm text-slate-400">
        暂无匹配教员。可以到教员橱窗提升订单曝光，或稍后再试。
      </div>
      <div v-else class="space-y-2 pb-2">
        <div
          v-for="item in teachers"
          :key="item.teacher_id"
          class="flex items-center justify-between gap-3 rounded-xl border border-slate-100 bg-white p-3"
        >
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-1.5">
              <span class="text-sm font-semibold text-slate-900">{{ item.name }}</span>
              <span
                v-if="item.subject_matched"
                class="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-600"
              >科目匹配</span>
              <span
                v-if="item.violation_count > 0"
                class="rounded-full bg-red-50 px-1.5 py-0.5 text-[10px] text-red-500"
              >违约 {{ item.violation_count }}</span>
            </div>
            <div class="mt-0.5 truncate text-xs text-slate-500">
              {{ [item.school, item.major, item.grade].filter(Boolean).join(" · ") || "—" }}
            </div>
            <div class="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-slate-400">
              <span v-if="item.home_area">{{ item.home_area }}</span>
              <span v-if="item.distance_km != null">距 {{ item.distance_km }} km</span>
              <span>成交 {{ item.completed_count }}</span>
              <span v-if="item.avg_rating != null">评分 {{ item.avg_rating }} ★</span>
            </div>
          </div>
          <button
            class="shrink-0 rounded-lg bg-slate-700 px-3 py-1.5 text-xs font-medium text-white disabled:bg-slate-100 disabled:text-slate-400"
            :disabled="invitedIds.has(item.teacher_id)"
            @click="invite(item)"
          >
            {{ invitedIds.has(item.teacher_id) ? "已邀约" : "邀约" }}
          </button>
        </div>
      </div>
    </div>
  </van-popup>
</template>
