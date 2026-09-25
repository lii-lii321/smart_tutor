<script setup lang="ts">
/**
 * 工作台待办卡（Batch 04）：纯展示组件——只渲染传入的 ViewModel，
 * 不请求 API、不算业务状态、不算金额、不判断权限、不定义 OrderStatus。
 */
export interface TodoViewModel {
  key: string;
  title: string;
  description?: string;
  count?: number;
  status?: "normal" | "warning" | "danger";
  actionLabel?: string;
}

withDefaults(defineProps<{ todos: TodoViewModel[]; title?: string }>(), {
  title: "今日待办",
});

const emit = defineEmits<{ (e: "open", todo: TodoViewModel): void }>();

const STATUS_TEXT_CLASS: Record<NonNullable<TodoViewModel["status"]>, string> = {
  normal: "text-brand-800",
  warning: "text-warning",
  danger: "text-danger",
};
</script>

<template>
  <div class="rounded-2xl border border-default bg-surface p-4 shadow-card">
    <h3 class="text-sm font-bold text-primary">{{ title }}</h3>
    <div
      v-if="todos.length"
      class="mt-1 divide-y divide-slate-100"
    >
      <button
        v-for="todo in todos"
        :key="todo.key"
        class="flex w-full items-center gap-3 py-3 text-left"
        @click="emit('open', todo)"
      >
        <span
          v-if="todo.count !== undefined"
          class="price-highlight w-10 shrink-0 text-center text-xl font-bold"
          :class="todo.count > 0 ? STATUS_TEXT_CLASS[todo.status ?? 'normal'] : 'text-slate-300'"
        >
          {{ todo.count > 0 ? todo.count : "✓" }}
        </span>
        <span class="min-w-0 flex-1">
          <span class="block text-sm font-medium text-primary">{{ todo.title }}</span>
          <span v-if="todo.description" class="block text-xs text-muted">{{ todo.description }}</span>
        </span>
        <span
          v-if="todo.actionLabel"
          class="shrink-0 text-xs font-medium text-brand-700"
        >{{ todo.actionLabel }} →</span>
        <van-icon
          v-else
          name="arrow"
          size="14"
          color="#94a3b8"
        />
      </button>
    </div>
    <p
      v-else
      class="py-6 text-center text-sm text-muted"
    >
      暂无待办，今天可以轻松一点
    </p>
  </div>
</template>
