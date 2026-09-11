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
  created_at: string | null;
}

export interface TeacherSummary {
  id: number;
  name: string;
  gender: string;
  school: string;
  is_985_211: boolean;
  is_985: boolean;
  is_211: boolean;
  is_double_first_class: boolean;
  major?: string | null;
  grade?: string | null;
  highlights?: string | null;
  /** 联系方式仅 B 端投递列表下发 */
  phone?: string | null;
  wechat_id?: string | null;
  /** 信用画像：投递列表接口按批量聚合填充 */
  completed_count?: number;
  violation_count?: number;
  avg_rating?: number | null;
}

/** 投递携带的简历快照（后端 TeacherResumeResponse） */
export interface ApplicationResume {
  id: number;
  teacher_id: number;
  title: string;
  teaching_subjects: string;
  teaching_grades: string;
  experience: string;
  strengths?: string | null;
  availability?: string | null;
  expected_rate?: string | null;
  is_default?: boolean;
  created_at?: string;
  updated_at?: string | null;
}

export interface ResumeBrief {
  id: number;
  title: string;
}

// ── 通知 ──

export interface NotificationItem {
  id: number;
  title: string;
  content?: string | null;
  application_id?: number | null;
  order_id?: number | null;
  created_at: string;
  is_read: boolean;
}

export interface NotificationList {
  unread_count: number;
  items: NotificationItem[];
}

export interface MarkedResponse {
  marked: number;
}

export interface OkResponse {
  ok: boolean;
}

// ── 认证/会话 ──

/** 教员完整资料（后端 TeacherResponse） */
export interface TeacherProfile {
  id: number;
  name: string;
  gender: string;
  school: string;
  is_985_211: boolean;
  is_985: boolean;
  is_211: boolean;
  is_double_first_class: boolean;
  major?: string | null;
  grade?: string | null;
  highlights?: string | null;
  phone?: string | null;
  wechat_id?: string | null;
  home_area?: string | null;
  lng?: number | null;
  lat?: number | null;
}

/** 中介简要信息（后端 TenantBrief） */
export interface TenantBriefInfo {
  id: number;
  tenant_name: string;
  invite_code: string;
  contact_wechat?: string | null;
}

/** GET /auth/me/profile —— teacher/tenant 按角色二选一出现 */
export interface MeProfileResponse {
  sub: string;
  role: "teacher" | "tenant_admin" | "super_admin";
  tenant_id: number | null;
  teacher?: TeacherProfile;
  tenant?: TenantBriefInfo;
}

/** 登录/注册响应（后端 TokenResponse） */
export interface TokenResponse {
  token: string;
  role: "teacher" | "tenant_admin" | "super_admin";
  teacher?: TeacherProfile | null;
  tenant?: TenantBriefInfo | null;
}

export interface DetailResponse {
  detail: string;
}

// ── AI 批量解析 ──

/** POST /orders/batch-parse 的 items 元素（后端 ParsedOrderItem，服务端填充字段可空） */
export interface ParsedOrderItem {
  raw_id: string;
  raw_text: string;
  grade_subject: string;
  requirements?: string | null;
  price_total: string;
  base_price: number;
  weekly_frequency: number;
  is_summer_vacation: boolean;
  address: string;
  subway_remark?: string | null;
  lesson_count?: number | null;
  lesson_hours: number;
  lng?: number | null;
  lat?: number | null;
  fuzzy_address?: string | null;
  calculated_info_fee?: number | null;
  deposit_amount?: number | null;
  balance_amount?: number | null;
  needs_manual_price: boolean;
  parser_source: string;
  parser_confidence: string;
  missing_fields: string[];
  needs_manual_review: boolean;
}

export interface BatchParseResponse {
  items: ParsedOrderItem[];
  count: number;
  /** 部分段解析失败时的原因列表：成功段照常返回 */
  warnings?: string[];
}

/** 导入确认页条目：在解析结果上追加客户端可编辑的真实门牌/家长电话（对应后端 OrderImportItem） */
export interface OrderDraftItem extends ParsedOrderItem {
  exact_address?: string | null;
  parent_phone?: string | null;
}

// ── 橱窗 / 推荐 ──

/** GET /public/agent/{code}/board（后端 AgentBoardResponse） */
export interface AgentBoardResponse {
  tenant_name: string;
  invite_code: string;
  contact_wechat?: string | null;
  orders: PublicOrderBrief[];
}

export interface RecommendationScoreBreakdown {
  distance: number;
  subject: number;
  grade: number;
  school: number;
  price: number;
  history: number;
}

/** GET /recommendations/{code} 的 items 元素（后端 TeacherOrderRecommendationItem） */
export interface TeacherOrderRecommendationItem extends PublicOrderBrief {
  status: OrderStatus;
  total_score: number;
  score_breakdown: RecommendationScoreBreakdown;
  reasons: string[];
  distance_km?: number | null;
  already_applied: boolean;
  application_id?: number | null;
  application_status?: ApplicationStatus | null;
}

export interface TeacherOrderRecommendationResponse {
  tenant_name: string;
  invite_code: string;
  count: number;
  items: TeacherOrderRecommendationItem[];
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
  resume?: ApplicationResume | null;
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
