<script setup lang="ts">
/**
 * 订单编辑弹层——订单管理页与订单工作区共用（此前内联在 OrdersList，
 * 审核页/工作区要看详情+编辑时无法复用）。
 * 打开时按 orderId 拉取详情填表，保存走 PATCH /orders/{id}；
 * 金额与费率由服务端重算（base_price 变更时），与导入口径一致。
 */
import { computed, ref, watch } from "vue";
import { showToast, showSuccessToast } from "vant";
import { ordersApi } from "@/api/orders";
import type { OrderDetail } from "@/api/types";

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

watch(
  show,
  async (visible) => {
    if (!visible || !props.orderId) {
      editForm.value = null;
      return;
    }
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
    } catch {
      showToast("加载订单失败");
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
  const gradeSubject = String(editForm.value.grade_subject || "").trim();
  const priceTotal = String(editForm.value.price_total || "").trim();
  const fuzzyAddress = String(editForm.value.fuzzy_address || "").trim();
  if (!gradeSubject || !priceTotal || !fuzzyAddress) {
    showToast("请填写年级科目、课酬文本和展示地址");
    return;
  }
  editForm.value.grade_subject = gradeSubject;
  editForm.value.price_total = priceTotal;
  editForm.value.fuzzy_address = fuzzyAddress;
  saving.value = true;
  try {
    await ordersApi.updateOrder(editingOrder.value.id, editForm.value);
    showSuccessToast("已保存");
    show.value = false;
    emit("saved");
  } catch {
    showToast("保存失败");
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
        <van-field v-model="editForm.grade_subject" label="年级科目" />
        <van-field v-model="editForm.price_total" label="课酬文本" />
        <van-field v-model.number="editForm.base_price" label="单次课酬" type="number" />
        <van-field v-model.number="editForm.weekly_frequency" label="每周次数" type="number" />
        <van-field v-model="editForm.fuzzy_address" label="展示地址" />
        <van-field v-model="editForm.subway_remark" label="交通备注" />
        <van-field v-model="editForm.exact_address" label="真实地址" />
        <van-field v-model="editForm.parent_phone" label="家长电话" />
        <van-field v-model.number="editForm.lng" label="经度" type="number" />
        <van-field v-model.number="editForm.lat" label="纬度" type="number" />
        <van-field v-model="editForm.requirements" label="教员要求" type="textarea" rows="3" />
        <van-cell title="寒暑假单">
          <template #right-icon>
            <van-switch v-model="editForm.is_summer_vacation" size="20" />
          </template>
        </van-cell>
      </van-cell-group>
      <div class="mt-4 grid grid-cols-2 gap-3">
        <button class="rounded-full border border-default bg-white py-2.5 text-sm font-medium text-secondary" @click="show = false">取消</button>
        <button
          class="header-gradient rounded-full py-2.5 text-sm font-semibold text-white disabled:opacity-60"
          :disabled="saving || !canSubmit"
          @click="saveEdit"
        >
          保存
        </button>
      </div>
    </div>
  </van-popup>
</template>
