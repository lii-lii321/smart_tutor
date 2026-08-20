import client from "./client";

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
  list: () => client.get("/teacher/resumes/").then((r) => r.data as TeacherResume[]),

  create: (payload: TeacherResumePayload) =>
    client.post("/teacher/resumes/", payload).then((r) => r.data as TeacherResume),

  update: (id: number, payload: Partial<TeacherResumePayload>) =>
    client.patch(`/teacher/resumes/${id}`, payload).then((r) => r.data as TeacherResume),

  setDefault: (id: number) =>
    client.post(`/teacher/resumes/${id}/default`).then((r) => r.data as TeacherResume),

  remove: (id: number) =>
    client.delete(`/teacher/resumes/${id}`).then((r) => r.data),
};
