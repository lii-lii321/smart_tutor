import { defineStore } from "pinia";
import { ref } from "vue";
import { ordersApi, publicApi } from "@/api/orders";
import type { OrderDraftItem, ParsedOrderItem, PublicOrderBrief } from "@/api/types";

// 橱窗订单与解析条目的类型统一走 api/types（与后端 schema 对齐），本地不再各存副本
export type OrderBrief = PublicOrderBrief;
export type { ParsedOrderItem, OrderDraftItem };

export const useOrderStore = defineStore("order", () => {
  const boardOrders = ref<OrderBrief[]>([]);
  const boardTenantName = ref("");
  const boardInviteCode = ref("");
  const boardContactWechat = ref("");
  const loading = ref(false);

  // 加载橱窗地图数据
  async function loadBoard(inviteCode: string) {
    loading.value = true;
    try {
      const res = await publicApi.getBoard(inviteCode);
      boardOrders.value = res.orders;
      boardTenantName.value = res.tenant_name || "";
      boardInviteCode.value = res.invite_code || inviteCode;
      boardContactWechat.value = res.contact_wechat || "";
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
    boardContactWechat,
    loading,
    loadBoard,
    batchParse,
    batchImport,
  };
});
