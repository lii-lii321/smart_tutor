<script setup lang="ts">
import { computed } from "vue";
import type { TeacherSummary } from "@/api/types";
import AppBadge from "@/components/ui/AppBadge.vue";

/**
 * 教员画像卡（Batch 04）：回答"这个教员适不适合这个订单"。
 * 只展示 TeacherSummary 里真实存在的字段——后端没有的画像维度
 * （授课区域/可授时间等在简历里，摘要接口不下发）就不显示，不编造。
 * 联系方式（phone/wechat_id）仅 B 端投递接口下发，C 端不会传。
 */
const props = withDefaults(
  defineProps<{
    teacher: TeacherSummary;
    compact?: boolean;
  }>(),
  { compact: false },
);

const badgeTone = computed(() => {
  if (props.teacher.is_985 && props.teacher.is_211) return "success" as const;
  if (props.teacher.is_985 || props.teacher.is_211 || props.teacher.is_double_first_class) return "brand" as const;
  return "neutral" as const;
});
const badgeLabel = computed(() => {
  const t = props.teacher;
  if (t.is_985 && t.is_211) return "985/211";
  if (t.is_985) return "985";
  if (t.is_211) return "211";
  if (t.is_double_first_class) return "双一流";
  return "";
});

const ratingText = computed(() =>
  props.teacher.avg_rating != null ? props.teacher.avg_rating.toFixed(1) : null
);
</script>

<template>
  <div class="min-w-0">
    <div class="flex flex-wrap items-center gap-1.5">
      <span class="text-sm font-bold text-primary">{{ teacher.name }}</span>
      <AppBadge v-if="badgeLabel" :tone="badgeTone" size="sm">{{ badgeLabel }}</AppBadge>
    </div>
    <div class="mt-0.5 truncate text-xs text-muted">
      {{ [teacher.school, teacher.major, teacher.grade].filter(Boolean).join(" · ") || "院校信息未填写" }}
    </div>

    <!-- 真实历史数据（投递接口批量聚合下发；没有就不显示） -->
    <div
      v-if="!compact"
      class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-secondary"
    >
      <span v-if="teacher.completed_count !== undefined">成交 <b class="text-success">{{ teacher.completed_count }}</b> 次</span>
      <span v-if="teacher.violation_count !== undefined && teacher.violation_count > 0" class="text-danger">
        违约 <b>{{ teacher.violation_count }}</b> 次
      </span>
      <span v-if="ratingText">评分 <b class="text-primary">{{ ratingText }}</b></span>
    </div>

    <!-- B 端联系方式（仅投递接口下发；教员端不会传，缺省不显示） -->
    <div
      v-if="!compact && (teacher.phone || teacher.wechat_id)"
      class="mt-1.5 truncate text-[11px] text-muted"
    >
      {{ [teacher.phone, teacher.wechat_id].filter(Boolean).join(" · ") }}
    </div>
  </div>
</template>
