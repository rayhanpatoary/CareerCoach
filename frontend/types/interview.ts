export const difficulties = ["beginner", "intermediate", "advanced"] as const;
export type Difficulty = (typeof difficulties)[number];
export interface InterviewRequest { job_role: string; difficulty: Difficulty }
export interface InterviewResponse extends InterviewRequest { question: string }
export type InterviewType = "technical" | "behavioral" | "mixed";
export interface Configuration extends InterviewRequest {
  interview_type: InterviewType;
  question_count: 3 | 5 | 8;
  job_description: string;
}
export interface Turn {
  id: string; position: number; question: string; answer: string | null;
  asked_at: string; answered_at: string | null;
}
export const categoryLabels = {
  accuracy: "Role-specific accuracy", clarity: "Communication & clarity",
  reasoning: "Problem-solving & reasoning", completeness: "Completeness & relevance",
  depth: "Practical examples & depth",
} as const;
export type CategoryKey = keyof typeof categoryLabels;
export interface Evaluation {
  overall_score: number | null; evidence_coverage: number; partial: boolean; answered_count: number;
  summary: string; strengths: string[]; improvements: string[]; knowledge_gaps: string[];
  recommendations: string[]; practice_plan: string[];
  categories: Record<CategoryKey, {score: number | null; evidence: string}>;
  rubric: Record<CategoryKey, number>;
  reviews: {question_id: string; effective: string; missing: string; improvement: string; example_answer: string}[];
}
export interface InterviewState extends Configuration {
  id: string; status: "generating_question" | "in_progress" | "completed" | "evaluating" | "finished";
  question: string | null; turns: Turn[]; answered_count: number;
  started_at: string; completed_at: string | null; expires_at: string; feedback: Evaluation | null; busy: boolean;
}
export interface PendingAction { path: string; body: Record<string, unknown> }
