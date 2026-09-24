<script setup lang="ts">
/**
 * 个人中心主页面：头部资料卡 + 菜单入口 + 角标。
 * 六个功能弹层拆分至 components/teacher/profile/（简历库/通知/费用/评价/资料编辑/改密）。
 */
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { notificationsApi } from "@/api/notifications";
import { applicationsApi } from "@/api/applications";
import TeacherTabbar from "@/components/TeacherTabbar.vue";
import ResumeLibrary from "@/components/teacher/profile/ResumeLibrary.vue";
import NotificationList from "@/components/NotificationList.vue";
import FeesPopup from "@/components/teacher/profile/FeesPopup.vue";
import ReviewsPopup from "@/components/teacher/profile/ReviewsPopup.vue";
import ProfileEditPopup from "@/components/teacher/profile/ProfileEditPopup.vue";
import PasswordPopup from "@/components/teacher/profile/PasswordPopup.vue";
import DeactivatePopup from "@/components/teacher/profile/DeactivatePopup.vue";
import { getLastInviteCode } from "@/utils/inviteCode";

const router = useRouter();
const auth = useAuthStore();

// 弹层开关（内容与加载逻辑在各子组件内）
const notifVisible = ref(false);
const feesVisible = ref(false);
const reviewsVisible = ref(false);
const profileVisible = ref(false);
const pwVisible = ref(false);
const deactivateVisible = ref(false);

// 角标常显：进页面即拉取未读通知数与评价数，而不是等点击后再加载
const notifUnread = ref(0);
const reviewCount = ref(0);

async function loadBadges() {
  try {
    // 两个角标都走轻量未读数端点，不再全量拉通知/评价列表
    const [notifUnreadCount, reviewTotal] = await Promise.all([
      notificationsApi.unreadCount(),
      applicationsApi.myReviewsCount(),
    ]);
    notifUnread.value = notifUnreadCount;
    reviewCount.value = reviewTotal;
  } catch {
    // 角标加载失败不打扰主流程
  }
}

onMounted(async () => {
  if (auth.isLoggedIn) {
    if (!auth.teacher) {
      await auth.fetchMe();
    }
    loadBadges();
  }
});

function handleLogout() {
  const inviteCode = getLastInviteCode();
  auth.logout();
  router.replace({
    path: "/teacher/login",
    query: { inviteCode },
  });
}
</script>

<template>
  <div class="min-h-screen bg-slate-50 pb-24 mx-auto max-w-2xl">
    <van-nav-bar title="个人中心" left-arrow @click-left="router.back()" />

    <section class="mx-4 mt-2.5 rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm lg:mx-auto lg:max-w-2xl">
      <div class="flex items-center gap-3">
        <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-slate-100">
          <van-icon name="manager-o" size="24" color="#1e3558" />
        </div>
        <div class="min-w-0 flex-1 text-slate-900">
          <div class="text-lg font-bold">{{ auth.teacher?.name || (auth.isLoggedIn ? "已登录" : "未登录") }}</div>
          <div class="truncate text-sm text-slate-500">
            {{ auth.teacher?.school }} · {{ auth.teacher?.grade }}
          </div>
          <div v-if="auth.teacher?.home_area" class="mt-0.5 truncate text-xs text-slate-400">
            常驻地：{{ auth.teacher.home_area }}
          </div>
        </div>
        <button
          class="shrink-0 rounded-lg bg-slate-100 px-3 py-1.5 text-xs text-slate-700"
          @click="profileVisible = true"
        >
          编辑资料
        </button>
      </div>
      <div
        v-if="auth.teacher?.is_985 || auth.teacher?.is_211 || auth.teacher?.is_double_first_class || auth.teacher?.is_985_211"
        class="mt-2 flex flex-wrap gap-1.5"
      >
        <span v-if="auth.teacher?.is_985" class="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-700">985</span>
        <span v-if="auth.teacher?.is_211" class="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-700">211</span>
        <span v-if="auth.teacher?.is_double_first_class" class="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-700">双一流</span>
        <span
          v-if="auth.teacher?.is_985_211 && !auth.teacher?.is_985 && !auth.teacher?.is_211"
          class="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs text-slate-700"
        >
          985/211
        </span>
      </div>
    </section>

    <div class="p-3 space-y-2.5">
      <ResumeLibrary />

      <section class="rounded-xl bg-white shadow-sm profile-menu">
        <van-cell title="我的通知" icon="bell" is-link @click="notifVisible = true">
          <template #value>
            <span v-if="notifUnread > 0" class="admin-notification-badge">{{ notifUnread > 99 ? "99+" : notifUnread }}</span>
          </template>
        </van-cell>
        <van-cell title="我的费用" icon="balance-pay" is-link @click="feesVisible = true" />
        <van-cell title="收到的评价" icon="star-o" is-link @click="reviewsVisible = true">
          <template #value>
            <span v-if="reviewCount > 0" class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">{{ reviewCount }} 条</span>
          </template>
        </van-cell>
        <van-cell title="修改登录密码" icon="shield-o" is-link @click="pwVisible = true" />
        <van-cell title="帮助中心" icon="question-o" is-link @click="router.push('/teacher/help')" />
      </section>

      <section class="rounded-xl bg-white shadow-sm profile-menu">
        <van-cell title="退出登录" icon="revoke" @click="handleLogout" />
        <van-cell title="注销账号" icon="warn-o" @click="deactivateVisible = true" />
      </section>
    </div>

    <NotificationList
      v-model:show="notifVisible"
      scope="teacher"
      title="我的通知"
      empty-hint="暂无通知。投递进展（候选、定金、试课、成交、退款）都会在这里提醒你。"
      @read="notifUnread = 0"
    />
    <FeesPopup v-model:show="feesVisible" />
    <ReviewsPopup v-model:show="reviewsVisible" />
    <ProfileEditPopup v-model:show="profileVisible" />
    <PasswordPopup v-model:show="pwVisible" />
    <DeactivatePopup v-model:show="deactivateVisible" />
    <TeacherTabbar />
  </div>
</template>

<style scoped>
/* 一屏收纳：压缩菜单行距（默认 10px 16px），编辑资料入口保留在头部卡片 */
.profile-menu :deep(.van-cell) {
  padding: 7px 16px;
}
</style>
