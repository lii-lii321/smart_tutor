<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import { resolveInviteCode } from "@/utils/inviteCode";

const route = useRoute();
const router = useRouter();

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
    <van-tabbar-item name="profile" icon="user-o" @click="goProfile">我的</van-tabbar-item>
  </van-tabbar>
</template>
