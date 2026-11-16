<script setup lang="ts">
/**
 * 订单编辑弹层——订单管理页与订单工作区共用（此前内联在 OrdersList，
 * 审核页/工作区要看详情+编辑时无法复用）。
 * 打开时按 orderId 拉取详情填表，保存走 PATCH /orders/{id}；
 * 金额与费率由服务端重算（base_price 变更时），与导入口径一致。
 */
import { computed, ref, watch } from "vue";
import { showToast, showSuccessToast } from "vant";
import type { FieldInstance } from "vant";
import { getApiErrorMessage } from "@/utils/apiError";
import { ordersApi } from "@/api/orders";
import type { OrderDetail } from "@/api/types";
import { loadAMap } from "@/utils/amap";
import AppButton from "@/components/ui/AppButton.vue";

const show = defineModel<boolean>("show", { default: false });

const props = defineProps<{ orderId: number | null }>();

const emit = defineEmits<{ (e: "saved"): void }>();

/** 编辑表单字段集（与后端 OrderUpdateRequest 对齐的子集） */
interface OrderEditForm {
  grade_subject: string;
  requirements: string;
  price_total: string;
  base_price: number;
  weekly_frequency: number;
  is_summer_vacation: boolean;
  fuzzy_address: string;
  subway_remark: string;
  exact_address: string;
  parent_phone: string;
  lng: number;
  lat: number;
}

const editForm = ref<OrderEditForm | null>(null);
const editingOrder = ref<OrderDetail | null>(null);
const saving = ref(false);
/** 打开时的展示地址：保存时对比判断"地址改了"→ 自动重新定位坐标 */
const originalAddress = ref("");

const addressChanged = computed(
  () =>
    Boolean(editForm.value) &&
    String(editForm.value?.fuzzy_address ?? "").trim() !== originalAddress.value.trim(),
);

/** 高德地理编码：地址文字 → 坐标；失败返回 null（Geocoder 已在 loader 预载） */
async function geocodeAddress(addr: string): Promise<{ lng: number; lat: number } | null> {
  try {
    const AMap = await loadAMap();
    return await new Promise((resolve) => {
      const geocoder = new AMap.Geocoder();
      geocoder.getLocation(addr, (status, result) => {
        const location = result.geocodes?.[0]?.location;
        if (status === "complete" && location) {
          resolve({ lng: location.lng, lat: location.lat });
        } else {
          resolve(null);
        }
      });
    });
  } catch {
    return null;
  }
}

// 必填三项的字段级错误（Login 内联错误模式）：blur 校验、提交时聚焦第一个非法字段
const gradeSubjectError = ref("");
const priceTotalError = ref("");
const fuzzyAddressError = ref("");
const gradeFieldRef = ref<FieldInstance>();
const priceFieldRef = ref<FieldInstance>();
const addressFieldRef = ref<FieldInstance>();
// 经纬度是机器字段（AI 定位产物），中介一般不改：折叠进高级区，不再裸露在主表单
const advancedOpen = ref(false);
const relocating = ref(false);

/** 按展示地址重新定位：地理编码失败/偏差的单（如落在 0,0 或外省），
 * 中介改完地址文字后一键重算坐标，不必手抄经纬度 */
async function relocateByAddress() {
  if (!editForm.value || relocating.value) return;
  const addr = String(editForm.value.fuzzy_address ?? "").trim();
  if (!addr) {
    showToast("请先填写展示地址，再重新定位");
    return;
  }
  relocating.value = true;
  const location = await geocodeAddress(addr);
  relocating.value = false;
  if (location) {
    editForm.value.lng = location.lng;
    editForm.value.lat = location.lat;
    showSuccessToast("已按地址重新定位，请保存");
  } else {
    showToast("定位失败：请核对地址文字（建议带上区县）后重试");
  }
}

function validateField(field: "grade_subject" | "price_total" | "fuzzy_address"): boolean {
  if (!editForm.value) return false;
  const value = String(editForm.value[field] ?? "").trim();
  let error = "";
  if (!value) {
    if (field === "grade_subject") error = "必填——年级科目是教员匹配与推荐的主要依据";
    else if (field === "price_total") error = "必填——课酬向教员与家长双端展示，请补齐";
    else error = "必填——展示地址决定教员能否评估通勤，请补齐";
  }
  if (field === "grade_subject") gradeSubjectError.value = error;
  else if (field === "price_total") priceTotalError.value = error;
  else fuzzyAddressError.value = error;
  return !error;
}

watch(
  show,
  async (visible) => {
    if (!visible || !props.orderId) {
      editForm.value = null;
      return;
    }
    gradeSubjectError.value = "";
    priceTotalError.value = "";
    fuzzyAddressError.value = "";
    advancedOpen.value = false;
    try {
      const detail = await ordersApi.getOrder(props.orderId);
      editingOrder.value = detail;
      editForm.value = {
        grade_subject: detail.grade_subject,
        requirements: detail.requirements || "",
        price_total: detail.price_total,
        base_price: detail.base_price,
        weekly_frequency: detail.weekly_frequency,
        is_summer_vacation: detail.is_summer_vacation,
        fuzzy_address: detail.fuzzy_address,
        subway_remark: detail.subway_remark || "",
        exact_address: detail.exact_address || "",
        parent_phone: detail.parent_phone || "",
        lng: detail.lng,
        lat: detail.lat,
      };
      // 坐标落 0,0 = 地理编码失败的待校准单：自动展开高级区露出"重新定位"
      advancedOpen.value = detail.lng === 0 && detail.lat === 0;
      originalAddress.value = detail.fuzzy_address;
    } catch (e) {
      showToast(getApiErrorMessage(e, "订单详情加载失败：网络或服务暂时不可用，请重试"));
      show.value = false;
    }
  },
  { immediate: true }
);

const canSubmit = computed(() =>
  Boolean(
    editForm.value &&
      String(editForm.value.grade_subject).trim() &&
      String(editForm.value.price_total).trim() &&
      String(editForm.value.fuzzy_address).trim(),
  ),
);

async function saveEdit() {
  if (!editingOrder.value || !editForm.value) return;
  const okGrade = validateField("grade_subject");
  const okPrice = validateField("price_total");
  const okAddress = validateField("fuzzy_address");
  if (!okGrade) {
    gradeFieldRef.value?.focus();
    return;
  }
  if (!okPrice) {
    priceFieldRef.value?.focus();
    return;
  }
  if (!okAddress) {
    addressFieldRef.value?.focus();
    return;
  }
  // 发送前去空白，与历史行为一致
  editForm.value.grade_subject = String(editForm.value.grade_subject ?? "").trim();
  editForm.value.price_total = String(editForm.value.price_total ?? "").trim();
  editForm.value.fuzzy_address = String(editForm.value.fuzzy_address ?? "").trim();
  saving.value = true;
  try {
    // 地址改了 → 保存前自动重新定位（否则坐标停留在旧位置，地图不动）；
    // 定位失败则不保存，避免"改了地址、图钉没动"的静默错位
    if (addressChanged.value) {
      const location = await geocodeAddress(editForm.value.fuzzy_address);
      if (!location) {
        showToast("新地址定位失败，未保存：请核对地址文字（建议带区县），或在坐标微调中手动填经纬度");
        saving.value = false;
        return;
      }
      editForm.value.lng = location.lng;
      editForm.value.lat = location.lat;
    }
    await ordersApi.updateOrder(editingOrder.value.id, editForm.value);
    showSuccessToast("已保存");
    show.value = false;
    emit("saved");
  } catch (e) {
    showToast(getApiErrorMessage(e, "保存失败：网络异常，请检查网络后重试"));
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <van-popup v-model:show="show" position="bottom" round>
    <div v-if="editForm" class="p-4 max-h-[82vh] overflow-y-auto">
      <div class="mb-3 flex items-center justify-between">
        <div class="min-w-0">
          <div class="text-base font-semibold text-primary">编辑订单</div>
          <div class="mt-0.5 truncate text-xs text-muted">#{{ editingOrder?.raw_id }} · {{ editingOrder?.grade_subject }}</div>
        </div>
        <button
          class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-soft text-secondary"
          @click="show = false"
        >
          <van-icon name="cross" />
        </button>
      </div>
      <van-cell-group inset>
        <van-field
          ref="gradeFieldRef"
          v-model="editForm.grade_subject"
          label="年级科目"
          required
          clearable
          :error-message="gradeSubjectError"
          @update:model-value="gradeSubjectError = ''"
          @blur="validateField('grade_subject')"
        />
        <van-field
          ref="priceFieldRef"
          v-model="editForm.price_total"
          label="课酬文本"
          required
          clearable
          :error-message="priceTotalError"
          @update:model-value="priceTotalError = ''"
          @blur="validateField('price_total')"
        />
        <van-field v-model.number="editForm.base_price" label="单次课酬" type="number" />
        <van-field v-model.number="editForm.weekly_frequency" label="每周次数" type="number" />
        <van-field
          ref="addressFieldRef"
          v-model="editForm.fuzzy_address"
          label="展示地址"
          required
          clearable
          :error-message="fuzzyAddressError"
          @update:model-value="fuzzyAddressError = ''"
          @blur="validateField('fuzzy_address')"
        />
        <div
          v-if="addressChanged"
          class="mx-4 mb-1 rounded-md bg-brand-50 px-2.5 py-1.5 text-caption leading-4 text-brand-700"
        >
          地址已修改：保存时将自动重新定位坐标（定位失败会提示，不会静默错位）
        </div>
        <van-field v-model="editForm.subway_remark" label="交通备注" />
        <van-field v-model="editForm.exact_address" label="真实地址" />
        <van-field v-model="editForm.parent_phone" label="家长电话" />
        <van-cell
          title="坐标微调"
          label="AI 自动定位一般无需改动；地图偏移时才手动修正"
          is-link
          :arrow-direction="advancedOpen ? 'up' : 'down'"
          @click="advancedOpen = !advancedOpen"
        />
        <template v-if="advancedOpen">
          <van-cell>
            <AppButton
              size="sm"
              variant="secondary"
              block
              :disabled="relocating"
              :loading="relocating"
              @click="relocateByAddress"
            >
              按展示地址重新定位
            </AppButton>
          </van-cell>
          <van-field v-model.number="editForm.lng" label="经度" type="number" />
          <van-field v-model.number="editForm.lat" label="纬度" type="number" />
        </template>
        <van-field v-model="editForm.requirements" label="教员要求" type="textarea" rows="3" />
        <van-cell title="寒暑假单">
          <template #right-icon>
            <van-switch v-model="editForm.is_summer_vacation" size="20" />
          </template>
        </van-cell>
      </van-cell-group>
      <div class="mt-4 grid grid-cols-2 gap-3">
        <AppButton size="md" variant="secondary" @click="show = false">取消</AppButton>
        <AppButton
          size="md"
          :disabled="saving || !canSubmit"
          @click="saveEdit"
        >
          保存
        </AppButton>
      </div>
    </div>
  </van-popup>
</template>
