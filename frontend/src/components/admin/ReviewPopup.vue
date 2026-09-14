<script setup lang="ts">
/** 评价教员弹层（自 ApplicationsReview.vue 拆出）：一单一评，可修改。 */
import { ref, watch } from "vue";
import type { ApplicationItem } from "@/api/types";
import { applicationsApi } from "@/api/applications";
import { getApiErrorMessage } from "@/utils/apiError";
import { showSuccessToast, showToast } from "vant";

const show = defineModel<boolean>("show", { default: false });

const props = defineProps<{
  app: ApplicationItem | null;
}>();

const emit = defineEmits<{ (e: "submitted"): void }>();

const rating = ref(5);
const comment = ref("");
const submitting = ref(false);

watch(show, (visible) => {
  if (!visible || !props.app) return;
  const avg = props.app.teacher?.avg_rating;
  rating.value = avg != null ? Math.round(avg) : 5;
  comment.value = "";
});

async function submitReview() {
  if (!props.app) return;
  submitting.value = true;
  try {
    await applicationsApi.review(props.app.id, rating.value, comment.value.trim() || undefined);
    showSuccessToast("评价已提交");
    show.value = false;
    emit("submitted");
  } catch (e) {
    showToast(getApiErrorMessage(e, "提交失败"));
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
    close-on-click-overlay
  >
    <div
      v-if="app"
      class="p-5"
    >
      <div class="mb-1 text-lg font-bold">
        评价教员：{{ app.teacher?.name || `#${app.teacher_id}` }}
      </div>
      <div class="mb-4 text-xs text-gray-400">
        评价会进入教员信用档案并影响推荐排序，一单一条，可修改
      </div>
      <div class="flex items-center justify-center py-2">
        <van-rate
          v-model="rating"
          :size="30"
          color="#f59e0b"
        />
      </div>
      <van-field
        v-model="comment"
        label="评语"
        type="textarea"
        rows="2"
        autosize
        maxlength="255"
        show-word-limit
        placeholder="如：守时负责，家长反馈很好"
      />
      <button
        class="mt-4 w-full header-gradient text-white rounded-xl py-3 text-sm font-semibold disabled:opacity-50"
        :disabled="submitting"
        @click="submitReview"
      >
        {{ submitting ? "提交中..." : "提交评价" }}
      </button>
    </div>
  </van-popup>
</template>
