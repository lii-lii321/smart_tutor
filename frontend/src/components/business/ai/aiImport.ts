/**
 * AI Import 展示适配器（Batch 03）：
 * 后端 ParsedOrderItem → AI Import UI Model → 解析结果卡片/异常摘要。
 *
 * 置信度红线（规格书）：后端下发的是**定性置信度** parser_confidence
 * （"high"/"medium"/"ai"，见 services/parser.py:289,520），不是数字百分比。
 * 适配器只翻译定性等级，**绝不生成数值百分比**；字段缺失以
 * missing_fields（后端口径："薪资"/"教员要求"）与显式字段空值为准。
 *
 * 三级分诊（纯展示层分类，集中在适配器，页面不做判断）：
 * - ready   正常：可直接确认创建
 * - review  待确认：needs_manual_review（后端口径：missing_fields 非空或待定价）
 * - blocked 无法创建：必填缺失（科目/地点）或课酬过低——创建必被后端拒收
 */
import type { OrderDraftItem } from "@/stores/order";
import { calcInfoFee } from "@/utils/fee";

export type ParsedFieldStatus = "normal" | "warning" | "missing";
export type DraftTriage = "ready" | "review" | "blocked";

export interface ParsedOrderField {
  key: string;
  label: string;
  value: string;
  status: ParsedFieldStatus;
  /** ⚠ 提示文案（来自后端 missing_fields 口径或显式字段状态，不编造） */
  reason?: string;
}

export interface ParsedDraftView {
  index: number;
  rawId: string;
  /** 后端定性置信度原值："high" | "medium" | "ai" */
  confidence: string;
  confidenceLabel: string;
  triage: DraftTriage;
  triageLabel: string;
  /** 无法创建的原因（blocked 时必有） */
  blockedReason?: string;
  fields: ParsedOrderField[];
}

export type DraftTriageCounts = { ready: number; review: number; blocked: number };

export const CONFIDENCE_LABELS: Record<string, string> = {
  high: "高置信",
  medium: "中置信",
  ai: "AI 补全",
};

const TRIAGE_LABELS: Record<DraftTriage, string> = {
  ready: "可直接确认",
  review: "待确认",
  blocked: "无法创建",
};

/** 单条草稿是否可创建（与后端 OrderImportItem 校验对齐的展示层映射） */
export function isDraftImportable(view: ParsedDraftView): boolean {
  return view.triage !== "blocked";
}

export function buildDraftViews(items: OrderDraftItem[]): ParsedDraftView[] {
  return items.map((item, index) => buildDraftView(item, index));
}

function buildDraftView(item: OrderDraftItem, index: number): ParsedDraftView {
  const gradeSubject = String(item.grade_subject || "").trim();
  const address = String(item.fuzzy_address || "").trim();
  const basePrice = Number(item.base_price) || 0;
  const fee = basePrice > 0 ? calcInfoFee(basePrice, item.weekly_frequency, !!item.is_summer_vacation) : null;
  const missing = item.missing_fields || [];

  const fields: ParsedOrderField[] = [
    field(
      "grade_subject",
      "年级科目",
      gradeSubject || "未识别",
      gradeSubject ? "normal" : "missing",
      gradeSubject ? undefined : "未识别",
    ),
    field(
      "price",
      "课酬",
      basePrice > 0 ? `¥${basePrice}/次` : String(item.price_total || "").trim() || "未识别",
      basePrice > 0 ? (fee ? "normal" : "warning") : "warning",
      basePrice > 0
        ? fee
          ? undefined
          : "信息费低于最低定金，需调整课酬或改为待定价"
        : "待定价：填写课酬或保持待教员报价",
    ),
    field(
      "frequency",
      "上课频次",
      item.weekly_frequency > 0
        ? `每周 ${item.weekly_frequency} 次${item.lesson_count ? ` · 共 ${item.lesson_count} 次` : ""}`
        : "未识别",
      item.weekly_frequency > 0 ? "normal" : "warning",
      item.weekly_frequency > 0 ? undefined : "原文未写明频次，请人工确认",
    ),
    field("address", "上课地点", address || "未识别", address ? "normal" : "missing", address ? undefined : "未识别，导入后可在订单管理校准"),
    field(
      "requirements",
      "教员要求",
      String(item.requirements || "").trim() || "未识别",
      String(item.requirements || "").trim() ? "normal" : "missing",
      String(item.requirements || "").trim() ? undefined : missing.includes("教员要求") ? "后端标记缺失" : "原文未写明",
    ),
  ];

  // 分诊：blocked = 创建必被后端拒收；review = 后端 needs_manual_review 口径
  let triage: DraftTriage = "ready";
  let blockedReason: string | undefined;
  if (!gradeSubject || !address) {
    triage = "blocked";
    blockedReason = !gradeSubject ? "年级科目缺失" : "上课地点缺失";
  } else if (basePrice > 0 && !fee) {
    triage = "blocked";
    blockedReason = "课酬过低：信息费不足最低定金";
  } else if (item.needs_manual_review || basePrice <= 0) {
    triage = "review";
  }

  return {
    index,
    rawId: item.raw_id,
    confidence: item.parser_confidence || "medium",
    confidenceLabel: CONFIDENCE_LABELS[item.parser_confidence] || CONFIDENCE_LABELS.medium,
    triage,
    triageLabel: TRIAGE_LABELS[triage],
    blockedReason,
    fields,
  };
}

function field(
  key: string,
  label: string,
  value: string,
  status: ParsedFieldStatus,
  reason?: string,
): ParsedOrderField {
  return { key, label, value, status, reason };
}

export function countTriage(views: ParsedDraftView[]): DraftTriageCounts {
  const counts: DraftTriageCounts = { ready: 0, review: 0, blocked: 0 };
  for (const view of views) {
    counts[view.triage] += 1;
  }
  return counts;
}
