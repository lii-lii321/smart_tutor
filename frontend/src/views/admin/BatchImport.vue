<script setup lang="ts">
import { computed, ref } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { infoFeeRate, calcInfoFee, MIN_DEPOSIT } from "@/utils/fee";
import { useRouter } from "vue-router";
import { useOrderStore, type OrderDraftItem } from "@/stores/order";
import AdminTabbar from "@/components/AdminTabbar.vue";
import AIImportProgress from "@/components/business/ai/AIImportProgress.vue";
import {
  buildDraftViews,
  countTriage,
  isDraftImportable,
  type DraftTriage,
} from "@/components/business/ai/aiImport";
import { showToast } from "vant";

const router = useRouter();
const orderStore = useOrderStore();

const rawText = ref("");
const parsedItems = ref<OrderDraftItem[]>([]);
const checkedItems = ref<Set<number>>(new Set());
const step = ref<"input" | "preview" | "done">("input");
const parsing = ref(false);
const importing = ref(false);
const editingIdx = ref<number | null>(null);
const importResult = ref<{ imported: number; skipped: string[] } | null>(null);
// 后端 warnings：整段解析失败的原文段数（成功段照常返回）
const segmentWarnings = ref<string[]>([]);
// 异常分诊过滤器（Batch 03）：all / review / blocked
const triageFilter = ref<"all" | DraftTriage>("all");

const SAMPLE_TEXT = `【成都家教 91940393】
联系地址：武侯区凯德·世纪名邸东庭
年级性别：预三年级，女
辅导科目：语数英
时间安排：一周2次，一次2小时
教员要求：有经验的女老师，985优先
薪资待遇：60-70/h

【成都家教 91940455】
学员地址：郫都区红光兰台府
年级：8升9
科目：物理
课酬：200-240/2h`;

const textLength = computed(() => rawText.value.length);

// 四步工作流口径：粘贴订单 → AI 识别 → 人工校对 → 批量发布。
// 解析请求期间 step 仍在 input，但视觉上点亮"AI 识别"步（诚实呈现：没有分字段假进度）。
// 窄屏（<400px）用两字短标签，避免步进器把页面撑出横向溢出。
const stepLabels = [
  { full: "粘贴订单", short: "粘贴" },
  { full: "AI 识别", short: "识别" },
  { full: "人工校对", short: "校对" },
  { full: "批量发布", short: "发布" },
] as const;
const stepIndex = computed(() => {
  if (step.value === "input") return parsing.value ? 1 : 0;
  if (step.value === "preview") return 2;
  return 3;
});

/* ── AI Import Domain（Batch 03）：API → 适配器 → UI 模型，分诊/字段状态集中在此 ── */

// 编辑直接作用于 parsedItems（可编辑草稿），draftViews 随之响应式重算——
// 原始 AI 结果（raw_text 原文）始终保留在 item.raw_text，不被人工修改覆盖
const draftViews = computed(() => buildDraftViews(parsedItems.value));
const triageCounts = computed(() => countTriage(draftViews.value));
const visibleDrafts = computed(() =>
  triageFilter.value === "all"
    ? draftViews.value
    : draftViews.value.filter((view) => view.triage === triageFilter.value)
);
const selectedImportableCount = computed(
  () => draftViews.value.filter((view) => checkedItems.value.has(view.index) && isDraftImportable(view)).length
);
const blockedSelectedCount = computed(
  () => draftViews.value.filter((view) => checkedItems.value.has(view.index) && !isDraftImportable(view)).length
);

// 信息费预览与后端 services/calculator.py 单一费率源对齐（utils/fee.ts），含寒暑假 2.5 倍与最低定金口径
function feeRateOf(item: OrderDraftItem) {
  return infoFeeRate(item.weekly_frequency, !!item.is_summer_vacation);
}

function calcFee(base: number, weekly: number, summer: boolean) {
  return calcInfoFee(base, weekly, summer);
}

function feeOf(item: OrderDraftItem) {
  return calcFee(Number(item.base_price) || 0, item.weekly_frequency, !!item.is_summer_vacation);
}

// "课酬过低"定义：课酬 × 费率 算出的信息费不足最低定金 ¥100
function tooCheapLabel(item: OrderDraftItem) {
  const base = Number(item.base_price) || 0;
  const total = Math.round(base * feeRateOf(item) * 100) / 100;
  return `信息费 ¥${total}（¥${base} × ${feeRateOf(item)}）低于最低定金 ¥${MIN_DEPOSIT}`;
}

function itemState(view: (typeof draftViews.value)[number]): { label: string; cls: string } {
  if (view.triage === "blocked") return { label: "无法创建", cls: "bg-danger-soft text-danger border-danger-soft" };
  if (view.triage === "review") return { label: "待确认", cls: "bg-warning-soft text-warning border-warning-soft" };
  return { label: "可直接确认", cls: "bg-success-soft text-success border-success-soft" };
}

function fillSample() {
  rawText.value = SAMPLE_TEXT;
}

function clearText() {
  rawText.value = "";
}

async function handleParse() {
  if (!rawText.value.trim()) {
    showToast("请先粘贴订单文本");
    return;
  }
  parsing.value = true;
  try {
    const res = await orderStore.batchParse(rawText.value.trim());
    parsedItems.value = res.items;
    checkedItems.value = new Set(res.items.map((_, i: number) => i));
    editingIdx.value = null;
    segmentWarnings.value = res.warnings || [];
    triageFilter.value = "all";
    step.value = "preview";
    // 部分段解析失败：成功段照常预览，但必须让用户知道内容不完整
    if (res.warnings?.length) {
      showToast(`有 ${res.warnings.length} 段未解析成功：${res.warnings[0]}`);
    }
  } catch (e) {
    showToast(getApiErrorMessage(e, "解析失败，请检查文本格式"));
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

const allChecked = computed(
  () => parsedItems.value.length > 0 && checkedItems.value.size === parsedItems.value.length
);

function toggleAll() {
  checkedItems.value = allChecked.value
    ? new Set()
    : new Set(parsedItems.value.map((_, i) => i));
}

function backToInput() {
  step.value = "input";
  editingIdx.value = null;
}

async function handleImport() {
  // 无法创建的条目（必填缺失/课酬过低）自动移出勾选并明确告知——绝不偷偷创建后让后端拒绝一堆
  const blocked: string[] = [];
  const next = new Set(checkedItems.value);
  for (const view of draftViews.value) {
    if (checkedItems.value.has(view.index) && !isDraftImportable(view)) {
      blocked.push(view.rawId);
      next.delete(view.index);
    }
  }
  if (blocked.length) {
    checkedItems.value = next;
  }
  const selected = parsedItems.value
    .filter((_, i) => checkedItems.value.has(i))
    .map(finalizeItem);
  if (selected.length === 0) {
    showToast({
      message: blocked.length
        ? `${blocked.length} 条无法导入（信息费不足 ¥${MIN_DEPOSIT} 或信息缺失）：${blocked.join("、")}。可修改课酬，或清空价格改为待定价`
        : "没有可导入的订单，请调整后重试",
      duration: 4000,
    });
    return;
  }
  if (blocked.length) {
    showToast({
      message: `${blocked.length} 条无法导入已移出勾选（信息费不足 ¥${MIN_DEPOSIT} 或信息缺失），其余继续导入`,
      duration: 4000,
    });
  }
  importing.value = true;
  try {
    const res = await orderStore.batchImport(selected);
    importResult.value = {
      imported: Number(res.imported || 0),
      skipped: res.skipped_duplicates || [],
    };
    step.value = "done";
    window.scrollTo({ top: 0 });
  } catch (e) {
    showToast(getApiErrorMessage(e, "导入失败，请稍后重试"));
  } finally {
    importing.value = false;
  }
}

function finalizeItem(item: OrderDraftItem): OrderDraftItem {
  const base = Number(item.base_price) || 0;
  const fee = calcFee(base, item.weekly_frequency, !!item.is_summer_vacation);
  if (base > 0 && fee) {
    return {
      ...item,
      base_price: base,
      calculated_info_fee: fee.total,
      deposit_amount: fee.deposit,
      balance_amount: fee.balance,
      needs_manual_price: false,
    };
  }
  return {
    ...item,
    base_price: 0,
    calculated_info_fee: 0,
    deposit_amount: 0,
    balance_amount: 0,
    needs_manual_price: true,
  };
}

function startAnotherBatch() {
  rawText.value = "";
  parsedItems.value = [];
  checkedItems.value = new Set();
  importResult.value = null;
  editingIdx.value = null;
  segmentWarnings.value = [];
  triageFilter.value = "all";
  step.value = "input";
}

// 创建结果里的重复编号：草稿仍在校对区，允许返回修改 raw_id 后重试（能力以现有 API 为准）
function backToPreviewFromDone() {
  step.value = "preview";
}
</script>

<template>
  <div class="import-page admin-page min-h-screen bg-page pb-24 mx-auto max-w-2xl">
    <van-nav-bar title="批量导入" left-arrow @click-left="router.push('/admin/dashboard')" />

    <main class="mx-auto w-full max-w-3xl px-4 pt-4">
      <!-- 步骤指示：四步工作流，AI 识别步用专属紫点亮；窄屏切两字短标签 -->
      <ol class="mb-4 flex items-center gap-1 text-xs">
        <li
          v-for="(label, i) in stepLabels"
          :key="label.full"
          class="flex shrink-0 items-center gap-1"
        >
          <span
            class="flex h-5 w-5 items-center justify-center rounded-full border text-[11px] font-semibold"
            :class="{
              'border-brand-800 bg-brand-800 text-white': stepIndex === i && i !== 1,
              'border-ai-deep bg-ai text-white': stepIndex === i && i === 1,
              'border-brand-200 bg-brand-50 text-brand-700': stepIndex > i,
              'border-slate-200 text-slate-400': stepIndex < i,
            }"
          >
            <van-icon v-if="stepIndex > i" name="success" size="12" />
            <template v-else>{{ i + 1 }}</template>
          </span>
          <span
            class="whitespace-nowrap"
            :class="stepIndex === i ? (i === 1 ? 'font-medium text-ai-deep' : 'font-medium text-primary') : 'text-slate-500'"
          >
            <span class="hidden min-[400px]:inline">{{ label.full }}</span>
            <span class="min-[400px]:hidden">{{ label.short }}</span>
            <span
              v-if="i === 1 && parsing"
              class="h-1.5 w-1.5 animate-pulse rounded-full bg-ai"
            />
          </span>
          <span v-if="i < stepLabels.length - 1" class="mx-0.5 h-px w-4 bg-slate-200" />
        </li>
      </ol>

      <!-- Step 1: 粘贴文本 -->
      <section v-if="step === 'input'" class="rounded-xl border border-slate-200 bg-white">
        <header class="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <div>
            <h2 class="text-sm font-semibold text-slate-900">订单原文</h2>
            <p class="mt-0.5 text-xs text-slate-500">粘贴微信聊天中复制的订单文本，AI 自动识别字段</p>
          </div>
          <button
            class="shrink-0 rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
            @click="fillSample"
          >
            填入示例
          </button>
        </header>

        <div class="p-4">
          <textarea
            v-model="rawText"
            class="import-textarea h-64 w-full resize-none rounded-lg border border-slate-200 bg-slate-50/50 p-3 font-mono text-[13px] leading-6 text-slate-800 focus:border-slate-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-slate-100"
            placeholder="在此粘贴文本…支持「编号 + 字段行」的标准格式，也支持自然语言描述。"
          />
          <div class="mt-3 flex items-center justify-between">
            <span class="text-xs text-slate-400">{{ textLength }} 字 · 原文将完整存档</span>
            <button
              v-if="rawText"
              class="text-xs text-slate-500 hover:text-slate-700"
              @click="clearText"
            >
              清空
            </button>
          </div>
        </div>

        <footer class="flex items-center justify-between gap-3 border-t border-slate-100 px-4 py-3">
          <p class="text-xs text-slate-400">导入前可在下一步逐条校对价格与地址</p>
          <button
            class="rounded-lg bg-brand-800 px-5 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="parsing || !rawText.trim()"
            @click="handleParse"
          >
            {{ parsing ? "AI 识别中…" : "开始 AI 识别" }}
          </button>
        </footer>
      </section>

      <!-- Step 3: 人工校对（AI Import Workspace） -->
      <section v-else-if="step === 'preview'" class="space-y-3">
        <!-- 异常摘要 + 分诊过滤（AIImportProgress：真实计数，无假进度） -->
        <AIImportProgress
          v-model="triageFilter"
          :total="parsedItems.length"
          :counts="triageCounts"
          :segment-failures="segmentWarnings.length"
        />

        <div class="flex items-center justify-between px-1 text-xs text-muted">
          <span>已勾选 <b class="text-secondary">{{ checkedItems.size }}</b> 条</span>
          <button class="font-medium text-brand-700" @click="toggleAll">
            {{ allChecked ? "取消全选" : "全选" }}
          </button>
        </div>

        <article
          v-for="view in visibleDrafts"
          :key="view.index"
          class="rounded-xl border bg-white"
          :class="checkedItems.has(view.index) ? 'border-slate-300 ring-1 ring-slate-100' : 'border-slate-200'"
        >
          <div class="flex items-start gap-3 px-4 py-3">
            <van-checkbox
              :model-value="checkedItems.has(view.index)"
              class="mt-0.5 shrink-0"
              @click.stop="toggleCheck(view.index)"
            />
            <div class="min-w-0 flex-1" @click="toggleCheck(view.index)">
              <div class="flex flex-wrap items-center gap-2">
                <span
                  class="rounded border px-1.5 py-0.5 text-[10px] font-medium"
                  :class="itemState(view).cls"
                >
                  {{ itemState(view).label }}
                </span>
                <!-- 后端定性置信度（parser_confidence），不显示数值百分比 -->
                <span class="rounded-full bg-surface-soft px-1.5 py-0.5 text-[10px] text-muted">
                  {{ view.confidenceLabel }}
                </span>
                <span v-if="parsedItems[view.index].is_summer_vacation" class="rounded border border-rose-200 bg-rose-50 px-1.5 py-0.5 text-[10px] text-rose-600">
                  寒暑假 ×2.5
                </span>
                <span v-if="parsedItems[view.index].parser_source" class="ml-auto text-[10px] text-slate-300">{{ parsedItems[view.index].parser_source }}</span>
              </div>
              <div class="mt-1 break-all font-mono text-xs text-slate-500">#{{ view.rawId }}</div>
              <div class="mt-1 text-sm font-semibold text-slate-900">{{ parsedItems[view.index].grade_subject || "（年级科目缺失）" }}</div>

              <!-- 字段级预览：状态来自适配器（normal/warning/missing），⚠ 不编造 -->
              <dl class="mt-2 space-y-1 text-xs">
                <div
                  v-for="f in view.fields"
                  :key="f.key"
                  class="flex min-w-0 items-baseline gap-2"
                >
                  <dt class="w-16 shrink-0 text-slate-400">{{ f.label }}</dt>
                  <dd class="min-w-0 flex-1" :class="f.status === 'normal' ? 'text-slate-700' : 'text-warning'">
                    {{ f.value }}
                    <span v-if="f.reason" class="text-warning/90">· {{ f.reason }}</span>
                  </dd>
                </div>
              </dl>
              <p v-if="view.blockedReason" class="mt-1.5 rounded-md bg-danger-soft px-2 py-1 text-[11px] text-danger">
                {{ view.blockedReason }}——创建时将自动跳过
              </p>
            </div>
            <button
              class="shrink-0 self-center rounded-md border px-2 py-1 text-xs"
              :class="editingIdx === view.index ? 'border-slate-300 text-slate-600' : 'border-slate-200 text-slate-600'"
              @click.stop="editingIdx = editingIdx === view.index ? null : view.index"
            >
              {{ editingIdx === view.index ? "收起" : "编辑" }}
            </button>
          </div>

          <!-- 展开编辑：人工修改的是待创建草稿，AI 原文（raw_text）不受影响 -->
          <div v-if="editingIdx === view.index" class="border-t border-slate-100 bg-slate-50/60 px-4 py-3">
            <div class="grid grid-cols-2 gap-x-3 gap-y-2.5">
              <label class="import-field">
                <span>年级科目</span>
                <input v-model="parsedItems[view.index].grade_subject" type="text" />
              </label>
              <label class="import-field">
                <span>单次课酬（¥）</span>
                <input v-model.number="parsedItems[view.index].base_price" type="number" min="0" step="10" placeholder="0 = 待教员报价" />
              </label>
              <label class="import-field">
                <span>每周次数</span>
                <input v-model.number="parsedItems[view.index].weekly_frequency" type="number" min="1" max="14" />
              </label>
              <label class="import-field">
                <span>展示地址</span>
                <input v-model="parsedItems[view.index].fuzzy_address" type="text" />
              </label>
              <label class="import-field">
                <span>真实门牌</span>
                <input v-model="parsedItems[view.index].exact_address" type="text" placeholder="尾款解锁后可见" />
              </label>
              <label class="import-field">
                <span>家长电话</span>
                <input v-model="parsedItems[view.index].parent_phone" type="tel" placeholder="选填" />
              </label>
              <label class="import-field col-span-2">
                <span>教员要求</span>
                <input v-model="parsedItems[view.index].requirements" type="text" />
              </label>
            </div>

            <div class="mt-3 flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2">
              <label class="flex items-center gap-2 text-xs text-slate-600">
                <van-switch v-model="parsedItems[view.index].is_summer_vacation" size="18px" />
                寒暑假密集单（费率 ×2.5）
              </label>
              <div class="text-right text-xs">
                <template v-if="feeOf(parsedItems[view.index])">
                  <span class="text-slate-500">试算：</span>
                  <b class="text-slate-600">¥{{ feeOf(parsedItems[view.index])!.total }}</b>
                  <span class="text-slate-400">（定金 ¥{{ feeOf(parsedItems[view.index])!.deposit }} + 尾款 ¥{{ feeOf(parsedItems[view.index])!.balance }}）</span>
                </template>
                <template v-else-if="Number(parsedItems[view.index].base_price) > 0">
                  <span class="text-red-500">{{ tooCheapLabel(parsedItems[view.index]) }}，请调整课酬或清空价格改为待定价</span>
                </template>
                <template v-else>
                  <span class="text-amber-600">待教员报价</span>
                </template>
              </div>
            </div>
            <p class="mt-2 text-[11px] text-slate-400">
              修改课酬/频次后费用将按平台费率自动试算；修改展示地址不会改变地图坐标，导入后可在订单管理中校准。
            </p>
          </div>
        </article>

        <div class="h-20" />
      </section>

      <!-- Step 4: 发布完成 -->
      <section v-else class="rounded-xl border border-slate-200 bg-white p-8 text-center">
        <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50">
          <van-icon name="passed" size="28" color="#059669" />
        </div>
        <h2 class="mt-4 text-base font-semibold text-slate-900">发布完成</h2>
        <p class="mt-1 text-sm text-slate-500">
          成功发布 <b class="text-slate-900">{{ importResult?.imported ?? 0 }}</b> 条订单
          <template v-if="importResult?.skipped?.length">
            ，跳过 {{ importResult.skipped.length }} 条重复编号
          </template>
        </p>
        <p v-if="importResult?.skipped?.length" class="mx-auto mt-2 max-w-md break-all text-xs text-slate-400">
          重复编号：{{ importResult.skipped.join("、") }}
        </p>
        <button
          v-if="importResult?.skipped?.length"
          class="mx-auto mt-3 block text-xs font-medium text-brand-700"
          @click="backToPreviewFromDone"
        >
          返回校对，修改重复编号后重试
        </button>
        <div class="mt-6 flex justify-center gap-3">
          <button
            class="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
            @click="startAnotherBatch"
          >
            继续导入
          </button>
          <button
            class="rounded-lg bg-brand-800 px-4 py-2 text-sm font-semibold text-white"
            @click="router.push('/admin/orders')"
          >
            查看订单列表
          </button>
        </div>
      </section>
    </main>

    <!-- Step 3 底部操作条：CTA 计数=可创建数，无法创建的已选条目明确提示将跳过 -->
    <div
      v-if="step === 'preview'"
      class="fixed inset-x-0 bottom-[50px] z-20 border-t border-slate-200 bg-white px-4 py-3"
    >
      <div class="mx-auto w-full max-w-3xl">
        <p
          v-if="blockedSelectedCount > 0"
          class="mb-1.5 text-center text-[11px] text-warning"
        >
          {{ blockedSelectedCount }} 条已选但存在必填问题，创建时将自动跳过
        </p>
        <div class="flex gap-3">
          <button
            class="rounded-lg border border-slate-200 px-4 py-2.5 text-sm text-slate-600"
            @click="backToInput"
          >
            返回修改
          </button>
          <button
            class="flex-1 rounded-lg bg-brand-800 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="importing || selectedImportableCount === 0"
            @click="handleImport"
          >
            {{ importing ? "发布中…" : `批量创建 ${selectedImportableCount} 条订单` }}
          </button>
        </div>
      </div>
    </div>

    <!-- 处理遮罩：AI 识别中给出诚实的"AI 工作卡"，不伪造分字段进度 -->
    <van-overlay :show="parsing || importing">
      <div class="flex h-full flex-col items-center justify-center gap-3 px-8">
        <div v-if="parsing" class="w-full max-w-xs rounded-2xl bg-surface p-5 text-center shadow-elevated">
          <span class="inline-flex items-center gap-1.5 rounded-full bg-ai-soft px-2.5 py-1 text-[11px] font-semibold text-ai-deep">
            <span class="h-1.5 w-1.5 animate-pulse rounded-full bg-ai" />
            AI 识别中
          </span>
          <div class="mt-3 text-sm font-medium text-primary">正在解析微信订单文本</div>
          <div class="mt-1.5 text-xs leading-5 text-muted">
            自动提取地址 · 年级 · 科目 · 课酬 · 时间<br>
            通常需要 10~30 秒，完成后逐条人工校对
          </div>
          <div class="mt-3 h-1 overflow-hidden rounded-full bg-surface-soft">
            <div class="h-full w-1/3 animate-pulse rounded-full bg-ai" />
          </div>
        </div>
        <template v-else>
          <van-loading type="spinner" size="32" color="white" />
          <span class="text-sm text-white">正在批量发布订单…</span>
        </template>
      </div>
    </van-overlay>
    <AdminTabbar />
  </div>
</template>

<style scoped>
.import-field {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.import-field span {
  font-size: 11px;
  color: #64748b;
}

.import-field input {
  width: 100%;
  border: 1px solid #dbe3ec;
  border-radius: 6px;
  background: #fff;
  padding: 6px 8px;
  font-size: 13px;
  color: #0f172a;
}

.import-field input:focus {
  outline: none;
  border-color: #334155;
  box-shadow: 0 0 0 2px rgb(var(--st-brand-800-rgb) / 0.08);
}
</style>