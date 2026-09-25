/**
 * 推荐解释适配器（Batch 02）：
 * 后端 services/recommendation.py 已下发 score_breakdown 六维分数与 reasons，
 * 这里只做 API → UI 模型的字段映射，不计算、不猜测、不生成假理由。
 *
 * 架构红线：前端不计算推荐分数。分数与理由全部来自接口真实数据；
 * 数据缺失时 explanation 为 null（页面显示"暂时无法生成匹配解释"，不放假默认值）。
 */
import type { RecommendationScoreBreakdown, TeacherOrderRecommendationItem } from "@/api/types";

export interface RecommendationFactor {
  key: string;
  label: string;
  score: number;
}

export interface RecommendationExplanation {
  totalScore: number;
  factors: RecommendationFactor[];
  /** 后端 reasons 原文（已截取前若干条），直接展示不二次加工 */
  reasons: string[];
}

/** score_breakdown 字段 → 中文标签（顺序即展示顺序） */
const FACTOR_LABELS: ReadonlyArray<[keyof RecommendationScoreBreakdown, string]> = [
  ["subject", "专业"],
  ["grade", "年级"],
  ["distance", "距离"],
  ["school", "院校"],
  ["price", "课酬"],
  ["history", "历史表现"],
];

export function buildRecommendationExplanation(
  item: Pick<TeacherOrderRecommendationItem, "total_score" | "score_breakdown" | "reasons"> | null | undefined,
): RecommendationExplanation | null {
  if (!item || item.score_breakdown == null) {
    return null;
  }
  const breakdown = item.score_breakdown;
  const factors = FACTOR_LABELS.filter(([key]) => typeof breakdown[key] === "number").map(
    ([key, label]) => ({ key, label, score: breakdown[key] })
  );
  if (factors.length === 0) {
    return null;
  }
  return {
    totalScore: item.total_score,
    factors,
    reasons: (item.reasons || []).slice(0, 3),
  };
}
