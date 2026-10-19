export const difficulties = ["beginner", "intermediate", "advanced"] as const;
export type Difficulty = (typeof difficulties)[number];
export interface InterviewRequest { job_role: string; difficulty: Difficulty }
export interface InterviewResponse extends InterviewRequest { question: string }
