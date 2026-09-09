/**
 * 与后端 models/schemas.py 对齐的响应类型。
 * 后端契约变更时此处同步修改，让视图层在编译期感知字段变化。
 */

export type OrderStatus = "recruiting" | "trial_in_progress" | "completed" | "archived";

export type ApplicationStatus =
  | "pending"
  | "shortlisted"
  | "trial_in_progress"
  | "deposit_paid"
  | "balance_paid"
  | "completed"
  | "rejected"
  | "refunded"
  | "forfeited";

export type FinancialType = "deposit_in" | "balance_in" | "refund_out" | "forfeit";

/** 订单列表项（GET /orders/ 的 items 元素） */
export interface OrderBrief {
  id: number;
  raw_id: string;
  grade_subject: string;
  price_total: string;
  base_price: number;
  fuzzy_address: string;
  status: OrderStatus;
  needs_manual_price: boolean;
  calculated_info_fee: number;
  deposit_amount: number;
  balance_amount: number;
  weekly_frequency: number;
  lng: number;
  lat: number;
  created_at: string | null;
  expired_at: string | null;
}

export interface OrderListResponse {
  items: OrderBrief[];
  page: number;
  page_size: number;
  total: number;
}

/** 订单详情（GET /orders/{id}，教员视角敏感字段为 null） */
export interface OrderDetail {
  id: number;
  raw_id: string;
  raw_text: string;
  grade_subject: string;
  requirements: string | null;
  exact_address: string | null;
  parent_phone: string | null;
  price_total: string;
  base_price: number;
  weekly_frequency: number;
  is_summer_vacation: boolean;
  fuzzy_address: string;
  subway_remark: string | null;
  lng: number;
  lat: number;
  calculated_info_fee: number;
  deposit_amount: number;
  balance_amount: number;
  needs_manual_price: boolean;
  status: OrderStatus;
  created_at: string | null;
  expired_at: string | null;
}

export interface TransitResponse {
  order_id: number;
  previous_status: OrderStatus;
  current_status: OrderStatus;
}

export interface BatchStatusUpdateResponse {
  updated: number;
  skipped: number;
}

export interface BatchImportResponse {
  imported: number;
  skipped_duplicates: string[];
}

export interface AddressUnlockResponse {
  exact_address: string | null;
  parent_phone: string | null;
}

/** 橱窗/推荐接口复用的订单展示结构（public.py _build_order_brief） */
export interface PublicOrderBrief {
  id: number;
  raw_id: string;
  grade_subject: string;
  price_total: string;
  base_price: number;
  calculated_info_fee: number;
  deposit_amount: number;
  balance_amount: number;
  needs_manual_price: boolean;
  fuzzy_address: string;
  subway_remark: string | null;
  lng: number;
  lat: number;
  weekly_frequency: number;
  is_summer_vacation: boolean;
  expired_at: string | null;
}

export interface TeacherSummary {
  id: number;
  name: string;
  school?: string | null;
  major?: string | null;
  grade?: string | null;
  highlights?: string | null;
}

export interface ResumeBrief {
  id: number;
  title: string;
}

/** 投递（models/schemas.py ApplicationResponse） */
export interface ApplicationItem {
  id: number;
  order_id: number;
  raw_order_id: string | null;
  teacher_id: number;
  tenant_id: number;
  tenant_name: string | null;
  order_grade_subject: string | null;
  order_price_total: string | null;
  order_fuzzy_address: string | null;
  resume_id: number | null;
  teacher?: TeacherSummary | null;
  status: ApplicationStatus;
  proposed_price: number | null;
  applied_at: string;
  shortlisted_at: string | null;
  deposit_paid_at: string | null;
  balance_paid_at: string | null;
  rejected_at: string | null;
  refunded_at: string | null;
}

export interface ApplicationSummaryResponse {
  total_applications: number;
  order_counts: Record<string, number>;
}

export interface OrderReviewItem {
  id: number;
  order_id: number;
  application_id: number;
  teacher_id: number;
  rating: number;
  comment: string | null;
  created_at: string;
  updated_at: string | null;
}

/** 财务流水（models/schemas.py FinancialRecordResponse） */
export interface FinancialRecordItem {
  id: number;
  order_id: number;
  tenant_id: number;
  teacher_id: number;
  amount: number;
  type: FinancialType;
  remark: string | null;
  operator_role: string | null;
  created_at: string;
  order_subject: string | null;
  order_raw_id: string | null;
  teacher_name: string | null;
  teacher_school: string | null;
  raw_order_id: string | null;
}

export interface FinancialSummaryResponse {
  deposit_in: number;
  balance_in: number;
  refund_out: number;
  forfeit: number;
  net_amount: number;
  records: FinancialRecordItem[];
}

export interface TeacherFeeSummaryResponse {
  total_paid: number;
  total_refunded: number;
  total_forfeit: number;
  records: FinancialRecordItem[];
}
