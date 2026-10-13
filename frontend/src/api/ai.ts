import client from "./client";

export interface FindOrderConditions {
  subject?: string | null;
  grade?: string | null;
  min_base_price?: number | null;
  max_base_price?: number | null;
  radius_km?: number | null;
  anchor?: string | null;
}

/** 找单结果卡片：订单列表同款字段 + 距离（无距离条件时为 null） */
export interface AiOrderItem {
  id: number;
  raw_id: string;
  grade_subject: string;
  price_total: string;
  base_price: number;
  fuzzy_address: string;
  status: string;
  needs_manual_price: boolean;
  calculated_info_fee: number;
  deposit_amount: number;
  balance_amount: number;
  weekly_frequency: number;
  lng: number;
  lat: number;
  created_at: string | null;
  expired_at: string | null;
  distance_km: number | null;
}

export interface FindOrdersResponse {
  conditions: FindOrderConditions;
  warnings: string[];
  total_matched: number;
  scanned: number;
  items: AiOrderItem[];
}

/** 相似订单：找单卡片同款字段 + 语义相似度（余弦，0~1） */
export interface SimilarOrderItem extends AiOrderItem {
  similarity: number;
}

export interface KnowledgeDoc {
  id: number;
  tenant_id: number | null;
  title: string;
  source_type: string;
  status: string;
  chunk_count: number;
  fail_reason: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Citation {
  index: number;
  document_id: number;
  title: string;
  snippet: string;
  score: number;
}

export interface AssistantAnswer {
  answer: string;
  citations: Citation[];
  latency_ms: number | null;
}

/** 设备定位（"附近"默认锚点）：浏览器 Geolocation 授权一次后缓存于本会话 */
export interface DeviceLocation {
  lng: number;
  lat: number;
}

/**
 * AI 助手（阶段 1a 找单 / 1b 知识库问答）。
 * AI 只产出条件或文案；数据查询、租户过滤、脱敏全在后端既有代码路径，
 * 结果永远可以在订单管理页 / 知识库管理页人工复核。
 */
export const aiApi = {
  /** 自然语言找单：条件解析在后端，warnings 如实透出；
   *  location 为设备定位——"附近"未指地点时后端优先按它计算 */
  findOrders: (query: string, location?: DeviceLocation) =>
    client
      .post<FindOrdersResponse>("/ai/find-orders", {
        query,
        anchor_lng: location?.lng,
        anchor_lat: location?.lat,
      })
      .then((r) => r.data),

  /** 知识库问答：回答带来源引用；无依据时后端如实说明 */
  ask: (question: string) =>
    client.post<AssistantAnswer>("/ai/assistant/query", { question }).then((r) => r.data),

  /** 上传知识文档（粘贴文本）；后端同步切分+向量化，失败置 failed 可重传 */
  createDocument: (title: string, content: string) =>
    client.post<KnowledgeDoc>("/ai/knowledge/documents", { title, content }).then((r) => r.data),

  /** 文档列表：本租户 + 平台公共库 */
  listDocuments: () =>
    client
      .get<{ items: KnowledgeDoc[]; total: number }>("/ai/knowledge/documents")
      .then((r) => r.data),

  deleteDocument: (id: number) =>
    client.delete<{ ok: boolean }>(`/ai/knowledge/documents/${id}`).then((r) => r.data),

  /** 相似订单：向量初筛 + 后端实时状态/租户复核；已有索引时零嵌入调用 */
  similarOrders: (orderId: number) =>
    client.get<{ items: SimilarOrderItem[] }>(`/ai/orders/${orderId}/similar`).then((r) => r.data),
};
