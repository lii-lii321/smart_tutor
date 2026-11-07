<script setup lang="ts">
import { computed } from "vue";
import { stageOptions } from "@/composables/useBoardFilters";
import AppButton from "@/components/ui/AppButton.vue";

/**
 * 筛选底部弹层：学段/学科/城市/排序四组 chips。
 * 全部状态由父层通过 v-model 传入（useBoardFilters 的 ref），本组件无本地状态。
 */
const props = defineProps<{
  visible: boolean;
  stage: string;
  subjects: string[];
  city: string;
  cityLabel: string;
  cityOptions: string[];
  sort: string;
  sortOptions: Array<{ value: string; label: string }>;
  availableSubjects: string[];
}>();

const emit = defineEmits<{
  (e: "update:visible", value: boolean): void;
  (e: "update:stage", value: string): void;
  (e: "update:subjects", value: string[]): void;
  (e: "update:city", value: string): void;
  (e: "update:sort", value: string): void;
  (e: "reset"): void;
}>();

const show = computed({
  get: () => props.visible,
  set: (value: boolean) => emit("update:visible", value),
});

function toggleSubject(subject: string) {
  const next = props.subjects.includes(subject)
    ? props.subjects.filter((s) => s !== subject)
    : [...props.subjects, subject];
  emit("update:subjects", next);
}
</script>

<template>
  <van-popup v-model:show="show" position="bottom" round class="max-h-[75vh]">
    <div class="flex flex-col gap-4 px-4 pb-[calc(16px+env(safe-area-inset-bottom))] pt-4">
      <div>
        <p class="mb-2 text-xs font-medium text-secondary">学段</p>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="opt in stageOptions"
            :key="opt.value"
            type="button"
            class="rounded-full border px-3 py-1.5 text-xs"
            :class="stage === opt.value ? 'border-brand-800 bg-brand-800 text-white' : 'border-default bg-surface text-secondary'"
            @click="emit('update:stage', opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>

      <div>
        <p class="mb-2 text-xs font-medium text-secondary">学科（可多选）</p>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="subject in availableSubjects"
            :key="subject"
            type="button"
            class="rounded-full border px-3 py-1.5 text-xs"
            :class="subjects.includes(subject) ? 'border-brand-800 bg-brand-800 text-white' : 'border-default bg-surface text-secondary'"
            @click="toggleSubject(subject)"
          >
            {{ subject }}
          </button>
        </div>
      </div>

      <div>
        <p class="mb-2 text-xs font-medium text-secondary">城市（当前：{{ cityLabel }}）</p>
        <!-- 单行横向滑动条：全国 300+ 城市禁止摊开换行（曾把弹层撑成整屏）；
             首位常驻「全部城市」复位项，滚动条带右缘渐隐提示还有更多 -->
        <div class="relative">
          <div class="flex gap-2 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            <button
              type="button"
              class="flex-none whitespace-nowrap rounded-full border px-3 py-1.5 text-xs"
              :class="city === 'all' ? 'border-brand-800 bg-brand-800 text-white' : 'border-default bg-surface text-secondary'"
              @click="emit('update:city', 'all')"
            >
              全部城市
            </button>
            <button
              v-for="c in cityOptions"
              :key="c"
              type="button"
              class="flex-none whitespace-nowrap rounded-full border px-3 py-1.5 text-xs"
              :class="city === c ? 'border-brand-800 bg-brand-800 text-white' : 'border-default bg-surface text-secondary'"
              @click="emit('update:city', c)"
            >
              {{ c }}
            </button>
          </div>
          <div
            class="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-white to-transparent"
            aria-hidden="true"
          />
        </div>
      </div>

      <div>
        <p class="mb-2 text-xs font-medium text-secondary">排序</p>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="opt in sortOptions"
            :key="opt.value"
            type="button"
            class="rounded-full border px-3 py-1.5 text-xs"
            :class="sort === opt.value ? 'border-brand-800 bg-brand-800 text-white' : 'border-default bg-surface text-secondary'"
            @click="emit('update:sort', opt.value)"
          >
            {{ opt.label }}
          </button>
        </div>
      </div>

      <div class="flex gap-3">
        <AppButton variant="secondary" block @click="emit('reset')">重置</AppButton>
        <AppButton block @click="emit('update:visible', false)">完成</AppButton>
      </div>
    </div>
  </van-popup>
</template>
