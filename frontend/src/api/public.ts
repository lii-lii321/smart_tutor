import client from "./client";

/** 教员公开成绩单（无需登录；脱敏口径见后端 routers/v1/teacher_public.py） */
export interface ScorecardReview {
  rating: number;
  comment: string | null;
  grade_subject: string | null;
  created_at: string | null;
}

export interface Scorecard {
  teacher_id: number;
  display_name: string;
  school: string;
  major: string | null;
  grade: string | null;
  tags: string[];
  completed_count: number;
  violation_count: number;
  avg_rating: number | null;
  review_count: number;
  reviews: ScorecardReview[];
}

export const publicApi = {
  scorecard: (teacherId: number) =>
    client.get<Scorecard>(`/public/teacher/${teacherId}/scorecard`).then((r) => r.data),
};
