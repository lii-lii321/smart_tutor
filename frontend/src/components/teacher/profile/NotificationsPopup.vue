<script setup lang="ts">
/**
 * 我的通知弹层（自 Profile.vue 拆出）：打开时拉取列表，支持一键已读与跳转订单。
 * 全部已读后向父级发 read 事件同步角标。
 */
import { ref, watch } from "vue";
import { useRouter } from "vue-router";
import { notificationsApi, type NotificationItem } from "@/api/notifications";
import { showToast } from "vant";

const show = defineModel<boolean>("show", { default: false });

const emit = defineEmits<{ (e: "read"): void }>();

const router = useRouter();

const notifLoading = ref(false);
const notifications = ref<NotificationItem[]>([]);
const unread = ref(0);

watch(
  show,
  async (visible) => {
    if (!visible) return;
    notifLoading.value = true;
    try {
      const data = await notificationsApi.mine();
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
    await notificationsApi.readAll();
    notifications.value = notifications.value.map((n) => ({ ...n, is_read: true }));
    unread.value = 0;
    emit("read");
    showToast("已全部标记为已读");
  } catch {
    showToast("操作失败");
  }
}
</script>

<template>
  <van-popup v-model:show="show" round position="bottom" :style="{ maxHeight: '75vh' }" close-on-click-overlay>
    <div class="flex max-h-[75vh] flex-col p-4">
      <div class="mb-3 flex items-center justify-between">
        <div class="text-base font-semibold text-slate-950">我的通知</div>
        <button
          v-if="unread > 0"
          class="text-sm text-blue-600"
          @click="markAllRead"
        >
          全部已读
        </button>
      </div>
      <div class="overflow-y-auto">
        <div v-if="notifLoading" class="flex justify-center py-8">
          <van-loading type="spinner" color="#2563eb" />
        </div>
        <div v-else-if="notifications.length === 0" class="py-8 text-center text-sm text-slate-400">
          暂无通知。投递进展（候选、定金、试课、成交、退款）都会在这里提醒你。
        </div>
        <div v-else class="space-y-3">
          <article
            v-for="item in notifications"
            :key="item.id"
            class="rounded-lg border p-3"
            :class="item.is_read ? 'border-slate-100 bg-white' : 'border-blue-100 bg-blue-50/40'"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="text-sm font-semibold text-slate-900">
                {{ item.is_read ? "" : "● " }}{{ item.title }}
              </div>
              <div class="shrink-0 text-xs text-slate-400">
                {{ new Date(item.created_at).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) }}
              </div>
            </div>
            <p v-if="item.content" class="mt-1 text-sm leading-5 text-slate-600">{{ item.content }}</p>
            <button
              v-if="item.order_id"
              class="mt-2 text-xs font-medium text-blue-600"
              @click="show = false; router.push(`/teacher/orders/${item.order_id}`)"
            >
              去查看 →
            </button>
          </article>
        </div>
      </div>
    </div>
  </van-popup>
</template>
