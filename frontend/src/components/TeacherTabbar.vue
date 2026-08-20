<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();

const AGENT_STORAGE_KEY = "teacher_agent_invite_codes";

const active = computed(() => {
  if (route.path.startsWith("/teacher/applications")) return "applications";
  if (route.path.startsWith("/teacher/profile")) return "profile";
  return "board";
});

function getInviteCode() {
  const routeInviteCode = route.params.inviteCode;
  if (typeof routeInviteCode === "string" && routeInviteCode.trim()) {
    return routeInviteCode.trim();
  }

  try {
    const saved = JSON.parse(localStorage.getItem(AGENT_STORAGE_KEY) || "[]");
    if (Array.isArray(saved) && saved[0]) {
      return String(saved[0]);
    }
  } catch {
    // Ignore malformed local storage and fall back to the default demo invite code.
  }

  return "tx886";
}

function goBoard() {
  router.push(`/teacher/board/${getInviteCode()}`);
}
</script>

<template>
  <van-tabbar :model-value="active" :fixed="true" :border="true" active-color="#2563eb" safe-area-inset-bottom>
    <van-tabbar-item name="board" icon="location-o" @click="goBoard">找单</van-tabbar-item>
    <van-tabbar-item name="applications" icon="orders-o" @click="router.push('/teacher/applications')">投递</van-tabbar-item>
    <van-tabbar-item name="profile" icon="user-o" @click="router.push('/teacher/profile')">我的</van-tabbar-item>
  </van-tabbar>
</template>
