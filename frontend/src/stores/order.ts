import { defineStore } from "pinia";
import { ref } from "vue";
import { ordersApi, publicApi } from "@/api/orders";

export interface OrderBrief {
  id: number;
  grade_subject: string;
  price_total: string;
  base_price: number;
  weekly_frequency: number;
  fuzzy_address: string;
  subway_remark?: string;
  lng: number;
  lat: number;
  calculated_info_fee: number;
  deposit_amount: number;
  balance_amount: number;
  needs_manual_price: boolean;
  created_at: string;
}

export interface ParsedOrderItem {
  raw_id: string;
  raw_text: string;
  grade_subject: string;
  requirements: string;
  price_total: string;
  base_price: number;
  weekly_frequency: number;
  is_summer_vacation: boolean;
  address: string;
  subway_remark?: string;
  lesson_count?: number | null;
  lesson_hours: number;
  lng: number;
  lat: number;
  fuzzy_address: string;
  exact_address?: string;
  parent_phone?: string;
  calculated_info_fee: number;
  deposit_amount: number;
  balance_amount: number;
  needs_manual_price: boolean;
  parser_source?: string;
  parser_confidence?: string;
  missing_fields?: string[];
  needs_manual_review?: boolean;
}

export const useOrderStore = defineStore("order", () => {
  const boardOrders = ref<OrderBrief[]>([]);
  const boardTenantName = ref("");
  const boardInviteCode = ref("");
  const loading = ref(false);

  // 加载橱窗地图数据
  async function loadBoard(inviteCode: string) {
    loading.value = true;
    try {
      const res = await publicApi.getBoard(inviteCode);
      boardOrders.value = res.orders;
      boardTenantName.value = res.tenant_name || "";
      boardInviteCode.value = res.invite_code || inviteCode;
    } finally {
      loading.value = false;
    }
  }

  // 批量解析
  async function batchParse(rawText: string) {
    loading.value = true;
    try {
      const res = await ordersApi.batchParse(rawText);
      return res;
    } finally {
      loading.value = false;
    }
  }

  // 批量导入
  async function batchImport(items: ParsedOrderItem[]) {
    loading.value = true;
    try {
      const res = await ordersApi.batchImport(items);
      return res;
    } finally {
      loading.value = false;
    }
  }

  return {
    boardOrders,
    boardTenantName,
    boardInviteCode,
    loading,
    loadBoard,
    batchParse,
    batchImport,
  };
});
