<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { useOrderStore, type ParsedOrderItem } from "@/stores/order";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast, showSuccessToast } from "vant";

const router = useRouter();
const orderStore = useOrderStore();

const rawText = ref("");
const parsedItems = ref<ParsedOrderItem[]>([]);
const checkedItems = ref<Set<number>>(new Set());
const step = ref<"input" | "preview">("input");
const parsing = ref(false);
const importing = ref(false);

async function handleParse() {
  if (!rawText.value.trim()) {
    showToast("请粘贴微信聊天文本");
    return;
  }
  parsing.value = true;
  try {
    const res = await orderStore.batchParse(rawText.value.trim());
    parsedItems.value = res.items;
    checkedItems.value = new Set(res.items.map((_: any, i: number) => i));
    step.value = "preview";
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "解析失败，请检查文本格式");
  } finally {
    parsing.value = false;
  }
}

function toggleCheck(index: number) {
  const next = new Set(checkedItems.value);
  if (next.has(index)) next.delete(index);
  else next.add(index);
  checkedItems.value = next;
}

function toggleAll() {
  if (checkedItems.value.size === parsedItems.value.length) {
    checkedItems.value = new Set();
  } else {
    checkedItems.value = new Set(parsedItems.value.map((_, i) => i));
  }
}

async function handleImport() {
  const selected = parsedItems.value.filter((_, i) => checkedItems.value.has(i));
  if (selected.length === 0) {
    showToast("请至少勾选一条");
    return;
  }
  importing.value = true;
  try {
    const res = await orderStore.batchImport(selected);
    const skipped = res.skipped_duplicates?.length || 0;
    if (res.imported > 0 && skipped > 0) {
      showSuccessToast(`已导入 ${res.imported} 条，跳过 ${skipped} 条重复编号`);
    } else if (res.imported > 0) {
      showSuccessToast(`已导入 ${res.imported} 条订单`);
    } else {
      showToast(`没有新订单可导入，${skipped} 条编号已存在`);
    }
    step.value = "input";
    rawText.value = "";
    parsedItems.value = [];
    checkedItems.value = new Set();
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "导入失败");
  } finally {
    importing.value = false;
  }
}
</script>

<template>
  <div class="min-h-screen bg-gray-50 pb-20">
    <van-nav-bar title="批量导入" left-arrow @click-left="router.push('/admin/dashboard')" />

    <!-- Step 1: 粘贴文本 -->
    <div v-if="step === 'input'" class="p-4 space-y-4">
      <div class="bg-white rounded-2xl p-5 shadow-sm">
        <div class="text-sm text-gray-400 mb-3">📋 粘贴微信聊天中复制的中介订单文本（支持「自带价」）</div>
        <div class="text-xs text-gray-400 mb-2">原文会完整保留到数据库，AI 只负责辅助计算信息费。</div>
        <textarea
          v-model="rawText"
          class="w-full h-48 p-3 border border-gray-200 rounded-xl text-sm resize-none focus:outline-none focus:border-primary-500"
          placeholder="示例：&#10;✨✨2026081023&#10;【学生年级】：大一&#10;【需要科目】：高数&#10;【薪水】：70-100/h&#10;【住址】：郫都区红光兰台府&#10;&#10;也支持老格式：&#10;【涨分🐶452】8升9物理 200-240/2h 成华区蓝光coco国际 女大"
        />
        <button
          class="w-full header-gradient text-white rounded-xl py-3.5 text-base font-semibold mt-3 disabled:opacity-50"
          :disabled="parsing || !rawText.trim()"
          @click="handleParse"
        >
          {{ parsing ? "🤖 AI 解析中..." : "🤖 开始 AI 解析" }}
        </button>
      </div>
    </div>

    <!-- Step 2: 预览确认 -->
    <div v-else class="p-4">
      <div class="flex h-[calc(100vh-156px)] flex-col">
        <div class="flex items-center justify-between bg-white rounded-2xl p-4 shadow-sm">
          <div class="text-sm text-gray-600">
            已解析 <span class="font-bold text-primary-600">{{ parsedItems.length }}</span> 条
            <span v-if="parsedItems.some(i => i.needs_manual_price)" class="text-orange-500 ml-1">
              · {{ parsedItems.filter(i => i.needs_manual_price).length }}条待教员报价
            </span>
          </div>
          <button class="text-primary-600 text-sm" @click="toggleAll">
            {{ checkedItems.size === parsedItems.length ? "取消全选" : "全选" }}
          </button>
        </div>

        <div class="mt-3 flex-1 overflow-y-auto space-y-3 pr-1 pb-24">
          <div
            v-for="(item, index) in parsedItems"
            :key="index"
            class="bg-white rounded-2xl p-4 shadow-sm"
            :class="{ 'ring-2 ring-primary-500': checkedItems.has(index) }"
            @click="toggleCheck(index)"
          >
            <div class="flex items-start gap-3">
              <van-checkbox :model-value="checkedItems.has(index)" class="shrink-0 mt-1" />
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1 flex-wrap">
                  <span class="font-semibold text-sm">{{ item.raw_id }}</span>
                  <span class="text-primary-600 font-bold">{{ item.grade_subject }}</span>
                  <span v-if="item.is_summer_vacation" class="px-1.5 py-0.5 bg-red-100 text-red-600 text-xs rounded">暑假</span>
                  <span
                    v-if="item.needs_manual_price"
                    class="px-1.5 py-0.5 bg-orange-100 text-orange-600 text-xs rounded"
                  >待教员报价</span>
                </div>

                <div class="text-gray-400 text-xs space-y-0.5">
                  <div>📍 {{ item.fuzzy_address }}</div>
                  <div v-if="!item.needs_manual_price">
                    ¥{{ item.calculated_info_fee }}（定金{{ item.deposit_amount }} + 尾款{{ item.balance_amount }}）
                  </div>
                  <div v-else class="text-orange-500">
                    💬 原文：{{ item.price_total }} — 由教员申请时自行报价
                  </div>
                  <div>📅 每周 {{ item.weekly_frequency }} 次<template v-if="item.lesson_count"> · 共 {{ item.lesson_count }} 次</template></div>
                  <div v-if="item.requirements" class="text-gray-500">📝 {{ item.requirements }}</div>
                  <div v-if="item.subway_remark">🚇 {{ item.subway_remark }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 底部操作栏 -->
        <div class="fixed bottom-[50px] left-0 right-0 bg-white border-t p-4">
          <div class="flex gap-3">
            <button
              class="flex-1 bg-gray-100 text-gray-600 rounded-xl py-3 text-sm font-semibold"
              @click="step = 'input'"
            >
              返回修改
            </button>
            <button
              class="flex-[2] header-gradient text-white rounded-xl py-3 text-sm font-semibold disabled:opacity-50"
              :disabled="importing || checkedItems.size === 0"
              @click="handleImport"
            >
              {{ importing ? "导入中..." : `导入 ${checkedItems.size} 条订单` }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 加载遮罩 -->
    <van-overlay :show="parsing || importing">
      <div class="flex flex-col items-center justify-center h-full gap-3">
        <van-loading type="spinner" size="32" color="white" />
        <span class="text-white text-sm">{{ parsing ? "AI 正在解析..." : "正在导入..." }}</span>
      </div>
    </van-overlay>
    <AdminTabbar />
  </div>
</template>
