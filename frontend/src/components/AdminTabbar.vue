<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { applicationsApi } from "@/api/applications";
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();

const props = defineProps<{ applicationCount?: number }>();
const fetchedApplicationCount = ref(0);
const displayApplicationCount = computed(() => props.applicationCount ?? fetchedApplicationCount.value);

onMounted(async () => {
  if (props.applicationCount !== undefined) return;
  try {
    const summary = await applicationsApi.summary();
    fetchedApplicationCount.value = Number(summary?.total_applications || 0);
  } catch {
    fetchedApplicationCount.value = 0;
  }
});

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
  <van-tabbar class="admin-tabbar" :model-value="active" :fixed="true" :border="true" active-color="#2563eb" safe-area-inset-bottom>
    <van-tabbar-item name="dashboard" icon="home-o" @click="go('/admin/dashboard')">首页</van-tabbar-item>
    <van-tabbar-item name="import" icon="add-o" @click="go('/admin/batch-import')">导入</van-tabbar-item>
    <van-tabbar-item name="orders" icon="records-o" @click="go('/admin/orders')">订单</van-tabbar-item>
    <van-tabbar-item name="map" icon="location-o" @click="go('/admin/map')">地图</van-tabbar-item>
    <van-tabbar-item name="applications" icon="user-o" @click="go('/admin/applications')">
      <template #icon>
        <span class="relative inline-flex h-6 w-6 items-center justify-center">
          <van-icon name="user-o" size="24" />
          <span v-if="displayApplicationCount" class="admin-notification-badge absolute -right-1 -top-1">{{ displayApplicationCount > 99 ? "99+" : displayApplicationCount }}</span>
        </span>
      </template>
      投递
    </van-tabbar-item>
    <van-tabbar-item name="financial" icon="balance-list-o" @click="go('/admin/financial-records')">财务</van-tabbar-item>
  </van-tabbar>
</template>
