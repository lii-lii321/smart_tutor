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
    const data = await notificationsApi.mine();
    unread.value = Number(data?.unread_count || 0);
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

</script>

<template>
  <van-tabbar class="teacher-tabbar" :model-value="active" :z-index="1000" :fixed="true" :border="true" active-color="#2563eb" safe-area-inset-bottom>
    <van-tabbar-item name="board" icon="location-o" @click="goBoard">找单</van-tabbar-item>
    <van-tabbar-item name="applications" icon="orders-o" @click="goApplications">投递</van-tabbar-item>
    <van-tabbar-item name="profile" icon="user-o" :badge="unreadLabel" @click="goProfile">我的</van-tabbar-item>
  </van-tabbar>
</template>
