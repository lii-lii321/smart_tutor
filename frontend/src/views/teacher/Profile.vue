<script setup lang="ts">
/**
 * 个人中心：教员个人资产聚合页。
 *
 * 结构（2026-10-29 去臃肿改版，数据全部来自真实端点，逻辑与旧版一一对应）：
 *   身份卡（认证院校标签 + 常驻地 + 个人简介）
 *   → 数据卡（资产统计 4 格 + 我的投递 5 桶，两段合一减少盒层）
 *   → 订阅找单（默认折叠为一行摘要，点开展开编辑器）
 *   → 功能菜单（单列分组行：简历/费用/评价/改密/通知/帮助）
 *   → 简历库内嵌区块 + 风险区（退出/注销）。
 *
 * 口径说明：本产品信息费由教员支付、课酬走线下，平台没有"教员收入"数据，
 * 资金侧统计用「累计支付」（定金+尾款信息费），不虚构收入。
 */
import { computed, nextTick, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { showToast } from "vant";
import { useAuthStore } from "@/stores/auth";
import { notificationsApi } from "@/api/notifications";
import { applicationsApi } from "@/api/applications";
import { financialApi } from "@/api/financial";
import { publicApi, type Scorecard } from "@/api/public";
import { subscriptionsApi, type TeacherSubscription } from "@/api/subscriptions";
import { formatMoney } from "@/utils/format";
import { getApiErrorMessage } from "@/utils/apiError";
import type { ApplicationStatus } from "@/api/types";
import TeacherTabbar from "@/components/TeacherTabbar.vue";
import ResumeLibrary from "@/components/teacher/profile/ResumeLibrary.vue";
import NotificationList from "@/components/NotificationList.vue";
import FeesPopup from "@/components/teacher/profile/FeesPopup.vue";
import ReviewsPopup from "@/components/teacher/profile/ReviewsPopup.vue";
import ProfileEditPopup from "@/components/teacher/profile/ProfileEditPopup.vue";
import PasswordPopup from "@/components/teacher/profile/PasswordPopup.vue";
import DeactivatePopup from "@/components/teacher/profile/DeactivatePopup.vue";
import { appConfirm } from "@/composables/appConfirm";
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
// 首拉期间用骨架屏占位，替代先闪 "—" 再跳数字；未登录不进加载流程，直接落静态态
const statsLoading = ref(auth.isLoggedIn);

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

// 数字滚动：骨架屏落定后统计值从 0 缓动到目标（"¥270.00" 只滚数字部分，
// "—" 等无数字值原样展示）。纯展示层动效，不改任何数据口径。
const displayed = ref<Record<string, string>>({});
function animateStats() {
  for (const s of stats.value) {
    const m = s.value.match(/-?\d[\d,]*(\.\d+)?/);
    const target = m ? parseFloat(m[0].replace(/,/g, "")) : NaN;
    if (!m || Number.isNaN(target)) {
      displayed.value[s.key] = s.value;
      continue;
    }
    const decimals = m[1] ? m[1].length - 1 : 0;
    const at = m.index ?? 0;
    const prefix = s.value.slice(0, at);
    const suffix = s.value.slice(at + m[0].length);
    const render = (v: number) => {
      displayed.value[s.key] = prefix + v.toFixed(decimals) + suffix;
    };
    const dur = 750;
    const start = performance.now();
    render(0);
    const step = (now: number) => {
      const p = Math.min((now - start) / dur, 1);
      render(target * (1 - Math.pow(1 - p, 3)));
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
}
watch(statsLoading, (v) => {
  if (!v) nextTick(animateStats);
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

// ── 订阅找单：默认折叠为一行摘要（科目·学段·课酬下限），点开展开编辑器；
// 开关拨动仍即时保存，与旧版行为一致 ──
const SUBSCRIBE_SUBJECTS = ["数学", "英语", "语文", "物理", "化学", "生物", "历史", "地理", "政治"];
const SUBSCRIBE_GRADES = ["小学", "初中", "高中"];
const subscription = ref<TeacherSubscription>({
  enabled: false,
  subjects: [],
  grades: [],
  min_base_price: null,
  updated_at: null,
});
const subSaving = ref(false);
const subOpen = ref(false);
const minPriceInput = ref<string>("");

const subSummary = computed(() => {
  const s = subscription.value;
  if (!s.enabled) return "已关闭 · 开启后匹配新单会提醒你";
  const parts: string[] = [];
  if (s.subjects.length) parts.push(s.subjects.join("、"));
  if (s.grades.length) parts.push(s.grades.join("/"));
  if (s.min_base_price != null) parts.push(`≥¥${s.min_base_price}`);
  return parts.length ? parts.join(" · ") : "已开启 · 未设偏好";
});

function loadSubscription() {
  subscriptionsApi
    .getMine()
    .then((sub) => {
      subscription.value = sub;
      minPriceInput.value = sub.min_base_price != null ? String(sub.min_base_price) : "";
    })
    .catch(() => {
      // 加载失败保持默认关闭态，保存时会整体覆盖
    });
}

function toggleChip(list: string[], value: string) {
  const index = list.indexOf(value);
  if (index >= 0) list.splice(index, 1);
  else list.push(value);
}

async function saveSubscription() {
  if (subSaving.value) return;
  // 防御 type=number 输入框的 v-model 数字/空串双态：统一转数字再校验
  const raw = minPriceInput.value;
  const minPrice = raw == null || String(raw).trim() === "" ? null : Number(raw);
  if (minPrice != null && (Number.isNaN(minPrice) || minPrice < 0)) {
    showToast("课酬下限请填非负数字");
    return;
  }
  subSaving.value = true;
  try {
    const saved = await subscriptionsApi.saveMine({
      enabled: subscription.value.enabled,
      subjects: subscription.value.subjects,
      grades: subscription.value.grades,
      min_base_price: minPrice,
    });
    subscription.value = saved;
    showToast(saved.enabled ? "订阅已保存，匹配的新单会通知你" : "订阅已关闭");
  } catch (e) {
    showToast(getApiErrorMessage(e, "保存失败，请稍后重试"));
  } finally {
    subSaving.value = false;
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
  // 结束后即使部分端点失败也如实显示 —，不再回到骨架屏
  statsLoading.value = false;
}

// 简历库是内嵌区块（非弹层）：菜单行平滑滚动定位过去
const resumeSection = ref<HTMLDivElement | null>(null);
function scrollToResume() {
  resumeSection.value?.scrollIntoView({ behavior: "smooth", block: "start" });
}

onMounted(async () => {
  if (auth.isLoggedIn) {
    if (!auth.teacher) {
      try {
        await auth.fetchMe();
      } catch {
        // 拉取失败不阻断统计加载：statsLoading 必须能落定，否则骨架屏永久卡住
      }
    }
    loadBadges();
    loadAssets();
    loadSubscription();
  }
});

async function handleLogout() {
  // 二次确认：登出会丢失未提交的表单内容，与删简历/注销同一风险梯度
  const ok = await appConfirm({
    title: "退出登录？",
    message: "退出后需重新登录才能查看投递与接单，未提交的内容将丢失。",
    confirmText: "退出登录",
    danger: true,
  });
  if (!ok) return;
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
    <section class="st-in st-d1 mx-4 mt-2.5 rounded-2xl border border-default bg-white px-4 py-4 shadow-sm lg:mx-auto lg:max-w-2xl">
      <div class="flex items-center gap-3">
        <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-surface-soft">
          <van-icon name="manager-o" size="24" color="var(--st-brand-800)" />
        </div>
        <div class="min-w-0 flex-1 text-primary">
          <div class="flex flex-wrap items-center gap-1.5">
            <span class="text-lg font-bold leading-6">{{ auth.teacher?.name || (auth.isLoggedIn ? "已登录" : "未登录") }}</span>
            <span
              v-if="auth.teacher?.is_985 || auth.teacher?.is_211 || auth.teacher?.is_double_first_class || auth.teacher?.is_985_211"
              class="rounded-full bg-brand-50 px-1.5 py-0.5 text-caption font-medium leading-4 text-brand-700"
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
          class="shrink-0 rounded-lg bg-surface-soft px-3 py-1.5 text-xs text-secondary transition active:scale-95 active:bg-border-strong/40"
          @click="profileVisible = true"
        >
          编辑资料
        </button>
      </div>
      <div class="mt-2 flex flex-wrap gap-1.5">
        <span v-if="auth.teacher?.is_985" class="rounded-full bg-brand-50 px-2.5 py-0.5 text-caption leading-4 text-brand-700">985</span>
        <span v-if="auth.teacher?.is_211" class="rounded-full bg-brand-50 px-2.5 py-0.5 text-caption leading-4 text-brand-700">211</span>
        <span v-if="auth.teacher?.is_double_first_class" class="rounded-full bg-brand-50 px-2.5 py-0.5 text-caption leading-4 text-brand-700">双一流</span>
        <span
          v-if="auth.teacher?.is_985_211 && !auth.teacher?.is_985 && !auth.teacher?.is_211"
          class="rounded-full bg-brand-50 px-2.5 py-0.5 text-caption leading-4 text-brand-700"
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

    <!-- 数据卡：资产统计 + 我的投递两段合一（2026-10-29 去臃肿：4 个独立小盒并成一段）；
         统计值带数字滚动进场 -->
    <section class="st-card st-in st-d2 mx-4 mt-3 p-4 lg:mx-auto lg:max-w-2xl">
      <template v-if="statsLoading">
        <van-skeleton title :row="2" title-width="60%" row-width="80%" />
      </template>
      <template v-else>
        <div class="grid grid-cols-4 divide-x divide-default">
          <div v-for="s in stats" :key="s.key" class="min-w-0 px-1 text-center">
            <div class="truncate text-lg font-bold leading-6 text-primary tabular-nums">{{ displayed[s.key] ?? s.value }}</div>
            <div class="mt-0.5 text-caption leading-4 text-secondary">{{ s.label }}</div>
            <div class="mt-0.5 truncate text-caption text-muted">{{ s.sub }}</div>
          </div>
        </div>

        <div class="my-3 border-t border-dashed border-default"></div>

        <div class="mb-2 flex items-center justify-between">
          <h3 class="text-sm font-bold text-primary">我的投递</h3>
          <button class="text-xs font-medium text-link transition active:opacity-60" @click="router.push('/teacher/applications')">
            查看全部 →
          </button>
        </div>
        <div class="grid grid-cols-5 gap-1.5 text-center">
          <button
            v-for="b in orderBuckets"
            :key="b.label"
            class="rounded-lg bg-surface-soft/60 py-2 transition active:scale-95 active:bg-surface-soft"
            :title="b.hint"
            @click="router.push('/teacher/applications')"
          >
            <div class="text-base font-bold leading-6" :class="b.count > 0 ? 'text-brand-800' : 'text-muted'">
              {{ b.count }}
            </div>
            <div class="mt-0.5 text-caption text-muted">{{ b.label }}</div>
          </button>
        </div>
      </template>
    </section>

    <!-- 订阅找单：默认折叠为一行摘要，点开展开编辑器（开关拨动仍即时保存） -->
    <section class="st-card st-in st-d3 mx-4 mt-3 p-4 lg:mx-auto lg:max-w-2xl">
      <div
        class="flex cursor-pointer items-center gap-3"
        role="button"
        :aria-expanded="subOpen"
        @click="subOpen = !subOpen"
      >
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent-ink">
          <van-icon name="bell" size="16" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block text-sm font-semibold leading-5 text-primary">订阅找单</span>
          <span class="block truncate text-caption leading-4 text-muted">{{ subSummary }}</span>
        </span>
        <span class="shrink-0" @click.stop>
          <van-switch v-model="subscription.enabled" size="20px" @change="saveSubscription" />
        </span>
        <van-icon
          name="arrow-down"
          size="14"
          class="shrink-0 text-muted transition-transform duration-300"
          :class="subOpen ? 'rotate-180' : ''"
        />
      </div>

      <div class="sub-collapse" :class="{ 'sub-open': subOpen }">
        <div class="sub-inner">
          <div class="mt-3 space-y-2.5 border-t border-dashed border-default pt-3">
            <p class="text-caption leading-4 text-muted">
              设置偏好后，新入库的匹配订单会通过「我的通知」提醒你
            </p>
            <div>
              <div class="mb-1.5 text-caption font-medium text-secondary">科目（可多选，不限则留空）</div>
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="s in SUBSCRIBE_SUBJECTS"
                  :key="s"
                  class="rounded-full px-2.5 py-1 text-caption font-medium transition active:scale-95"
                  :class="
                    subscription.subjects.includes(s)
                      ? 'bg-brand-800 text-white'
                      : 'bg-surface-soft text-secondary'
                  "
                  @click="toggleChip(subscription.subjects, s)"
                >
                  {{ s }}
                </button>
              </div>
            </div>
            <div>
              <div class="mb-1.5 text-caption font-medium text-secondary">学段</div>
              <div class="flex flex-wrap gap-1.5">
                <button
                  v-for="g in SUBSCRIBE_GRADES"
                  :key="g"
                  class="rounded-full px-2.5 py-1 text-caption font-medium transition active:scale-95"
                  :class="
                    subscription.grades.includes(g)
                      ? 'bg-brand-800 text-white'
                      : 'bg-surface-soft text-secondary'
                  "
                  @click="toggleChip(subscription.grades, g)"
                >
                  {{ g }}
                </button>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <span class="shrink-0 text-caption font-medium text-secondary">单次课酬不低于</span>
              <input
                v-model="minPriceInput"
                type="text"
                inputmode="decimal"
                placeholder="不限"
                class="w-20 rounded-lg border border-default bg-surface-soft/60 px-2 py-1 text-caption text-primary focus:border-brand-500 focus:bg-white focus:outline-none"
              />
              <span class="text-caption text-muted">元 / 次</span>
            </div>
            <div class="text-right">
              <button
                class="rounded-full bg-ink px-4 py-1.5 text-caption font-semibold text-white transition active:scale-95 disabled:opacity-50"
                :disabled="subSaving"
                @click="saveSubscription"
              >
                {{ subSaving ? "保存中…" : "保存偏好" }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 功能菜单：单列分组行（原 2×2 tile + 两个 cell 卡收敛为一张卡） -->
    <section class="st-card st-in st-d4 mx-4 mt-3 divide-y divide-default overflow-hidden lg:mx-auto lg:max-w-2xl">
      <button class="flex w-full items-center gap-3 px-4 py-3 text-left transition active:bg-surface-soft" @click="scrollToResume">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-soft text-brand-800">
          <van-icon name="notes-o" size="17" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block text-sm font-semibold leading-5 text-primary">我的简历</span>
          <span class="block truncate text-caption leading-4 text-muted">完善资料，提升匹配率</span>
        </span>
        <van-icon name="arrow" size="14" class="shrink-0 text-muted" />
      </button>
      <button class="flex w-full items-center gap-3 px-4 py-3 text-left transition active:bg-surface-soft" @click="feesVisible = true">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-soft text-brand-800">
          <van-icon name="balance-pay" size="17" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block text-sm font-semibold leading-5 text-primary">我的费用</span>
          <span class="block truncate text-caption leading-4 text-muted">
            {{ feeTotals ? `累计支付 ${formatMoney(feeTotals.total_paid)}` : "定金与尾款流水" }}
          </span>
        </span>
        <van-icon name="arrow" size="14" class="shrink-0 text-muted" />
      </button>
      <button class="flex w-full items-center gap-3 px-4 py-3 text-left transition active:bg-surface-soft" @click="reviewsVisible = true">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-soft text-brand-800">
          <van-icon name="star-o" size="17" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block text-sm font-semibold leading-5 text-primary">收到的评价</span>
          <span class="block truncate text-caption leading-4 text-muted">
            {{ reviewCount > 0 ? `${reviewCount} 条${scorecard?.avg_rating != null ? ` · 均分 ${scorecard.avg_rating}★` : ""}` : "来自成交订单" }}
          </span>
        </span>
        <van-icon name="arrow" size="14" class="shrink-0 text-muted" />
      </button>
      <button class="flex w-full items-center gap-3 px-4 py-3 text-left transition active:bg-surface-soft" @click="pwVisible = true">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-soft text-brand-800">
          <van-icon name="shield-o" size="17" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block text-sm font-semibold leading-5 text-primary">修改密码</span>
          <span class="block truncate text-caption leading-4 text-muted">定期更换更安全</span>
        </span>
        <van-icon name="arrow" size="14" class="shrink-0 text-muted" />
      </button>
      <button class="flex w-full items-center gap-3 px-4 py-3 text-left transition active:bg-surface-soft" @click="notifVisible = true">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-soft text-brand-800">
          <van-icon name="chat-o" size="17" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block text-sm font-semibold leading-5 text-primary">我的通知</span>
          <span class="block truncate text-caption leading-4 text-muted">
            {{ notifUnread > 0 ? "投递进展与新单提醒" : "暂无新通知" }}
          </span>
        </span>
        <span
          v-if="notifUnread > 0"
          class="flex h-4 min-w-4 shrink-0 items-center justify-center rounded-full bg-accent px-1 text-caption font-bold text-ink"
        >
          {{ notifUnread > 99 ? "99+" : notifUnread }}
        </span>
        <van-icon v-else name="arrow" size="14" class="shrink-0 text-muted" />
      </button>
      <button class="flex w-full items-center gap-3 px-4 py-3 text-left transition active:bg-surface-soft" @click="router.push('/teacher/help')">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-soft text-brand-800">
          <van-icon name="question-o" size="17" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block text-sm font-semibold leading-5 text-primary">帮助中心</span>
          <span class="block truncate text-caption leading-4 text-muted">规则解读 · 问 AI</span>
        </span>
        <van-icon name="arrow" size="14" class="shrink-0 text-muted" />
      </button>
    </section>

    <!-- 简历库/风险区：宽屏限宽与上方卡片对齐 -->
    <div class="st-in st-d5 mt-3 px-4 lg:mx-auto lg:max-w-2xl lg:px-0">
      <div ref="resumeSection">
        <ResumeLibrary />
      </div>
    </div>

    <section class="st-card st-in st-d6 mx-4 mt-3 divide-y divide-default overflow-hidden lg:mx-auto lg:max-w-2xl">
      <button class="flex w-full items-center gap-3 px-4 py-3 text-left transition active:bg-surface-soft" @click="handleLogout">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-surface-soft text-secondary">
          <van-icon name="revoke" size="17" />
        </span>
        <span class="min-w-0 flex-1 text-sm font-semibold leading-5 text-primary">退出登录</span>
      </button>
      <button class="flex w-full items-center gap-3 px-4 py-3 text-left transition active:bg-danger-soft/60" @click="deactivateVisible = true">
        <span class="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-danger-soft text-danger-deep">
          <van-icon name="warn-o" size="17" />
        </span>
        <span class="min-w-0 flex-1 text-sm font-semibold leading-5 text-danger-deep">注销账号</span>
      </button>
    </section>

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
/* 订阅找单折叠动画：grid-template-rows 0fr→1fr，无需 JS 测高 */
.sub-collapse {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.32s ease;
}
.sub-collapse.sub-open {
  grid-template-rows: 1fr;
}
.sub-inner {
  min-height: 0;
  overflow: hidden;
}

/* 进场 stagger：区块依次淡入上浮（尊重系统减弱动效偏好） */
.st-in {
  opacity: 0;
  transform: translateY(12px);
  animation: st-fade-up 0.5s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}
.st-d1 { animation-delay: 0.03s; }
.st-d2 { animation-delay: 0.09s; }
.st-d3 { animation-delay: 0.15s; }
.st-d4 { animation-delay: 0.21s; }
.st-d5 { animation-delay: 0.27s; }
.st-d6 { animation-delay: 0.33s; }
@keyframes st-fade-up {
  to {
    opacity: 1;
    transform: none;
  }
}
@media (prefers-reduced-motion: reduce) {
  .st-in {
    animation: none;
    opacity: 1;
    transform: none;
  }
}
</style>
