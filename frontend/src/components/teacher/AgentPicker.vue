<script setup lang="ts">
import { ref, watch } from "vue";

/**
 * 中介切换弹层（自 Board.vue 拆出，P1-1）：
 * 已存中介列表（切换/移除）+ 添加新中介表单。
 * 添加动作交由父级执行（涉及加载橱窗）；agents 变化（添加成功）后自动收起表单。
 */
const props = defineProps<{
  show: boolean;
  agents: string[];
  currentCode: string;
  tenantName: string;
  addError: string;
}>();

const emit = defineEmits<{
  (e: "update:show", value: boolean): void;
  (e: "update:addError", value: string): void;
  (e: "switch", code: string): void;
  (e: "remove", code: string): void;
  (e: "add", code: string): void;
}>();

const formVisible = ref(false);
const newInviteCode = ref("");

// 添加成功后父级会更新 agents 列表：据此收起表单并清空输入
watch(
  () => props.agents.length,
  () => {
    formVisible.value = false;
    newInviteCode.value = "";
  }
);

function submitAdd() {
  emit("add", newInviteCode.value.trim());
}
</script>

<template>
  <van-popup :show="show" round position="bottom" @update:show="(value: boolean) => emit('update:show', value)">
    <div class="max-h-[70vh] overflow-y-auto p-4">
      <div class="mb-4 flex items-center justify-between">
        <div>
          <div class="text-base font-semibold text-slate-950">选择中介橱窗</div>
          <div class="mt-1 text-xs text-slate-500">切换后地图会展示对应中介的订单</div>
        </div>
        <button class="rounded-lg bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700" @click="formVisible = true">
          添加
        </button>
      </div>

      <div class="space-y-2">
        <div
          v-for="code in agents"
          :key="code"
          class="flex items-center gap-3 rounded-xl border p-3"
          :class="code === currentCode ? 'border-blue-600 bg-blue-50' : 'border-slate-200 bg-white'"
        >
          <button class="min-w-0 flex-1 text-left" @click="emit('switch', code)">
            <div class="truncate text-sm font-semibold text-slate-950">
              {{ code === currentCode ? (tenantName || '当前中介') : '中介橱窗' }}
            </div>
            <div class="mt-1 text-xs text-slate-500">邀请码：{{ code }}</div>
          </button>
          <button
            class="rounded-lg bg-slate-100 px-3 py-2 text-xs text-slate-600"
            @click="emit('remove', code)"
          >
            移除
          </button>
        </div>
      </div>
    </div>
  </van-popup>

  <!-- 添加中介 -->
  <van-popup :show="formVisible" round position="bottom" @update:show="(value: boolean) => (formVisible = value)">
    <div class="p-4">
      <div class="mb-4 text-base font-semibold text-slate-950">添加中介橱窗</div>
      <van-field
        v-model="newInviteCode"
        label="邀请码"
        placeholder="输入中介给你的邀请码"
        clearable
        @update:model-value="emit('update:addError', '')"
      />
      <div v-if="addError" class="mt-2 rounded-lg bg-red-50 px-3 py-2 text-xs leading-5 text-red-600">
        {{ addError }}
      </div>
      <button
        class="mt-4 w-full rounded-xl bg-blue-600 py-3 text-sm font-semibold text-white"
        @click="submitAdd"
      >
        添加并查看
      </button>
    </div>
  </van-popup>
</template>
