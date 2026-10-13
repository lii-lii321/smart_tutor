<script setup lang="ts">
/**
 * AI 找单（阶段 1a）：自然语言描述 → AI 解析条件 → 租户内结构化查询 → 订单卡片。
 * 与 AI 批量录单同一套 AI 交互语言（ai 配色 / 诚实加载态）；
 * 结果可在订单管理页人工复核（卡片点击进订单工作区，底部提供普通查询兜底入口）。
 */
import { onMounted, ref } from "vue";
import { showToast } from "vant";
import { useRouter } from "vue-router";

import { aiApi, type DeviceLocation, type FindOrdersResponse } from "@/api/ai";
import AiFindOrderCard from "@/components/business/ai/AiFindOrderCard.vue";
import { conditionsChips } from "@/components/business/ai/aiFindOrders";
import AdminShell from "@/components/admin/AdminShell.vue";
import AppButton from "@/components/ui/AppButton.vue";
import { useSmartBack } from "@/composables/useSmartBack";
import { getApiErrorMessage } from "@/utils/apiError";

const router = useRouter();
const { goBack } = useSmartBack("/admin/orders");

const query = ref("");
const loading = ref(false);
const result = ref<FindOrdersResponse | null>(null);

// 结果暂存 sessionStorage：点进订单工作区后返回本页时恢复，而不是退回空白页
const RESULT_CACHE_KEY = "ai-find-orders:last-result";
// 设备定位：进页请求一次授权，"附近"默认按你的位置算（拒绝则本会话不再问，
// 后端退回在招订单中心兜底）
const LOCATION_CACHE_KEY = "ai-find-orders:device-location";
const deviceLocation = ref<DeviceLocation | null>(null);

onMounted(() => {
  try {
    const cached = sessionStorage.getItem(RESULT_CACHE_KEY);
    if (cached) {
      const saved = JSON.parse(cached) as { query?: string; result?: FindOrdersResponse };
      if (saved.query) query.value = saved.query;
      if (saved.result) result.value = saved.result;
    }
  } catch {
    // 缓存损坏直接忽略，等同无历史
  }
  restoreDeviceLocation();
});

function restoreDeviceLocation() {
  try {
    const cached = sessionStorage.getItem(LOCATION_CACHE_KEY);
    if (cached === "denied") return; // 用户已拒绝：本会话不再请求
    if (cached) {
      deviceLocation.value = JSON.parse(cached) as DeviceLocation;
      return;
    }
  } catch {
    // 同上，忽略损坏缓存
  }
  if (!("geolocation" in navigator)) return;
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const loc: DeviceLocation = {
        lng: Number(pos.coords.longitude.toFixed(6)),
        lat: Number(pos.coords.latitude.toFixed(6)),
      };
      deviceLocation.value = loc;
      try {
        sessionStorage.setItem(LOCATION_CACHE_KEY, JSON.stringify(loc));
      } catch {
        // 存不上只影响下次进页要重新授权，不影响本次
      }
    },
    () => {
      try {
        sessionStorage.setItem(LOCATION_CACHE_KEY, "denied");
      } catch {
        // 同上
      }
    },
    { timeout: 8000, maximumAge: 600_000 },
  );
}

const SAMPLE_QUERIES = [
  "附近10公里、时薪80以上的初中数学订单",
  "武侯区一周3次的高中英语，预算200以内",
  "最近发布的大学高数单",
];

function fillSample(text: string) {
  query.value = text;
}

async function handleFind() {
  const text = query.value.trim();
  if (!text) {
    showToast("请先描述你想找的订单");
    return;
  }
  loading.value = true;
  try {
    result.value = await aiApi.findOrders(text, deviceLocation.value ?? undefined);
    sessionStorage.setItem(
      RESULT_CACHE_KEY,
      JSON.stringify({ query: text, result: result.value }),
    );
    if (result.value.warnings.length) {
      showToast(result.value.warnings[0]);
    }
  } catch (e) {
    result.value = null;
    showToast(getApiErrorMessage(e, "AI 找单失败，请稍后重试"));
  } finally {
    loading.value = false;
  }
}

function openOrder(id: number) {
  router.push(`/admin/orders/${id}`);
}
</script>

<template>
  <AdminShell>
    <van-nav-bar title="AI 找单" left-arrow @click-left="goBack" />

    <main class="mx-auto w-full max-w-3xl px-4 pt-4">
      <!-- 输入区 -->
      <section class="rounded-xl border border-default bg-white">
        <header class="border-b border-default px-4 py-3">
          <h2 class="text-sm font-semibold text-primary">描述你想找的订单</h2>
          <p class="mt-0.5 text-xs text-secondary">用一句话说清科目、年级、价格、位置，AI 解析成筛选条件</p>
        </header>
        <div class="p-4">
          <textarea
            v-model="query"
            class="h-20 w-full resize-none rounded-lg border border-default bg-surface-soft/50 p-3 text-body leading-6 text-primary focus:border-brand-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-default"
            placeholder="例如：附近10公里、时薪80以上的初中数学订单"
            @keydown.enter.exact.prevent="handleFind"
          />
          <div class="mt-3 flex flex-wrap gap-2">
            <button
              v-for="sample in SAMPLE_QUERIES"
              :key="sample"
              class="rounded-full border border-default px-2.5 py-1 text-caption text-secondary hover:bg-surface-soft"
              @click="fillSample(sample)"
            >
              {{ sample }}
            </button>
          </div>
        </div>
        <footer class="border-t border-default px-4 py-3 text-right">
          <AppButton size="md" :disabled="loading || !query.trim()" @click="handleFind">
            {{ loading ? "AI 找单中…" : "开始找单" }}
          </AppButton>
        </footer>
      </section>

      <!-- 结果区 -->
      <section v-if="result" class="mt-4 space-y-3">
        <!-- 条件回显：AI 解析出什么条件就展示什么，不生效的键不出现 -->
        <div class="rounded-xl border border-default bg-white px-4 py-3">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-xs font-medium text-secondary">筛选条件：</span>
            <span
              v-for="chip in conditionsChips(result.conditions)"
              :key="chip"
              class="rounded-full bg-ai-soft px-2 py-0.5 text-caption font-medium text-ai-deep"
            >
              {{ chip }}
            </span>
          </div>
          <p
            v-for="warning in result.warnings"
            :key="warning"
            class="mt-2 rounded-md bg-warning-soft px-2 py-1 text-caption text-warning-deep"
          >
            {{ warning }}
          </p>
        </div>

        <div class="flex items-center justify-between px-1 text-xs text-muted">
          <span>
            匹配 <b class="text-secondary">{{ result.total_matched }}</b> 条
            <template v-if="result.total_matched > result.items.length">
              ，展示最近 {{ result.items.length }} 条
            </template>
            <template v-if="result.scanned">（扫描 {{ result.scanned }} 条候选）</template>
          </span>
          <button class="font-medium text-brand-700" @click="router.push('/admin/orders')">
            打开订单管理
          </button>
        </div>

        <AiFindOrderCard
          v-for="item in result.items"
          :key="item.id"
          :item="item"
          @open="openOrder"
        />

        <!-- 空态：给放宽条件的方向，不给假结果 -->
        <div
          v-if="result.items.length === 0"
          class="rounded-xl border border-default bg-white p-8 text-center"
        >
          <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-surface-soft">
            <van-icon name="search" size="24" class="text-muted" />
          </div>
          <h3 class="mt-3 text-sm font-semibold text-primary">没有匹配的招聘中订单</h3>
          <p class="mx-auto mt-1 max-w-xs text-xs leading-5 text-secondary">
            可以放宽价格或距离条件再试；也可以在订单管理页按编号、状态手动筛选。
          </p>
          <button class="mt-3 text-xs font-medium text-brand-700" @click="router.push('/admin/orders')">
            前往订单管理
          </button>
        </div>
      </section>

      <div class="h-8" />
    </main>

    <!-- 处理遮罩：与批量录单同款诚实 AI 加载卡，无假进度 -->
    <van-overlay :show="loading">
      <div class="flex h-full items-center justify-center px-8">
        <div class="w-full max-w-xs rounded-2xl bg-surface p-5 text-center shadow-elevated">
          <span class="inline-flex items-center gap-1.5 rounded-full bg-ai-soft px-2.5 py-1 text-caption font-semibold text-ai-deep">
            <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-ai" />
            AI 找单中
          </span>
          <div class="mt-3 text-sm font-medium text-primary">正在解析筛选条件并查询订单</div>
          <div class="mt-1.5 text-xs leading-5 text-muted">
            通常几秒内完成；结果与订单管理页同一数据口径
          </div>
        </div>
      </div>
    </van-overlay>
  </AdminShell>
</template>
