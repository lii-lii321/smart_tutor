<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { notificationsApi } from "@/api/notifications";
import { resolveInviteCode } from "@/utils/inviteCode";

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

// 「我的」标签的未读消息角标：每次进入页面重新拉取
const unread = ref(0);
const unreadLabel = computed(() =>
  unread.value > 99 ? "99+" : unread.value ? String(unread.value) : "",
);

onMounted(async () => {
  // 未登录（游客逛橱窗）不拉未读数：该接口 401 会触发全局"登录已过期"跳转，
  // 把游客从公开橱窗踢去登录页
  if (!auth.isLoggedIn) {
    return;
  }
  try {
    unread.value = await notificationsApi.unreadCount();
  } catch {
    unread.value = 0;
  }
});

const active = computed(() => {
  if (route.path.startsWith("/teacher/applications")) return "applications";
  if (route.path.startsWith("/teacher/profile")) return "profile";
  return "board";
});

function goBoard() {
  router.push(`/teacher/board/${resolveInviteCode(route.params.inviteCode)}`);
}

function goApplications() {
  router.push("/teacher/applications");
}

function goProfile() {
  router.push("/teacher/profile");
}

const tabs = [
  { key: "board", label: "找单", icon: "location-o", go: goBoard },
  { key: "applications", label: "投递", icon: "orders-o", go: goApplications },
  { key: "profile", label: "我的", icon: "user-o", go: goProfile },
];
</script>

<template>
  <!-- UI 2.0 悬浮胶囊底栏（设计稿 03 画板）：白底描边容器，激活项黑胶囊；
       自绘三等分替代 van-tabbar，safe-area 由 bottom 偏移吸收 -->
  <nav
    class="teacher-tabbar fixed inset-x-3 bottom-[calc(12px+env(safe-area-inset-bottom))] z-30 flex rounded-[36px] border border-default bg-surface p-1 shadow-lg"
  >
    <button
      v-for="tab in tabs"
      :key="tab.key"
      type="button"
      class="relative flex flex-1 flex-col items-center justify-center gap-0.5 rounded-[28px] py-2 text-caption font-medium transition-colors"
      :class="active === tab.key ? 'bg-ink text-white' : 'text-muted'"
      @click="tab.go()"
    >
      <van-icon :name="tab.icon" size="20" />
      {{ tab.label }}
      <span
        v-if="tab.key === 'profile' && unreadLabel"
        class="absolute right-[24%] top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-caption font-bold text-ink"
      >
        {{ unreadLabel }}
      </span>
    </button>
  </nav>
</template>
