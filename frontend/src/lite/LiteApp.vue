<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { showToast } from "vant";
import AppButton from "@/components/ui/AppButton.vue";
import AppEmpty from "@/components/ui/AppEmpty.vue";
import { loadAMap, locateCurrentPosition } from "@/utils/amap";
import { useAMap } from "@/composables/useAMap";
import type { PublicOrderBrief } from "@/api/types";
import { useLiteBoard, liteSortOptions, type LiteOrderItem } from "@/lite/composables/useLiteBoard";
import LiteOrderCard from "@/lite/components/LiteOrderCard.vue";
import LiteFilterSheet from "@/lite/components/LiteFilterSheet.vue";
import LiteOrderSheet from "@/lite/components/LiteOrderSheet.vue";

/**
 * 轻薄版橱窗单页：地图/列表双视图 + 筛选 + 详情弹层。
 * 只调 /public/* 免鉴权接口，无登录/投递/订阅。
 */
const mapRef = ref<HTMLDivElement | undefined>();
const MAP_CONTAINER_ID = "lite-map-container";
const map = useAMap({
  mapRef,
  containerId: MAP_CONTAINER_ID,
  onMarkerClick: (order) => openSheet(order),
});

const lite = useLiteBoard({ getMap: () => map.getMap() });
const { filters } = lite;

const activeView = ref<"map" | "list">("map");
const locating = ref(false);
const sheetVisible = ref(false);
const sheetOrderId = ref<number | null>(null);

const tenantName = computed(() => lite.board.value?.tenant_name ?? "");
const contactWechat = computed(() => lite.board.value?.contact_wechat ?? null);
const orders = computed<LiteOrderItem[]>(() => filters.filteredOrders.value as LiteOrderItem[]);

// ── 筛选弹层双向绑定（状态唯一来源在 useBoardFilters）──
const filterVisible = computed({
  get: () => filters.filterSheetVisible.value,
  set: (v: boolean) => (filters.filterSheetVisible.value = v),
});
const stage = computed({
  get: () => filters.selectedStage.value,
  set: (v: string) => {
    filters.selectedStage.value = v as typeof filters.selectedStage.value;
    lite.saveFilters();
  },
});
const subjects = computed({
  get: () => filters.selectedSubjects.value,
  set: (v: string[]) => {
    filters.selectedSubjects.value = v;
    lite.saveFilters();
  },
});
const city = computed({
  get: () => filters.selectedCity.value,
  set: (v: string) => {
    filters.selectedCity.value = v;
    if (v !== "all") {
      void filters.centerMapOnCity(v);
      // 距离参照链第二级：浏览器未定位成功时，用选中城市中心做距离基准
      // （批准计划：浏览器定位 > 城市中心 > null 沉底）
      void filters.fetchCityContext(v).then((ctx) => {
        if (ctx.center && !lite.distanceRefPoint.value) {
          lite.distanceRefPoint.value = ctx.center;
        }
      });
    }
    lite.saveFilters();
  },
});
const sort = computed({
  get: () => filters.sortMode.value,
  set: (v: string) => {
    filters.sortMode.value = v as typeof filters.sortMode.value;
    lite.saveFilters();
  },
});

function resetFilters() {
  filters.resetFilters();
  lite.saveFilters();
}

// ── 地图 ──
async function renderMapMarkers(fitView = true) {
  if (activeView.value !== "map" || !map.isReady()) return;
  await map.renderMarkers(orders.value, fitView);
}

/** 初始化地图并渲染标记。不写 activeView——用户切换视图不被慢加载覆盖（竞态：board 慢返回时用户已点列表） */
async function ensureMapView() {
  try {
    await map.ensureMap();
    await renderMapMarkers();
  } catch {
    // 地图加载失败（如高德 key 未配）：列表视图仍可用
    showToast("地图加载失败，可切换列表视图看单");
  }
}

async function switchView(view: "map" | "list") {
  activeView.value = view;
  if (view === "map") {
    await ensureMapView();
  }
}

watch(orders, () => void renderMapMarkers());

// ── 定位（唯一距离参照来源；HTTP 环境浏览器不开放定位 API）──
async function locateAndMeasure() {
  if (locating.value) return;
  locating.value = true;
  try {
    const AMap = await loadAMap();
    const [lng, lat] = await locateCurrentPosition(AMap);
    lite.distanceRefPoint.value = [lng, lat];
    map.getMap()?.setZoomAndCenter(15, [lng, lat]);
    if (!lite.hasPersistedPrefs && filters.sortMode.value !== "distance") {
      filters.sortMode.value = "distance";
      lite.saveFilters();
    }
    showToast("已按距离排序");
  } catch {
    showToast(window.isSecureContext === false ? "定位需 HTTPS 环境，可先按城市筛选" : "定位失败，请检查浏览器定位权限");
  } finally {
    locating.value = false;
  }
}

// ── 详情弹层 ──
function openSheet(order: PublicOrderBrief) {
  sheetOrderId.value = order.id;
  sheetVisible.value = true;
}

async function refresh() {
  await lite.load();
  await renderMapMarkers();
}

onMounted(async () => {
  await lite.load();
  // load 期间用户可能已切到列表（慢网络/Redis 重试 2s+）：只按当前视图初始化
  if (activeView.value === "map") {
    await ensureMapView();
  }
});
</script>

<template>
  <div class="flex h-[100dvh] flex-col bg-page">
    <!-- 顶栏：中介名 + 视图切换 -->
    <header class="relative z-30 flex flex-none items-center justify-between border-b border-default bg-white px-3 py-2">
      <div class="min-w-0">
        <p class="truncate text-sm font-semibold text-ink">{{ tenantName || "极速看单" }}</p>
        <p class="text-[11px] text-muted">看中的单子复制微信直接联系中介</p>
      </div>
      <div class="flex flex-none items-center gap-1 rounded-full border border-default bg-surface-soft p-0.5">
        <button
          type="button"
          class="rounded-full px-3 py-1 text-xs"
          :class="activeView === 'map' ? 'bg-ink text-white' : 'text-secondary'"
          @click="switchView('map')"
        >
          地图
        </button>
        <button
          type="button"
          class="rounded-full px-3 py-1 text-xs"
          :class="activeView === 'list' ? 'bg-ink text-white' : 'text-secondary'"
          @click="switchView('list')"
        >
          列表
        </button>
      </div>
    </header>

    <!-- 工具栏：筛选 + 排序摘要 + 定位 -->
    <div class="relative z-20 flex flex-none items-center gap-2 border-b border-default bg-white px-3 py-1.5">
      <button
        type="button"
        class="flex items-center gap-1 rounded-full border px-3 py-1 text-xs"
        :class="filters.hasActiveFilters.value ? 'border-brand-800 bg-brand-800 text-white' : 'border-default bg-surface text-secondary'"
        @click="filterVisible = true"
      >
        筛选
        <span v-if="filters.activeFilterCount.value > 0" class="rounded-full bg-white/20 px-1.5">
          {{ filters.activeFilterCount.value }}
        </span>
      </button>
      <div class="flex min-w-0 flex-1 gap-1 overflow-x-auto">
        <button
          v-for="opt in liteSortOptions"
          :key="opt.value"
          type="button"
          class="flex-none rounded-full px-2.5 py-1 text-xs"
          :class="sort === opt.value ? 'bg-surface-soft font-medium text-ink' : 'text-muted'"
          @click="sort = opt.value"
        >
          {{ opt.label }}
        </button>
      </div>
      <button
        type="button"
        class="flex-none rounded-full p-1"
        :class="lite.distanceRefPoint.value ? 'text-accent' : 'text-muted'"
        :disabled="locating"
        aria-label="按我的位置排序"
        @click="locateAndMeasure"
      >
        <van-icon name="location-o" />
      </button>
    </div>

    <!-- 主体：地图 / 列表 -->
    <main class="relative min-h-0 flex-1">
      <div v-show="activeView === 'map'" ref="mapRef" :id="MAP_CONTAINER_ID" class="absolute inset-0" />

      <div v-show="activeView === 'list'" class="absolute inset-0 overflow-y-auto px-3 pb-8 pt-3">
        <van-loading v-if="lite.loading.value" class="py-12" size="24" vertical>加载中…</van-loading>

        <AppEmpty v-else-if="lite.loadError.value" icon="📡" title="橱窗加载失败" description="网络波动或链接已失效，请重试">
          <template #action>
            <AppButton size="sm" @click="refresh">重试</AppButton>
          </template>
        </AppEmpty>

        <AppEmpty
          v-else-if="orders.length === 0"
          icon="🗺️"
          title="没有符合筛选的订单"
          description="放宽学段/学科/城市条件试试，或清除全部筛选"
        >
          <template #action>
            <AppButton size="sm" variant="secondary" @click="resetFilters">清除筛选</AppButton>
          </template>
        </AppEmpty>

        <template v-else>
          <div class="space-y-2.5">
            <LiteOrderCard v-for="order in orders" :key="order.id" :order="order" @select="openSheet" />
          </div>
          <p class="py-4 text-center text-[11px] text-muted">共 {{ orders.length }} 单 · 看中的直接联系中介微信</p>
        </template>
      </div>
    </main>

    <LiteFilterSheet
      v-model:visible="filterVisible"
      v-model:stage="stage"
      v-model:subjects="subjects"
      v-model:city="city"
      v-model:sort="sort"
      :city-label="filters.activeCityLabel.value"
      :city-options="filters.cityOptions.value"
      :sort-options="liteSortOptions"
      :available-subjects="filters.availableSubjects.value"
      @reset="resetFilters"
    />

    <LiteOrderSheet
      v-model:visible="sheetVisible"
      :invite-code="lite.inviteCode"
      :order-id="sheetOrderId"
      :fallback-wechat="contactWechat"
    />
  </div>
</template>
