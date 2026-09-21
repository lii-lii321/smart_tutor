<script setup lang="ts">
/**
 * 通知列表弹层——教员端与 B 端共用（此前两端各维护一份约 120 行，口径已开始漂移）。
 * 差异点全部收敛为 props/内部适配：
 * - scope 决定 API 走教员侧还是租户侧端点；
 * - 通知跳转：教员去订单详情，中介去投递审核页；
 * - 空态文案与标题由调用方传入。
 * 管理模式：勾选批量删除 / 清空全部（用户主动删除，不设自动清理）；
 * 教员端全部已读后发 read 事件同步角标。
 */
import { computed, ref, watch } from "vue";
import { formatDateTime } from "@/utils/format";
import { useRouter } from "vue-router";
import { showToast } from "vant";
import { appConfirm } from "@/composables/appConfirm";
import { notificationsApi, type NotificationItem } from "@/api/notifications";

const show = defineModel<boolean>("show", { default: false });

const props = defineProps<{
  /** 数据域：teacher 走教员端点，tenant 走 B 端端点（超管可见全平台） */
  scope: "teacher" | "tenant";
  title: string;
  emptyHint: string;
}>();

const emit = defineEmits<{ (e: "read"): void }>();

const router = useRouter();

const notifLoading = ref(false);
const notifications = ref<NotificationItem[]>([]);
const unread = ref(0);
// 管理模式：勾选删除
const managing = ref(false);
const checkedIds = ref<Set<number>>(new Set());

const api = computed(() =>
  props.scope === "teacher"
    ? {
        mine: notificationsApi.mine,
        readAll: notificationsApi.readAll,
        deleteChecked: notificationsApi.deleteMine,
        deleteAll: notificationsApi.deleteAllMine,
      }
    : {
        mine: notificationsApi.tenantMine,
        readAll: notificationsApi.tenantReadAll,
        deleteChecked: notificationsApi.deleteTenant,
        deleteAll: notificationsApi.deleteAllTenant,
      }
);

watch(
  show,
  async (visible) => {
    if (!visible) return;
    notifLoading.value = true;
    try {
      const data = await api.value.mine();
      notifications.value = data.items;
      unread.value = data.unread_count;
    } catch {
      showToast("通知加载失败");
    } finally {
      notifLoading.value = false;
    }
  },
  { immediate: true }
);

async function markAllRead() {
  try {
    await api.value.readAll();
    notifications.value = notifications.value.map((n) => ({ ...n, is_read: true }));
    unread.value = 0;
    emit("read");
    showToast("已全部标记为已读");
  } catch {
    showToast("操作失败");
  }
}

const allChecked = computed(
  () => notifications.value.length > 0 && checkedIds.value.size === notifications.value.length
);

function toggleChecked(id: number) {
  const next = new Set(checkedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  checkedIds.value = next;
}

function toggleAll() {
  checkedIds.value = allChecked.value
    ? new Set()
    : new Set(notifications.value.map((n) => n.id));
}

function toggleManaging() {
  managing.value = !managing.value;
  checkedIds.value = new Set();
}

async function deleteChecked() {
  const ids = [...checkedIds.value];
  if (ids.length === 0) return;
  try {
    const res = await api.value.deleteChecked(ids);
    notifications.value = notifications.value.filter((n) => !checkedIds.value.has(n.id));
    checkedIds.value = new Set();
    showToast(`已删除 ${res.marked} 条`);
  } catch {
    showToast("删除失败");
  }
}

async function deleteAll() {
  const ok = await appConfirm({
    title: "清空全部通知？",
    message: "删除后不可恢复，投递进展仍可在对应订单中查看。",
    confirmText: "清空",
    danger: true,
  });
  if (!ok) return;
  try {
    await api.value.deleteAll();
    notifications.value = [];
    checkedIds.value = new Set();
    showToast("已清空");
  } catch {
    showToast("删除失败");
  }
}

function openItem(item: NotificationItem) {
  if (!item.order_id) return;
  show.value = false;
  router.push(
    props.scope === "teacher"
      ? `/teacher/orders/${item.order_id}`
      : `/admin/applications?order=${item.order_id}`
  );
}
</script>

<template>
  <van-popup v-model:show="show" round position="bottom" :style="{ maxHeight: '75vh' }" close-on-click-overlay>
    <div class="flex max-h-[75vh] flex-col p-4">
      <div class="mb-3 flex items-center justify-between">
        <div class="text-base font-semibold text-slate-950">{{ title }}</div>
        <div class="flex items-center gap-3">
          <button
            v-if="!managing && unread > 0"
            class="text-sm text-blue-600"
            @click="markAllRead"
          >
            全部已读
          </button>
          <button
            v-if="notifications.length > 0"
            class="text-sm text-slate-500"
            @click="toggleManaging"
          >
            {{ managing ? "完成" : "管理" }}
          </button>
        </div>
      </div>

      <!-- 管理模式工具条：全选 + 删除 -->
      <div v-if="managing" class="mb-2 flex items-center justify-between rounded-lg bg-slate-50 px-3 py-2">
        <label class="flex items-center gap-2 text-sm text-slate-600">
          <input type="checkbox" :checked="allChecked" @change="toggleAll" />
          全选（{{ checkedIds.size }}/{{ notifications.length }}）
        </label>
        <button
          class="text-sm font-medium text-red-500 disabled:opacity-40"
          :disabled="checkedIds.size === 0"
          @click="deleteChecked"
        >
          删除选中
        </button>
      </div>

      <div class="overflow-y-auto">
        <div v-if="notifLoading" class="flex justify-center py-8">
          <van-loading type="spinner" color="#2563eb" />
        </div>
        <div v-else-if="notifications.length === 0" class="py-8 text-center text-sm text-slate-400">
          {{ emptyHint }}
        </div>
        <div v-else class="space-y-3">
          <article
            v-for="item in notifications"
            :key="item.id"
            class="rounded-lg border p-3"
            :class="managing ? 'flex items-start gap-2 border-slate-100 bg-white' : item.is_read ? 'border-slate-100 bg-white' : 'border-blue-100 bg-blue-50/40'"
          >
            <input
              v-if="managing"
              type="checkbox"
              class="mt-1"
              :checked="checkedIds.has(item.id)"
              @change="toggleChecked(item.id)"
            />
            <div class="min-w-0 flex-1">
              <div class="flex items-start justify-between gap-2">
                <div class="text-sm font-semibold text-slate-900">
                  {{ !managing && !item.is_read ? "● " : "" }}{{ item.title }}
                </div>
                <div class="shrink-0 text-xs text-slate-400">
                  {{ formatDateTime(item.created_at) }}
                </div>
              </div>
              <p v-if="item.content" class="mt-1 text-sm leading-5 text-slate-600">{{ item.content }}</p>
              <button
                v-if="!managing && item.order_id"
                class="mt-2 text-xs font-medium text-blue-600"
                @click="openItem(item)"
              >
                {{ scope === "teacher" ? "去查看 →" : "去处理 →" }}
              </button>
            </div>
          </article>
        </div>
      </div>

      <button
        v-if="managing && notifications.length > 0"
        class="mt-3 shrink-0 text-center text-xs text-slate-400"
        @click="deleteAll"
      >
        清空全部通知
      </button>
    </div>
  </van-popup>
</template>
