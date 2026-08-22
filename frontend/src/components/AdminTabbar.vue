<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();

const active = computed(() => {
  if (route.path.startsWith("/admin/batch-import")) return "import";
  if (route.path.startsWith("/admin/orders")) return "orders";
  if (route.path.startsWith("/admin/map")) return "map";
  if (route.path.startsWith("/admin/applications")) return "applications";
  if (route.path.startsWith("/admin/financial-records")) return "financial";
  return "dashboard";
});

function go(path: string) {
  if (route.path !== path) {
    router.push(path);
  }
}
</script>

<template>
  <van-tabbar :model-value="active" :fixed="true" :border="true" active-color="#2563eb">
    <van-tabbar-item name="dashboard" icon="home-o" @click="go('/admin/dashboard')">首页</van-tabbar-item>
    <van-tabbar-item name="import" icon="add-o" @click="go('/admin/batch-import')">导入</van-tabbar-item>
    <van-tabbar-item name="orders" icon="records-o" @click="go('/admin/orders')">订单</van-tabbar-item>
    <van-tabbar-item name="map" icon="location-o" @click="go('/admin/map')">地图</van-tabbar-item>
    <van-tabbar-item name="applications" icon="user-o" @click="go('/admin/applications')">投递</van-tabbar-item>
    <van-tabbar-item name="financial" icon="balance-list-o" @click="go('/admin/financial-records')">财务</van-tabbar-item>
  </van-tabbar>
</template>
