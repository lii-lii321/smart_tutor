<script setup lang="ts">
/**
 * 教员管理（人力池视角，2026-09-30 按概念稿方向重构）：
 * 老板三问——谁最近还在动、谁干净、谁该小心。
 * - 顶部概览数字 = 筛选器（全部/可推单/已拉黑，点击即筛），底部给"近 30 天投递过"的真实活跃定义
 * - 每行右上角最近投递相对时间（last_applied_at，7 天内绿色）；成交率替代原始计数（≥60% 转绿）
 * - 违约 0 是干净（常规字重），>0 整行琥珀；已拉黑整行降透明 + ⊘ 头像，可追溯不争注意力
 * - 拉黑/移出收进行内「⋯」菜单（破坏性操作不占最高对比度）
 * 数据全部来自 /tenants/my-teachers + blacklist 端点；排序/搜索/筛选为前端侧（量级几十人，
 * usePagedList 50/页——"成交多/评分高"只在已加载分页内生效，量大需下沉 SQL）。
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { useRouter } from "vue-router";
import { tenantsApi, type MyTeacher } from "@/api/tenants";
import client from "@/api/client";
import { todayStr, parseDbTime } from "@/utils/format";
import { copyContact } from "@/utils/clipboard";
import { formatDateTime } from "@/utils/format";
import AdminShell from "@/components/admin/AdminShell.vue";
import { showToast } from "vant";
import { appConfirm } from "@/composables/appConfirm";
import { usePagedList } from "@/composables/usePagedList";

const router = useRouter();

const teachersPaged = usePagedList<MyTeacher>(
  (page, pageSize) =>
    tenantsApi.myTeachers(page, pageSize).then((list) => ({ items: list })),
  { pageSize: 50 }
);
const {
  items: teachers,
  loading: teachersLoading,
  hasMore: teachersHasMore,
  load: loadTeachers,
  loadMore: loadMoreTeachers,
} = teachersPaged;

async function loadTeachersSafe() {
  try {
    await loadTeachers();
  } catch {
    teachers.value = [];
  }
}
loadTeachersSafe();

// ⋯ 菜单点空白关闭：document 捕获阶段监听（先于弹层内部冒泡逻辑）
onMounted(() => document.addEventListener("click", onDocClickCloseMenu, true));
onUnmounted(() => document.removeEventListener("click", onDocClickCloseMenu, true));

async function loadMoreTeachersSafe() {
  try {
    await loadMoreTeachers();
  } catch {
    showToast("加载更多失败，请重试");
  }
}

// ── 概览：三个可点数字即筛选器 ──
const searchText = ref("");
const listFilter = ref<"all" | "available" | "blacklisted">("all");
const overviewFilters: Array<{ key: "all" | "available" | "blacklisted"; label: string }> = [
  { key: "all", label: "全部教员" },
  { key: "available", label: "可推单" },
  { key: "blacklisted", label: "已拉黑" },
];

const availableCount = computed(() => teachers.value.filter((t) => !t.is_blacklisted).length);
const blacklistedCount = computed(() => teachers.value.filter((t) => t.is_blacklisted).length);
const totalApplications = computed(() =>
  teachers.value.reduce((sum, t) => sum + Number(t.applications_total || 0), 0),
);
const totalDeals = computed(() =>
  teachers.value.reduce((sum, t) => sum + Number(t.completed_count || 0), 0),
);
/** "活跃"的真实定义：近 30 天有投递动作的人数 */
const recent30Count = computed(() => {
  const cutoff = Date.now() - 30 * 86400000;
  return teachers.value.filter((t) => {
    if (!t.last_applied_at) return false;
    const time = parseDbTime(t.last_applied_at).getTime();
    return Number.isFinite(time) && time >= cutoff;
  }).length;
});

// ── 搜索 + 排序（前端侧；排序只在已加载分页内生效）──
const sortKey = ref<"recent" | "deals" | "rating" | "violations">("recent");
const sortOptions: Array<{ key: "recent" | "deals" | "rating" | "violations"; label: string }> = [
  { key: "recent", label: "最近投递" },
  { key: "deals", label: "成交多" },
  { key: "rating", label: "评分高" },
  { key: "violations", label: "违约多" },
];

const filteredTeachers = computed(() => {
  const kw = searchText.value.trim().toLowerCase();
  let list = teachers.value.filter((t) => {
    if (listFilter.value === "available" && t.is_blacklisted) return false;
    if (listFilter.value === "blacklisted" && !t.is_blacklisted) return false;
    if (!kw) return true;
    return (
      t.name.toLowerCase().includes(kw) ||
      (t.phone || "").includes(kw) ||
      (t.school || "").toLowerCase().includes(kw)
    );
  });
  // 已拉黑永远排在最下面（出局者不争注意力），其余按所选口径排
  list = [...list].sort((a, b) => {
    if (a.is_blacklisted !== b.is_blacklisted) return a.is_blacklisted ? 1 : -1;
    if (sortKey.value === "recent") {
      const ta = a.last_applied_at ? parseDbTime(a.last_applied_at).getTime() : 0;
      const tb = b.last_applied_at ? parseDbTime(b.last_applied_at).getTime() : 0;
      return tb - ta;
    }
    if (sortKey.value === "deals") return b.completed_count - a.completed_count;
    if (sortKey.value === "rating") return (b.avg_rating ?? -1) - (a.avg_rating ?? -1);
    if (sortKey.value === "violations") return b.violation_count - a.violation_count;
    return 0;
  });
  return list;
});

// ── 行级派生：最近投递相对时间 / 成交率 / 状态标 ──
function relativeApplied(t: string | null | undefined): { text: string; fresh: boolean } | null {
  if (!t) return null;
  const then = parseDbTime(t).getTime();
  if (!Number.isFinite(then)) return null;
  const diffDays = Math.floor((Date.now() - then) / 86400000);
  const sameDay = new Date().toDateString() === new Date(then).toDateString();
  if (sameDay || diffDays < 1) return { text: "今天投递", fresh: true };
  return { text: `${diffDays} 天前`, fresh: diffDays <= 7 };
}

/** 成交率 = 成交 / 投递；无投递返回 null（显示 —） */
function dealRate(t: MyTeacher): number | null {
  const total = Number(t.applications_total || 0);
  if (total <= 0) return null;
  return Math.round((Number(t.completed_count || 0) / total) * 100);
}

function rateClass(t: MyTeacher): string {
  const rate = dealRate(t);
  if (rate == null) return "text-secondary";
  return rate >= 60 ? "text-success-deep" : "text-primary";
}

type RowState = "available" | "violated" | "blacklisted";
function rowState(t: MyTeacher): RowState {
  if (t.is_blacklisted) return "blacklisted";
  if (t.violation_count > 0) return "violated";
  return "available";
}

function stateChip(t: MyTeacher): { text: string; cls: string } {
  const state = rowState(t);
  if (state === "blacklisted") return { text: "已拉黑", cls: "bg-surface-soft text-muted" };
  if (state === "violated") return { text: `${t.violation_count} 次违约`, cls: "bg-warning-soft text-warning-deep" };
  return { text: "可推单", cls: "bg-success-soft text-success-deep" };
}

// ── 拉黑/移出（收进行内 ⋯ 菜单；确认弹窗文案原样保留）──
// Vant Popover 默认的外部点击关闭在本环境不可靠（实测点空白不收），
// 改为受控模式：openMenuId 单开 + document 捕获监听点空白关闭。
const openMenuId = ref<number | null>(null);

function toggleMenu(teacher: MyTeacher) {
  openMenuId.value = openMenuId.value === teacher.teacher_id ? null : teacher.teacher_id;
}

function closeMenu() {
  openMenuId.value = null;
}

/** 点空白关闭 ⋯ 菜单：捕获阶段执行，点在弹层内或触发按钮上则忽略 */
function onDocClickCloseMenu(e: MouseEvent) {
  if (openMenuId.value == null) return;
  const target = e.target as HTMLElement | null;
  if (!target) return;
  if (target.closest(".van-popover") || target.closest("[data-menu-trigger]")) return;
  closeMenu();
}

function menuActions(t: MyTeacher) {
  return [{ text: t.is_blacklisted ? "移出黑名单" : "拉黑", danger: !t.is_blacklisted }];
}

async function onMenuSelect(teacher: MyTeacher) {
  closeMenu();
  await toggleBlacklist(teacher);
}

// ── 教员详情弹层：点卡片看全部信息 ──
const detailVisible = ref(false);
const detailTeacher = ref<MyTeacher | null>(null);

function openDetail(teacher: MyTeacher) {
  detailTeacher.value = teacher;
  detailVisible.value = true;
}

async function toggleBlacklistFromDetail() {
  if (!detailTeacher.value) return;
  await toggleBlacklist(detailTeacher.value);
  // 列表已重拉（对象为新生成），弹层里显示的是旧引用——关闭避免展示过期状态
  detailVisible.value = false;
}

async function toggleBlacklist(teacher: MyTeacher) {
  const action = teacher.is_blacklisted ? "移出黑名单" : "拉黑";
  const ok = await appConfirm({
    title: `${action}？`,
    message: teacher.is_blacklisted
      ? `移出后「${teacher.name}」可重新投递本中介的订单。`
      : teacher.violation_count > 0
        ? `该教员有 ${teacher.violation_count} 次违约记录。拉黑后其待审投递将被拒绝，且无法再投递本中介订单。`
        : `拉黑后「${teacher.name}」的待审投递将被拒绝，且无法再投递本中介订单。`,
    confirmText: action,
    danger: !teacher.is_blacklisted,
  });
  if (!ok) return;
  try {
    if (teacher.is_blacklisted) {
      await tenantsApi.unblacklist(teacher.teacher_id);
      showToast("已移出黑名单");
    } else {
      await tenantsApi.blacklist(teacher.teacher_id, "中介手动拉黑");
      showToast("已拉黑");
    }
    await loadTeachers();
  } catch (e) {
    showToast(getApiErrorMessage(e, "操作失败"));
  }
}

// ── 导出 CSV ──
const exporting = ref(false);

async function exportTeachers() {
  exporting.value = true;
  try {
    const res = await client.get(tenantsApi.myTeachersExportUrl(), { responseType: "blob" });
    const url = URL.createObjectURL(res.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = `我的教员_${todayStr()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  } catch {
    showToast("导出失败，请重试");
  } finally {
    exporting.value = false;
  }
}
</script>

<template>
  <AdminShell>
    <van-nav-bar title="教员管理" left-arrow @click-left="router.push('/admin/dashboard')" />

    <div class="mx-auto w-full max-w-3xl px-4">
    <!-- 标题 + 导出（说明句移除：默认认知不占版面） -->
    <div class="mt-2 flex items-center justify-between">
      <h1 class="text-[20px] font-bold leading-7 text-primary">我的教员</h1>
      <button
        v-if="teachers.length > 0"
        class="inline-flex items-center gap-1 text-[13px] font-medium text-secondary disabled:opacity-50"
        :disabled="exporting"
        @click="exportTeachers"
      >
        <van-icon name="down" size="13" />
        {{ exporting ? "导出中..." : "导出" }}
      </button>
    </div>

    <!-- 概览数字 = 筛选器；底部一行给真实的"活跃"定义 -->
    <section class="mt-3 overflow-hidden rounded-2xl border border-default bg-surface shadow-card">
      <div class="grid grid-cols-3">
        <button
          v-for="f in overviewFilters"
          :key="f.key"
          class="px-2 py-3.5 text-center transition-colors"
          :class="[
            listFilter === f.key ? 'bg-brand-800 text-white' : 'bg-surface text-primary',
            f.key !== 'blacklisted' ? 'border-r border-default' : '',
          ]"
          @click="listFilter = f.key"
        >
          <span class="block text-[22px] font-bold leading-7 tabular-nums">
            {{ f.key === "all" ? teachers.length : f.key === "available" ? availableCount : blacklistedCount }}
          </span>
          <span
            class="mt-0.5 block text-[11px]"
            :class="listFilter === f.key ? 'text-white/75' : 'text-muted'"
          >
            {{ f.label }}
          </span>
        </button>
      </div>
      <div class="flex items-center justify-between border-t border-default px-4 py-2.5 text-[11px] leading-4">
        <span
          v-if="recent30Count > 0"
          class="font-medium text-success-deep"
        >{{ recent30Count }} 人在近 30 天投递过</span>
        <span v-else class="text-muted">近 30 天没有教员投递</span>
        <span class="shrink-0 text-muted">共 {{ totalApplications }} 次投递 · {{ totalDeals }} 单成交</span>
      </div>
    </section>

    <!-- 搜索 -->
    <van-field
      v-model="searchText"
      placeholder="搜索姓名 / 手机号 / 学校"
      clearable
      class="mt-3 rounded-xl border border-default"
    />

    <!-- 排序：单独一行 + 标签，与筛选明确区分 -->
    <div class="mt-3 flex items-center gap-2 text-[12px]">
      <span class="shrink-0 text-muted">排序</span>
      <span class="h-3 w-px shrink-0 bg-default" />
      <button
        v-for="opt in sortOptions"
        :key="opt.key"
        class="px-0.5"
        :class="sortKey === opt.key ? 'font-bold text-primary' : 'text-muted'"
        @click="sortKey = opt.key"
      >
        {{ opt.label }}
      </button>
    </div>

    <!-- 名录 -->
    <div class="mt-3 space-y-2 pb-2">
      <div v-if="teachersLoading" class="flex justify-center py-6">
        <van-loading color="#334155" />
      </div>
      <div v-else-if="teachers.length === 0" class="rounded-2xl border border-default bg-surface p-8 text-center text-sm text-muted shadow-card">
        还没有教员投递过你的订单。收到第一份投递后，教员会自动进入这里。
      </div>
      <div v-else-if="filteredTeachers.length === 0" class="rounded-2xl border border-default bg-surface p-8 text-center text-sm text-muted shadow-card">
        没有符合条件的教员
      </div>
      <div v-else class="space-y-2">
        <article
          v-for="teacher in filteredTeachers"
          :key="teacher.teacher_id"
          class="cursor-pointer rounded-2xl border bg-surface p-3.5"
          :class="rowState(teacher) === 'violated'
            ? 'border-warning-mid bg-warning-soft/50'
            : 'border-default shadow-sm'"
          @click="openDetail(teacher)"
        >
          <div class="flex items-start gap-3">
            <!-- 头像：首字；已拉黑 ⊘ -->
            <span
              class="grid h-10 w-10 shrink-0 place-items-center rounded-xl text-[15px] font-bold"
              :class="teacher.is_blacklisted ? 'bg-surface-soft text-muted' : 'bg-brand-50 text-brand-800'"
            >
              <van-icon v-if="teacher.is_blacklisted" name="close" size="16" />
              <template v-else>{{ (teacher.name || "?").slice(0, 1) }}</template>
            </span>

            <div class="min-w-0 flex-1">
              <div class="flex items-center justify-between gap-2">
                <span class="flex min-w-0 items-center gap-1.5">
                  <span
                    class="truncate text-[15px] font-bold"
                    :class="teacher.is_blacklisted ? 'text-secondary' : 'text-primary'"
                  >{{ teacher.name }}</span>
                  <span
                    class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium leading-4"
                    :class="stateChip(teacher).cls"
                  >{{ stateChip(teacher).text }}</span>
                </span>
                <span
                  v-if="relativeApplied(teacher.last_applied_at)"
                  class="shrink-0 text-[11px] font-medium"
                  :class="relativeApplied(teacher.last_applied_at)!.fresh ? 'text-success-deep' : 'text-muted'"
                >
                  {{ relativeApplied(teacher.last_applied_at)!.text }}
                </span>
              </div>
              <div class="mt-0.5 truncate text-[12px] text-muted">
                {{ [teacher.school, teacher.gender === "female" ? "女" : teacher.gender === "male" ? "男" : ""].filter(Boolean).join(" · ") || "—" }}
              </div>
            </div>
          </div>

          <!-- 信用行：已拉黑=终止说明+移出入口；正常=可比较口径+⋯ 菜单 -->
          <div class="mt-2 border-t border-default pt-2">
            <div class="flex items-center justify-between gap-2">
              <template v-if="teacher.is_blacklisted">
                <span class="text-[12px] leading-5 text-muted">已停止投递本中介订单</span>
              </template>
              <template v-else>
                <span class="text-[11px] text-muted">拉黑仅对本中介生效</span>
              </template>
              <van-popover
                :show="openMenuId === teacher.teacher_id"
                trigger="manual"
                placement="left"
                :actions="menuActions(teacher)"
                @select="onMenuSelect(teacher)"
              >
                <template #reference>
                  <button
                    data-menu-trigger
                    class="shrink-0 rounded px-2 py-0.5 text-[13px] font-bold leading-5 text-muted"
                    aria-label="更多操作"
                    @click.stop="toggleMenu(teacher)"
                  >···</button>
                </template>
              </van-popover>
            </div>
            <div
              v-if="!teacher.is_blacklisted"
              class="mt-1 flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-[12px]"
            >
              <span class="text-muted">投递 <b class="font-semibold text-secondary">{{ teacher.applications_total }}</b></span>
              <span aria-hidden="true" class="text-muted">·</span>
              <span class="text-muted">成交率 <b class="font-bold tabular-nums" :class="rateClass(teacher)">{{ dealRate(teacher) == null ? "—" : `${dealRate(teacher)}%` }}</b></span>
              <span aria-hidden="true" class="text-muted">·</span>
              <span class="text-muted">评分 <b v-if="teacher.avg_rating != null" class="font-semibold text-secondary">{{ teacher.avg_rating }}</b><b v-else class="font-medium text-muted">— 未评价</b></span>
              <span aria-hidden="true" class="text-muted">·</span>
              <span :class="teacher.violation_count > 0 ? 'text-danger-deep' : 'text-secondary'">违约 <b class="font-semibold">{{ teacher.violation_count }}</b></span>
            </div>
          </div>
        </article>

        <button
          v-if="teachersHasMore && !teachersLoading"
          class="w-full rounded-xl border border-default bg-surface py-2.5 text-xs font-medium text-secondary disabled:opacity-50"
          @click="loadMoreTeachersSafe"
        >
          加载更多教员
        </button>
        <div
          v-if="!teachersHasMore && teachers.length > 0"
          class="py-2 text-center text-xs text-muted"
        >
          共 {{ teachers.length }} 位教员 · 已全部显示
        </div>
      </div>
    </div>
    </div>

    <!-- 教员详情弹层：点击卡片查看全部信息 + 拉黑/移出操作 -->
    <van-popup
      v-model:show="detailVisible"
      position="bottom"
      round
      :style="{ maxHeight: '82vh' }"
    >
      <div
        v-if="detailTeacher"
        class="p-5 pb-[calc(20px+env(safe-area-inset-bottom))]"
      >
        <div class="flex items-center gap-3">
          <span
            class="grid h-12 w-12 shrink-0 place-items-center rounded-xl text-[17px] font-bold"
            :class="detailTeacher.is_blacklisted ? 'bg-surface-soft text-muted' : 'bg-brand-50 text-brand-800'"
          >
            <van-icon v-if="detailTeacher.is_blacklisted" name="close" size="18" />
            <template v-else>{{ (detailTeacher.name || "?").slice(0, 1) }}</template>
          </span>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-1.5">
              <span class="truncate text-[17px] font-bold text-primary">{{ detailTeacher.name }}</span>
              <span
                class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium leading-4"
                :class="stateChip(detailTeacher).cls"
              >{{ stateChip(detailTeacher).text }}</span>
            </div>
            <div class="mt-0.5 truncate text-xs text-muted">
              {{ [detailTeacher.school, detailTeacher.gender === "female" ? "女" : detailTeacher.gender === "male" ? "男" : ""].filter(Boolean).join(" · ") || "—" }}
            </div>
          </div>
        </div>

        <!-- 基本信息与信用明细 -->
        <div class="mt-4 space-y-2.5 text-sm">
          <div class="flex items-center justify-between gap-3">
            <span class="shrink-0 text-[12px] text-muted">手机号</span>
            <span class="flex min-w-0 items-center gap-2 text-secondary">
              <span class="truncate">{{ detailTeacher.phone || "—" }}</span>
              <button
                v-if="detailTeacher.phone"
                class="shrink-0 text-xs font-medium text-brand-700"
                @click="copyContact(detailTeacher.phone, '手机号已复制')"
              >
                复制
              </button>
            </span>
          </div>
          <div class="flex items-center justify-between gap-3 border-t border-dashed border-default pt-2.5">
            <span class="shrink-0 text-[12px] text-muted">最近投递</span>
            <span class="min-w-0 truncate text-secondary">
              <template v-if="relativeApplied(detailTeacher.last_applied_at)">
                {{ relativeApplied(detailTeacher.last_applied_at)!.text }}
                <template v-if="detailTeacher.last_applied_at">（{{ formatDateTime(detailTeacher.last_applied_at) }}）</template>
              </template>
              <template v-else>—</template>
            </span>
          </div>
          <div class="flex items-center justify-between gap-3 border-t border-dashed border-default pt-2.5">
            <span class="shrink-0 text-[12px] text-muted">投递次数</span>
            <span class="text-secondary">{{ detailTeacher.applications_total }}</span>
          </div>
          <div class="flex items-center justify-between gap-3 border-t border-dashed border-default pt-2.5">
            <span class="shrink-0 text-[12px] text-muted">成交数 / 成交率</span>
            <span class="text-secondary">
              {{ detailTeacher.completed_count }}
              <template v-if="dealRate(detailTeacher) != null"> · {{ dealRate(detailTeacher) }}%</template>
            </span>
          </div>
          <div class="flex items-center justify-between gap-3 border-t border-dashed border-default pt-2.5">
            <span class="shrink-0 text-[12px] text-muted">违约次数</span>
            <span :class="detailTeacher.violation_count > 0 ? 'text-danger-deep' : 'text-secondary'">
              {{ detailTeacher.violation_count }}
            </span>
          </div>
          <div class="flex items-center justify-between gap-3 border-t border-dashed border-default pt-2.5">
            <span class="shrink-0 text-[12px] text-muted">平均评分</span>
            <span class="text-secondary">
              <template v-if="detailTeacher.avg_rating != null">{{ detailTeacher.avg_rating }} ★</template>
              <template v-else>— 未评价</template>
            </span>
          </div>
        </div>

        <!-- 拉黑状态与操作 -->
        <div
          class="mt-4 rounded-xl p-3"
          :class="detailTeacher.is_blacklisted ? 'bg-surface-soft' : 'bg-danger-soft'"
        >
          <template v-if="detailTeacher.is_blacklisted">
            <p class="text-[12px] leading-5 text-muted">
              该教员已被拉黑，暂停投递本中介订单；移出后可重新投递（拉黑仅对本中介生效）。
            </p>
            <button
              class="mt-2 w-full rounded-lg bg-surface py-2 text-sm font-semibold text-secondary"
              @click="toggleBlacklistFromDetail"
            >
              移出黑名单
            </button>
          </template>
          <template v-else>
            <p class="text-[12px] leading-5 text-muted">
              拉黑后其待审投递将被拒绝，且无法再投递本中介订单；移出后可恢复。
            </p>
            <button
              class="mt-2 w-full rounded-lg bg-surface py-2 text-sm font-semibold text-danger-deep"
              @click="toggleBlacklistFromDetail"
            >
              拉黑该教员
            </button>
          </template>
        </div>
      </div>
    </van-popup>
  </AdminShell>
</template>
