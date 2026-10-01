<script setup lang="ts">
/**
 * 个人中心：教员个人资产聚合页。
 *
 * 结构（2026-09-29 改版，参照概念稿方向、数据全部来自真实端点）：
 *   身份卡（认证院校标签 + 常驻地 + 个人简介）
 *   → 资产统计（接单/进行中/评价/累计支付，来自公开成绩单 + 我的投递 + 费用汇总）
 *   → 我的投递状态分布（点击进入投递列表）
 *   → 功能入口（简历库/费用/评价/改密）+ 通知/帮助/退出。
 *
 * 口径说明：本产品信息费由教员支付、课酬走线下，平台没有"教员收入"数据，
 * 资金侧统计用「累计支付」（定金+尾款信息费），不虚构收入。
 */
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { notificationsApi } from "@/api/notifications";
import { applicationsApi } from "@/api/applications";
import { financialApi } from "@/api/financial";
import { publicApi, type Scorecard } from "@/api/public";
import { formatMoney } from "@/utils/format";
import type { ApplicationStatus } from "@/api/types";
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

// ── 资产统计：三个真实端点，任一失败该卡显示 —，不编造 ──
const scorecard = ref<Scorecard | null>(null);
const feeTotals = ref<{ total_paid: number; total_refunded: number; total_forfeit: number } | null>(null);
const statusCounts = ref<Partial<Record<ApplicationStatus, number>>>({});

const stats = computed(() => {
  const sc = scorecard.value;
  const counts = statusCounts.value;
  const active = (["pending", "shortlisted", "trial_in_progress", "deposit_paid", "balance_paid"] as ApplicationStatus[])
    .reduce((sum, s) => sum + (counts[s] || 0), 0);
  return [
    { key: "deals", label: "接单", value: sc ? String(sc.completed_count) : "—", sub: `违约 ${sc?.violation_count ?? 0} 次` },
    { key: "active", label: "进行中", value: active > 0 ? String(active) : "—", sub: "投递推进中" },
    {
      key: "reviews",
      label: "评价",
      value: reviewCount.value > 0 ? String(reviewCount.value) : "—",
      sub: sc?.avg_rating != null ? `均分 ${sc.avg_rating} ★` : "来自成交订单",
    },
    {
      key: "paid",
      label: "累计支付",
      value: feeTotals.value ? formatMoney(feeTotals.value.total_paid) : "—",
      sub: "信息费（定金+尾款）",
    },
  ];
});

/** 我的投递状态分布：5 个真实分组（推进中=已入选到尾款之间） */
const orderBuckets = computed(() => {
  const c = statusCounts.value;
  const sum = (keys: ApplicationStatus[]) => keys.reduce((s, k) => s + (c[k] || 0), 0);
  return [
    { label: "待审核", count: sum(["pending"]), hint: "等待中介审核" },
    { label: "候选中", count: sum(["shortlisted"]), hint: "已入选候选队列" },
    { label: "推进中", count: sum(["trial_in_progress", "deposit_paid", "balance_paid"]), hint: "试课与定金/尾款推进" },
    { label: "已成交", count: sum(["completed"]), hint: "已完成的订单" },
    { label: "已终止", count: sum(["rejected", "refunded", "forfeited"]), hint: "未通过/已退款/定金没收" },
  ];
});

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

async function loadAssets() {
  const tasks: Promise<void>[] = [
    applicationsApi
      .listMine(1, 50)
      .then((list) => {
        const counts: Partial<Record<ApplicationStatus, number>> = {};
        for (const a of list) counts[a.status] = (counts[a.status] || 0) + 1;
        statusCounts.value = counts;
      })
      .catch(() => {}),
    financialApi
      .myFees(1, 1)
      .then((r) => {
        feeTotals.value = { total_paid: r.total_paid, total_refunded: r.total_refunded, total_forfeit: r.total_forfeit };
      })
      .catch(() => {}),
  ];
  if (auth.teacher?.id) {
    tasks.push(
      publicApi
        .scorecard(auth.teacher.id)
        .then((sc) => {
          scorecard.value = sc;
        })
        .catch(() => {}),
    );
  }
  await Promise.all(tasks);
}

// 简历库是内嵌区块（非弹层）：入口 tile 平滑滚动定位过去
const resumeSection = ref<HTMLDivElement | null>(null);
function scrollToResume() {
  resumeSection.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

onMounted(async () => {
  if (auth.isLoggedIn) {
    if (!auth.teacher) {
      await auth.fetchMe();
    }
    loadBadges();
    loadAssets();
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
  <div class="min-h-screen bg-page pb-24 mx-auto max-w-2xl">
    <van-nav-bar title="个人中心" left-arrow @click-left="router.back()" />

    <!-- 身份卡：教员在平台上的身份第一眼 -->
    <section class="mx-4 mt-2.5 rounded-2xl border border-default bg-white px-4 py-4 shadow-sm lg:mx-auto lg:max-w-2xl">
      <div class="flex items-center gap-3">
        <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-surface-soft">
          <van-icon name="manager-o" size="24" color="var(--st-brand-800)" />
        </div>
        <div class="min-w-0 flex-1 text-primary">
          <div class="flex flex-wrap items-center gap-1.5">
            <span class="text-lg font-bold leading-6">{{ auth.teacher?.name || (auth.isLoggedIn ? "已登录" : "未登录") }}</span>
            <span
              v-if="auth.teacher?.is_985 || auth.teacher?.is_211 || auth.teacher?.is_double_first_class || auth.teacher?.is_985_211"
              class="rounded-full bg-brand-50 px-1.5 py-0.5 text-[10px] font-medium leading-4 text-brand-700"
            >
              已认证院校
            </span>
          </div>
          <div class="mt-0.5 truncate text-sm text-secondary">
            {{ [auth.teacher?.school, auth.teacher?.major, auth.teacher?.grade].filter(Boolean).join(" · ") || "—" }}
          </div>
          <div v-if="auth.teacher?.home_area" class="mt-0.5 truncate text-xs text-muted">
            常驻地：{{ auth.teacher.home_area }}
          </div>
        </div>
        <button
          class="shrink-0 rounded-lg bg-surface-soft px-3 py-1.5 text-xs text-secondary"
          @click="profileVisible = true"
        >
          编辑资料
        </button>
      </div>
      <div class="mt-2 flex flex-wrap gap-1.5">
        <span v-if="auth.teacher?.is_985" class="rounded-full bg-brand-50 px-2.5 py-0.5 text-[11px] leading-4 text-brand-700">985</span>
        <span v-if="auth.teacher?.is_211" class="rounded-full bg-brand-50 px-2.5 py-0.5 text-[11px] leading-4 text-brand-700">211</span>
        <span v-if="auth.teacher?.is_double_first_class" class="rounded-full bg-brand-50 px-2.5 py-0.5 text-[11px] leading-4 text-brand-700">双一流</span>
        <span
          v-if="auth.teacher?.is_985_211 && !auth.teacher?.is_985 && !auth.teacher?.is_211"
          class="rounded-full bg-brand-50 px-2.5 py-0.5 text-[11px] leading-4 text-brand-700"
        >
          985/211
        </span>
      </div>
      <div
        v-if="auth.teacher?.highlights"
        class="mt-2.5 flex items-center gap-2 rounded-lg bg-surface-soft px-3 py-2 text-xs leading-5 text-secondary"
      >
        <van-icon name="bookmark-o" size="13" class="shrink-0 text-muted" />
        <span class="min-w-0 flex-1">{{ auth.teacher.highlights }}</span>
      </div>
    </section>

    <!-- 资产统计：接单/进行中/评价/累计支付（全部来自真实端点） -->
    <section class="mx-4 mt-3 grid grid-cols-4 gap-2 lg:mx-auto lg:max-w-2xl">
      <div v-for="s in stats" :key="s.key" class="rounded-xl bg-white p-3 text-center shadow-sm">
        <div class="truncate text-base font-bold leading-6 text-primary">{{ s.value }}</div>
        <div class="mt-0.5 text-[11px] leading-4 text-secondary">{{ s.label }}</div>
        <div class="mt-0.5 truncate text-[10px] leading-3 text-muted">{{ s.sub }}</div>
      </div>
    </section>

    <!-- 我的投递状态分布：与投递页同一状态机口径 -->
    <section class="mx-4 mt-3 rounded-2xl bg-white p-4 shadow-sm lg:mx-auto lg:max-w-2xl">
      <div class="mb-3 flex items-center justify-between">
        <h3 class="text-sm font-bold text-primary">我的投递</h3>
        <button class="text-xs text-brand-800" @click="router.push('/teacher/applications')">查看全部 →</button>
      </div>
      <div class="grid grid-cols-5 gap-1.5 text-center">
        <button
          v-for="b in orderBuckets"
          :key="b.label"
          class="rounded-lg bg-surface-soft/60 py-2"
          :title="b.hint"
          @click="router.push('/teacher/applications')"
        >
          <div class="text-base font-bold leading-6" :class="b.count > 0 ? 'text-brand-800' : 'text-muted'">
            {{ b.count }}
          </div>
          <div class="mt-0.5 text-[10px] leading-3 text-muted">{{ b.label }}</div>
        </button>
      </div>
    </section>

    <!-- 功能入口 2×2 -->
    <section class="mx-4 mt-3 grid grid-cols-2 gap-2.5 lg:mx-auto lg:max-w-2xl">
      <button class="flex items-center gap-2.5 rounded-xl border border-default bg-white p-3 text-left" @click="scrollToResume">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-soft text-brand-800">
          <van-icon name="notes-o" size="17" />
        </span>
        <span class="min-w-0">
          <span class="block text-sm font-semibold leading-5 text-primary">我的简历</span>
          <span class="block truncate text-[11px] leading-4 text-muted">完善资料，提升匹配率</span>
        </span>
      </button>
      <button class="flex items-center gap-2.5 rounded-xl border border-default bg-white p-3 text-left" @click="feesVisible = true">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-soft text-brand-800">
          <van-icon name="balance-pay" size="17" />
        </span>
        <span class="min-w-0">
          <span class="block text-sm font-semibold leading-5 text-primary">我的费用</span>
          <span class="block truncate text-[11px] leading-4 text-muted">
            {{ feeTotals ? `累计支付 ${formatMoney(feeTotals.total_paid)}` : "定金与尾款流水" }}
          </span>
        </span>
      </button>
      <button class="flex items-center gap-2.5 rounded-xl border border-default bg-white p-3 text-left" @click="reviewsVisible = true">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-soft text-brand-800">
          <van-icon name="star-o" size="17" />
        </span>
        <span class="min-w-0">
          <span class="block text-sm font-semibold leading-5 text-primary">收到的评价</span>
          <span class="block truncate text-[11px] leading-4 text-muted">
            {{ reviewCount > 0 ? `${reviewCount} 条${scorecard?.avg_rating != null ? ` · 均分 ${scorecard.avg_rating}★` : ""}` : "来自成交订单" }}
          </span>
        </span>
      </button>
      <button class="flex items-center gap-2.5 rounded-xl border border-default bg-white p-3 text-left" @click="pwVisible = true">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-soft text-brand-800">
          <van-icon name="shield-o" size="17" />
        </span>
        <span class="min-w-0">
          <span class="block text-sm font-semibold leading-5 text-primary">修改密码</span>
          <span class="block truncate text-[11px] leading-4 text-muted">定期更换更安全</span>
        </span>
      </button>
    </section>

    <div class="mt-3 space-y-2.5 px-4">
      <div ref="resumeSection">
        <ResumeLibrary />
      </div>

      <section class="rounded-xl bg-white shadow-sm profile-menu">
        <van-cell title="我的通知" icon="chat-o" is-link @click="notifVisible = true">
          <template #value>
            <span v-if="notifUnread > 0" class="admin-notification-badge">{{ notifUnread > 99 ? "99+" : notifUnread }}</span>
          </template>
        </van-cell>
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
