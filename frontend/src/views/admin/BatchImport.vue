<script setup lang="ts">
import { computed, ref } from "vue";
import { getApiErrorMessage } from "@/utils/apiError";
import { useRouter } from "vue-router";
import { useOrderStore, type ParsedOrderItem } from "@/stores/order";
import AdminTabbar from "@/components/AdminTabbar.vue";
import { showToast } from "vant";

const router = useRouter();
const orderStore = useOrderStore();

const rawText = ref("");
const parsedItems = ref<ParsedOrderItem[]>([]);
const checkedItems = ref<Set<number>>(new Set());
const step = ref<"input" | "preview" | "done">("input");
const parsing = ref(false);
const importing = ref(false);
const editingIdx = ref<number | null>(null);
const importResult = ref<{ imported: number; skipped: string[] } | null>(null);

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

const stepLabels = ["粘贴文本", "校对确认", "导入完成"] as const;
const stepIndex = computed(() => ["input", "preview", "done"].indexOf(step.value));

const pendingPriceCount = computed(() => parsedItems.value.filter((i) => Number(i.base_price) <= 0).length);
const reviewCount = computed(() => parsedItems.value.filter((i) => i.needs_manual_review).length);

// 与后端 services/calculator.py 费率一致：信息费 = 单次课酬 × 频率费率，最低定金 ¥100
const MIN_DEPOSIT = 100;

function feeRateOf(item: ParsedOrderItem) {
  return item.is_summer_vacation
    ? 2.5
    : item.weekly_frequency === 1
      ? 1.5
      : item.weekly_frequency === 2
        ? 1.0
        : item.weekly_frequency === 3
          ? 0.9
          : 0.8;
}

function calcFee(base: number, weekly: number, summer: boolean) {
  if (!base || base <= 0) return null;
  const rate = summer ? 2.5 : weekly === 1 ? 1.5 : weekly === 2 ? 1.0 : weekly === 3 ? 0.9 : 0.8;
  const total = Math.round(base * rate * 100) / 100;
  if (total < MIN_DEPOSIT) return null;
  return { total, deposit: MIN_DEPOSIT, balance: Math.round((total - MIN_DEPOSIT) * 100) / 100 };
}

function feeOf(item: ParsedOrderItem) {
  return calcFee(Number(item.base_price) || 0, item.weekly_frequency, !!item.is_summer_vacation);
}

// "课酬过低"定义：课酬 × 费率 算出的信息费不足最低定金 ¥100
function tooCheapLabel(item: ParsedOrderItem) {
  const base = Number(item.base_price) || 0;
  const total = Math.round(base * feeRateOf(item) * 100) / 100;
  return `信息费 ¥${total}（¥${base} × ${feeRateOf(item)}）低于最低定金 ¥${MIN_DEPOSIT}`;
}

function itemState(item: ParsedOrderItem): { label: string; cls: string } {
  if (Number(item.base_price) <= 0) return { label: "待定价", cls: "bg-amber-50 text-amber-700 border-amber-200" };
  if (!feeOf(item)) return { label: "课酬过低", cls: "bg-red-50 text-red-600 border-red-200" };
  if (item.needs_manual_review) return { label: "建议复核", cls: "bg-sky-50 text-sky-700 border-sky-200" };
  return { label: "就绪", cls: "bg-emerald-50 text-emerald-700 border-emerald-200" };
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
    checkedItems.value = new Set(res.items.map((_: ParsedOrderItem, i: number) => i));
    editingIdx.value = null;
    step.value = "preview";
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

// 单条是否能进入导入：科目/地址完整，且定价条目的信息费足额
function isImportable(item: ParsedOrderItem) {
  if (!item.grade_subject.trim() || !String(item.fuzzy_address || "").trim()) return false;
  if (Number(item.base_price) > 0 && !feeOf(item)) return false;
  return true;
}

async function handleImport() {
  // 课酬过低/信息缺失的条目会阻断校验且 toast 一闪即逝，这里自动移出勾选并明确告知
  const blocked: string[] = [];
  const next = new Set(checkedItems.value);
  for (const idx of next) {
    if (!isImportable(parsedItems.value[idx])) {
      blocked.push(parsedItems.value[idx].raw_id);
      next.delete(idx);
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

function finalizeItem(item: ParsedOrderItem): ParsedOrderItem {
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
  step.value = "input";
}
</script>

<template>
  <div class="import-page min-h-screen bg-slate-50 pb-24 mx-auto max-w-2xl">
    <van-nav-bar title="批量导入" left-arrow @click-left="router.push('/admin/dashboard')" />

    <main class="mx-auto w-full max-w-3xl px-4 pt-4">
      <!-- 步骤指示 -->
      <ol class="mb-4 flex items-center gap-2 text-xs">
        <li
          v-for="(label, i) in stepLabels"
          :key="label"
          class="flex items-center gap-1.5"
        >
          <span
            class="flex h-5 w-5 items-center justify-center rounded-full border text-[11px] font-semibold"
            :class="{
              'border-blue-600 bg-blue-600 text-white': stepIndex === i,
              'border-blue-300 text-blue-500': stepIndex > i,
              'border-slate-200 text-slate-400': stepIndex < i,
            }"
          >
            <van-icon v-if="stepIndex > i" name="success" size="12" />
            <template v-else>{{ i + 1 }}</template>
          </span>
          <span :class="stepIndex === i ? 'font-medium text-slate-900' : 'text-slate-500'">{{ label }}</span>
          <span v-if="i < stepLabels.length - 1" class="mx-1 h-px w-6 bg-slate-200" />
        </li>
      </ol>

      <!-- Step 1: 粘贴文本 -->
      <section v-if="step === 'input'" class="rounded-xl border border-slate-200 bg-white">
        <header class="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <div>
            <h2 class="text-sm font-semibold text-slate-900">订单原文</h2>
            <p class="mt-0.5 text-xs text-slate-500">粘贴微信聊天中复制的订单文本，系统自动识别字段</p>
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
            class="import-textarea h-64 w-full resize-none rounded-lg border border-slate-200 bg-slate-50/50 p-3 font-mono text-[13px] leading-6 text-slate-800 focus:border-blue-500 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100"
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
            class="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="parsing || !rawText.trim()"
            @click="handleParse"
          >
            {{ parsing ? "识别中…" : "识别并预览" }}
          </button>
        </footer>
      </section>

      <!-- Step 2: 校对确认 -->
      <section v-else-if="step === 'preview'" class="space-y-3">
        <div class="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600">
          <span>识别 <b class="text-slate-900">{{ parsedItems.length }}</b> 条</span>
          <span>已选 <b class="text-blue-600">{{ checkedItems.size }}</b> 条</span>
          <span v-if="pendingPriceCount" class="text-amber-600">{{ pendingPriceCount }} 条待定价</span>
          <span v-if="reviewCount" class="text-sky-600">{{ reviewCount }} 条建议复核</span>
          <button class="ml-auto text-blue-600" @click="toggleAll">
            {{ allChecked ? "取消全选" : "全选" }}
          </button>
        </div>

        <article
          v-for="(item, index) in parsedItems"
          :key="index"
          class="rounded-xl border bg-white"
          :class="checkedItems.has(index) ? 'border-blue-300 ring-1 ring-blue-100' : 'border-slate-200'"
        >
          <div class="flex items-start gap-3 px-4 py-3">
            <van-checkbox :model-value="checkedItems.has(index)" class="mt-0.5 shrink-0" @click.stop="toggleCheck(index)" />
            <div class="min-w-0 flex-1" @click="toggleCheck(index)">
              <div class="flex flex-wrap items-center gap-2">
                <span class="break-all font-mono text-xs text-slate-500">{{ item.raw_id }}</span>
                <span
                  class="rounded border px-1.5 py-0.5 text-[10px] font-medium"
                  :class="itemState(item).cls"
                  :title="itemState(item).label === '课酬过低' ? tooCheapLabel(item) : undefined"
                >
                  {{ itemState(item).label }}
                </span>
                <span v-if="item.is_summer_vacation" class="rounded border border-rose-200 bg-rose-50 px-1.5 py-0.5 text-[10px] text-rose-600">
                  寒暑假 ×2.5
                </span>
                <span v-if="item.parser_source" class="ml-auto text-[10px] text-slate-300">{{ item.parser_source }}</span>
              </div>
              <div class="mt-1 text-sm font-semibold text-slate-900">{{ item.grade_subject }}</div>
              <div class="mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs text-slate-500">
                <span class="truncate">课酬：{{ Number(item.base_price) > 0 ? `¥${item.base_price}/次` : item.price_total }}</span>
                <span>每周 {{ item.weekly_frequency }} 次<template v-if="item.lesson_count"> · 共 {{ item.lesson_count }} 次</template></span>
                <span class="truncate col-span-2">{{ item.fuzzy_address }}</span>
              </div>
            </div>
            <button
              class="shrink-0 self-center rounded-md border px-2 py-1 text-xs"
              :class="editingIdx === index ? 'border-slate-300 text-slate-600' : 'border-blue-200 text-blue-600'"
              @click.stop="editingIdx = editingIdx === index ? null : index"
            >
              {{ editingIdx === index ? "收起" : "编辑" }}
            </button>
          </div>

          <!-- 展开编辑 -->
          <div v-if="editingIdx === index" class="border-t border-slate-100 bg-slate-50/60 px-4 py-3">
            <div class="grid grid-cols-2 gap-x-3 gap-y-2.5">
              <label class="import-field">
                <span>年级科目</span>
                <input v-model="item.grade_subject" type="text" />
              </label>
              <label class="import-field">
                <span>单次课酬（¥）</span>
                <input v-model.number="item.base_price" type="number" min="0" step="10" placeholder="0 = 待教员报价" />
              </label>
              <label class="import-field">
                <span>每周次数</span>
                <input v-model.number="item.weekly_frequency" type="number" min="1" max="14" />
              </label>
              <label class="import-field">
                <span>展示地址</span>
                <input v-model="item.fuzzy_address" type="text" />
              </label>
              <label class="import-field">
                <span>真实门牌</span>
                <input v-model="item.exact_address" type="text" placeholder="尾款解锁后可见" />
              </label>
              <label class="import-field">
                <span>家长电话</span>
                <input v-model="item.parent_phone" type="tel" placeholder="选填" />
              </label>
              <label class="import-field col-span-2">
                <span>教员要求</span>
                <input v-model="item.requirements" type="text" />
              </label>
            </div>

            <div class="mt-3 flex items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2">
              <label class="flex items-center gap-2 text-xs text-slate-600">
                <van-switch v-model="item.is_summer_vacation" size="18px" />
                寒暑假密集单（费率 ×2.5）
              </label>
              <div class="text-right text-xs">
                <template v-if="feeOf(item)">
                  <span class="text-slate-500">试算：</span>
                  <b class="text-blue-600">¥{{ feeOf(item)!.total }}</b>
                  <span class="text-slate-400">（定金 ¥{{ feeOf(item)!.deposit }} + 尾款 ¥{{ feeOf(item)!.balance }}）</span>
                </template>
                <template v-else-if="Number(item.base_price) > 0">
                  <span class="text-red-500">{{ tooCheapLabel(item) }}，请调整课酬或清空价格改为待定价</span>
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

      <!-- Step 3: 完成 -->
      <section v-else class="rounded-xl border border-slate-200 bg-white p-8 text-center">
        <div class="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50">
          <van-icon name="passed" size="28" color="#059669" />
        </div>
        <h2 class="mt-4 text-base font-semibold text-slate-900">导入完成</h2>
        <p class="mt-1 text-sm text-slate-500">
          成功导入 <b class="text-slate-900">{{ importResult?.imported ?? 0 }}</b> 条订单
          <template v-if="importResult?.skipped?.length">
            ，跳过 {{ importResult.skipped.length }} 条重复编号
          </template>
        </p>
        <p v-if="importResult?.skipped?.length" class="mx-auto mt-2 max-w-md break-all text-xs text-slate-400">
          重复编号：{{ importResult.skipped.join("、") }}
        </p>
        <div class="mt-6 flex justify-center gap-3">
          <button
            class="rounded-lg border border-slate-200 px-4 py-2 text-sm text-slate-600 hover:bg-slate-50"
            @click="startAnotherBatch"
          >
            继续导入
          </button>
          <button
            class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white"
            @click="router.push('/admin/orders')"
          >
            查看订单列表
          </button>
        </div>
      </section>
    </main>

    <!-- Step 2 底部操作条 -->
    <div
      v-if="step === 'preview'"
      class="fixed inset-x-0 bottom-[50px] z-20 border-t border-slate-200 bg-white px-4 py-3"
    >
      <div class="mx-auto flex w-full max-w-3xl gap-3">
        <button
          class="rounded-lg border border-slate-200 px-4 py-2.5 text-sm text-slate-600"
          @click="backToInput"
        >
          返回修改
        </button>
        <button
          class="flex-1 rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          :disabled="importing || checkedItems.size === 0"
          @click="handleImport"
        >
          {{ importing ? "导入中…" : `确认导入 ${checkedItems.size} 条` }}
        </button>
      </div>
    </div>

    <!-- 处理遮罩 -->
    <van-overlay :show="parsing || importing">
      <div class="flex flex-col items-center justify-center h-full gap-3">
        <van-loading type="spinner" size="32" color="white" />
        <span class="text-sm text-white">
          {{ parsing ? "AI 正在识别字段，通常需要 10~30 秒" : "正在导入订单…" }}
        </span>
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
  border-color: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.08);
}
</style>