import client from "./client";
import type { OkResponse } from "./types";

export interface TeacherResume {
  id: number;
  teacher_id: number;
  title: string;
  teaching_subjects: string;
  teaching_grades: string;
  experience: string;
  strengths?: string | null;
  availability?: string | null;
  expected_rate?: string | null;
  is_default: boolean;
  created_at: string;
  updated_at?: string | null;
}

export interface TeacherResumePayload {
  title: string;
  teaching_subjects: string;
  teaching_grades: string;
  experience: string;
  strengths: string;
  availability: string;
  expected_rate: string;
  is_default: boolean;
}

export const resumesApi = {
  list: () => client.get<TeacherResume[]>("/teacher/resumes/").then((r) => r.data),

  create: (payload: TeacherResumePayload) =>
    client.post<TeacherResume>("/teacher/resumes/", payload).then((r) => r.data),

  update: (id: number, payload: Partial<TeacherResumePayload>) =>
    client.patch<TeacherResume>(`/teacher/resumes/${id}`, payload).then((r) => r.data),

  setDefault: (id: number) =>
    client.post<TeacherResume>(`/teacher/resumes/${id}/default`).then((r) => r.data),

  remove: (id: number) =>
    client.delete<OkResponse>(`/teacher/resumes/${id}`).then((r) => r.data),
};
