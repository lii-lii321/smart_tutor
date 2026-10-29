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

// 切中回弹：点中的 tab 图标播放一次弹性放大动画（2026-10-29 交互补强）
const bouncing = ref("");
let bounceTimer: ReturnType<typeof setTimeout> | undefined;
function onTab(tab: (typeof tabs)[number]) {
  tab.go();
  bouncing.value = tab.key;
  clearTimeout(bounceTimer);
  bounceTimer = setTimeout(() => (bouncing.value = ""), 450);
}

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
       自绘三等分替代 van-tabbar，safe-area 由 bottom 偏移吸收。
       2026-10-27 密度收紧：移动端首屏留给订单卡 -->
  <nav
    class="teacher-tabbar fixed inset-x-3 bottom-[calc(10px+env(safe-area-inset-bottom))] z-30 flex rounded-[24px] border border-default bg-surface p-0.5 shadow-lg"
  >
    <button
      v-for="tab in tabs"
      :key="tab.key"
      type="button"
      class="relative flex flex-1 flex-col items-center justify-center rounded-[18px] py-1 text-caption font-medium transition active:scale-95"
      :class="active === tab.key ? 'bg-ink text-white' : 'text-muted'"
      @click="onTab(tab)"
    >
      <van-icon
        :name="tab.icon"
        size="17"
        class="tab-ico"
        :class="{ 'tab-ico-bounce': bouncing === tab.key }"
      />
      {{ tab.label }}
      <span
        v-if="tab.key === 'profile' && unreadLabel"
        class="absolute right-[22%] top-0.5 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-accent px-1 text-caption font-bold text-ink"
      >
        {{ unreadLabel }}
      </span>
    </button>
  </nav>
</template>

<style scoped>
/* 切中回弹：图标弹性放大一次（超出部分不被胶囊裁剪，nav 未设 overflow） */
.tab-ico {
  display: inline-block;
}
.tab-ico-bounce {
  animation: tab-pop 0.42s cubic-bezier(0.34, 1.8, 0.5, 1);
}
@keyframes tab-pop {
  0% { transform: scale(1); }
  35% { transform: scale(1.28) translateY(-1px); }
  65% { transform: scale(0.92); }
  100% { transform: scale(1); }
}
@media (prefers-reduced-motion: reduce) {
  .tab-ico-bounce {
    animation: none;
  }
}
</style>
