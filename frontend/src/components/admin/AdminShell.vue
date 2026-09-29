<script setup lang="ts">
/**
 * B 端统一桌面外壳（Batch 02）。
 *
 *  解决的问题：此前五个后台页各自带一个 max-w（2xl / 4xl / 6xl / none 都有），
 *  侧栏是一条 76px 无标签图标带，1920px 屏上内容居中在几百像素里、两侧死白，
 *  页面之间也建立不起"我在同一个系统里"的位置感。本组件把这层 chrome 收成一处：
 *
 *    ≥1024px  212px 带文字分组的侧栏 + 56px 顶栏，内容区自适应
 *    <1024px  顶栏保留，导航仍是原有底部 AdminTabbar（H5 形态不变）
 *
 *  通知铃铛与 60s 未读轮询一并从 Dashboard 上移到此处 —— 它属于全局 chrome，
 *  不该只有首页才有入口。业务逻辑（api 调用、状态、路由）未改动。
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { notificationsApi } from "@/api/notifications";
import AdminTabbar from "@/components/AdminTabbar.vue";
import NotificationList from "@/components/NotificationList.vue";

/** fluid：桌面端不限内容宽度（表格 / 地图 / 三栏审核等需要铺满的页面）
 *  仅在模板中读取，故不接收返回值。 */
withDefaults(defineProps<{ fluid?: boolean }>(), { fluid: false });

const route = useRoute();
const router = useRouter();
const auth = useAuthStore();

const NAV_GROUPS = [
  {
    group: "经营",
    items: [
      { key: "dashboard", label: "工作台", to: "/admin/dashboard", icon: "wap-home-o" },
      { key: "applications", label: "投递审核", to: "/admin/applications", icon: "friends-o" },
    ],
  },
  {
    group: "订单",
    items: [
      { key: "orders", label: "订单管理", to: "/admin/orders", icon: "orders-o" },
      { key: "import", label: "AI 批量录单", to: "/admin/batch-import", icon: "bulb-o", ai: true },
      { key: "map", label: "地图看单", to: "/admin/map", icon: "location-o" },
    ],
  },
  {
    group: "资金与教员",
    items: [
      { key: "financial", label: "财务流水", to: "/admin/financial-records", icon: "balance-list-o" },
      { key: "settings", label: "设置", to: "/admin/settings", icon: "setting-o" },
    ],
  },
];

const activeKey = computed(() => {
  const p = route.path;
  if (p.startsWith("/admin/batch-import")) return "import";
  if (p.startsWith("/admin/orders")) return "orders";
  if (p.startsWith("/admin/map")) return "map";
  if (p.startsWith("/admin/applications")) return "applications";
  if (p.startsWith("/admin/financial-records")) return "financial";
  if (p.startsWith("/admin/settings")) return "settings";
  return "dashboard";
});

const tenantName = computed(
  () => auth.tenant?.tenant_name || (auth.role === "super_admin" ? "平台管理" : "中介后台"),
);
const inviteCode = computed(() => auth.tenant?.invite_code || "");

function go(path: string) {
  if (route.path !== path) router.push(path);
}

// ── 全局搜索：走订单列表既有的 ?q= 参数（OrdersList onMounted 会读取并搜索），
//    所以是真实检索而非占位；本 Shell 不直接调接口，职责只到跳转 ──
const searchText = ref("");
function submitSearch() {
  const q = searchText.value.trim();
  if (!q) return;
  router.push({ path: "/admin/orders", query: { q } });
}

// ── 通知（自 Dashboard.vue 原样上移：轻量未读数端点 + 60s 静默轮询） ──
const notifVisible = ref(false);
const notifUnread = ref(0);
let badgeTimer: number | undefined;

async function loadNotifBadge() {
  try {
    notifUnread.value = await notificationsApi.tenantUnreadCount();
  } catch {
    // 角标加载失败不打扰主流程
  }
}

function onVisibilityChange() {
  if (!document.hidden) loadNotifBadge();
}

onMounted(() => {
  loadNotifBadge();
  badgeTimer = window.setInterval(() => {
    if (document.hidden) return;
    loadNotifBadge();
  }, 60_000);
  document.addEventListener("visibilitychange", onVisibilityChange);
});

onUnmounted(() => {
  if (badgeTimer) window.clearInterval(badgeTimer);
  document.removeEventListener("visibilitychange", onVisibilityChange);
});

function logout() {
  auth.logout();
  router.push("/admin/login");
}
</script>

<template>
  <div class="admin-shell min-h-screen bg-page">
    <!-- 桌面侧栏：带文字与分组，是"同一个系统"的位置感来源 -->
    <aside
      class="fixed inset-y-0 left-0 z-40 hidden w-[212px] flex-col bg-brand-900 text-white lg:flex"
    >
      <div class="flex items-center gap-2.5 px-4 pb-4 pt-5 text-[15px] font-bold">
        <span class="grid h-7 w-7 place-items-center rounded-lg bg-white text-[13px] text-brand-900">智</span>
        智派家教
      </div>

      <div class="mx-3 mb-4 flex items-center gap-2 rounded-lg bg-white/10 px-3 py-2">
        <van-icon name="wap-home-o" size="16" class="text-white/70" />
        <div class="min-w-0 flex-1">
          <div class="truncate text-xs font-semibold leading-tight">{{ tenantName }}</div>
          <div v-if="inviteCode" class="truncate text-[10px] text-white/55">{{ inviteCode }}</div>
        </div>
      </div>

      <nav class="flex-1 overflow-y-auto pb-4">
        <template v-for="section in NAV_GROUPS" :key="section.group">
          <div class="px-4 pb-1 pt-3 text-[10px] font-semibold tracking-[0.13em] text-white/40">
            {{ section.group }}
          </div>
          <button
            v-for="item in section.items"
            :key="item.key"
            type="button"
            class="mx-2.5 flex w-[calc(100%-20px)] items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-medium transition-colors"
            :class="
              activeKey === item.key
                ? 'bg-white/15 text-white'
                : item.ai
                  ? 'text-[#c9c0fb] hover:bg-white/10'
                  : 'text-white/70 hover:bg-white/10'
            "
            @click="go(item.to)"
          >
            <van-icon :name="item.icon" size="16" />
            <span class="truncate">{{ item.label }}</span>
          </button>
        </template>
      </nav>

      <button
        type="button"
        class="flex items-center gap-2.5 border-t border-white/10 px-4 py-3 text-left"
        @click="logout"
      >
        <span class="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-white/15 text-[11px] font-semibold">
          {{ (tenantName || "管").slice(0, 1) }}
        </span>
        <div class="min-w-0 flex-1">
          <div class="truncate text-xs font-semibold">{{ tenantName }}</div>
          <div class="text-[10px] text-white/50">点击退出登录</div>
        </div>
        <van-icon name="revoke" size="14" class="text-white/45" />
      </button>
    </aside>

    <div class="lg:pl-[212px]">
      <!-- 顶栏：搜索 + 通知（两档尺寸共用，桌面端右对齐到内容边缘） -->
      <header
        class="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-default bg-surface/95 px-4 backdrop-blur lg:px-6"
      >
        <span class="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-brand-800 text-[12px] font-bold text-white lg:hidden">
          智
        </span>

        <form class="flex min-w-0 flex-1 items-center gap-2" @submit.prevent="submitSearch">
          <div
            class="flex h-9 w-full max-w-md min-w-0 items-center gap-2 rounded-lg bg-surface-soft px-3 text-muted"
          >
            <van-icon name="search" size="15" />
            <input
              v-model="searchText"
              type="search"
              class="min-w-0 flex-1 bg-transparent text-[13px] text-primary outline-none placeholder:text-muted"
              placeholder="搜索订单号 / 教员 / 手机号"
            />
          </div>
          <button
            type="submit"
            class="hidden h-9 shrink-0 items-center gap-1.5 rounded-lg border border-default px-3 text-xs font-medium text-secondary transition-colors hover:bg-surface-soft sm:flex"
          >
            搜索
          </button>
        </form>

        <div class="ml-auto flex shrink-0 items-center gap-2">
          <button
            type="button"
            class="relative grid h-9 w-9 place-items-center rounded-lg bg-surface-soft text-secondary transition-colors hover:bg-brand-50"
            aria-label="消息通知"
            @click="notifVisible = true"
          >
            <van-icon name="bell" size="17" />
            <span v-if="notifUnread > 0" class="admin-notification-badge absolute -right-1 -top-1">
              {{ notifUnread > 99 ? "99+" : notifUnread }}
            </span>
          </button>
          <button
            type="button"
            class="hidden h-9 items-center gap-1.5 rounded-lg bg-surface-soft px-3 text-[13px] text-secondary transition-colors hover:bg-brand-50 sm:flex"
            @click="go('/admin/settings')"
          >
            <van-icon name="setting-o" size="16" />
            设置
          </button>
        </div>
      </header>

      <!-- 页面内容：Shell 只管宽度口径与垂直节奏，页面内部左右内边距仍由各页自管
           （B 端表格/分栏需要紧贴可用宽度，双重 px 会挤掉数据列） -->
      <main
        class="w-full max-w-2xl pb-24 pt-3 lg:max-w-[1440px] lg:pb-8 lg:pt-5"
        :class="fluid ? 'lg:max-w-none' : ''"
      >
        <slot />
      </main>
    </div>

    <!-- 移动端底部导航（桌面端由侧栏承担，已在 main.css 隐藏） -->
    <AdminTabbar />

    <NotificationList
      v-model:show="notifVisible"
      scope="tenant"
      title="消息通知"
      empty-hint="暂无通知。收到新投递、订单即将过期时会在这里提醒。"
    />
  </div>
</template>
