import { categoryLabels, type Evaluation, type InterviewState } from "@/types/interview";

export function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}
const strings = (value: unknown) => Array.isArray(value) && value.every(v => typeof v === "string");
const score = (value: unknown) => value === null || (Number.isInteger(value) && Number(value) >= 0 && Number(value) <= 100);
export function validEvaluation(value: unknown): value is Evaluation {
  if (!record(value) || !score(value.overall_score) || typeof value.summary !== "string" ||
      typeof value.partial !== "boolean" || !Number.isInteger(value.answered_count) ||
      !Number.isInteger(value.evidence_coverage) || !record(value.categories) || !record(value.rubric)) return false;
  if (!["strengths", "improvements", "knowledge_gaps", "recommendations", "practice_plan"].every(k => strings(value[k]))) return false;
  const categories = value.categories, rubric = value.rubric;
  return Object.keys(categoryLabels).every(k => record(categories[k]) && score(categories[k].score) &&
    typeof categories[k].evidence === "string" && typeof rubric[k] === "number") &&
    Array.isArray(value.reviews) && value.reviews.every(v => record(v) &&
      ["question_id", "effective", "missing", "improvement", "example_answer"].every(k => typeof v[k] === "string"));
}
export function validState(value: unknown): value is InterviewState {
  if (!record(value)) return false;
  return typeof value.id === "string" && typeof value.job_role === "string" &&
    ["beginner", "intermediate", "advanced"].includes(String(value.difficulty)) &&
    ["technical", "behavioral", "mixed"].includes(String(value.interview_type)) &&
    [3, 5, 8].includes(Number(value.question_count)) && typeof value.job_description === "string" &&
    ["generating_question", "in_progress", "completed", "evaluating", "finished"].includes(String(value.status)) &&
    (value.question === null || typeof value.question === "string") && typeof value.busy === "boolean" &&
    Number.isInteger(value.answered_count) && typeof value.started_at === "string" && typeof value.expires_at === "string" &&
    (value.completed_at === null || typeof value.completed_at === "string") &&
    (value.feedback === null || validEvaluation(value.feedback)) && Array.isArray(value.turns) &&
    value.turns.every(t => record(t) && typeof t.id === "string" && Number.isInteger(t.position) &&
      typeof t.question === "string" && (t.answer === null || typeof t.answer === "string") && typeof t.asked_at === "string");
}
export async function sessionRequest(path: string, body?: Record<string, unknown>, method?: string): Promise<InterviewState> {
  const response = await fetch(`/api/interview/${path}`, {method: method ?? (body ? "POST" : "GET"),
    headers: body ? {"Content-Type": "application/json"} : undefined,
    body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(80000), cache: "no-store"});
  const data: unknown = await response.json();
  if (!response.ok) throw new Error(record(data) && typeof data.error === "string" ? data.error : "The request failed. Please retry.");
  if (!validState(data)) throw new Error("The server returned an invalid interview. Reload or retry this action.");
  return data;
}
export async function ensureSession() {
  const response = await fetch("/api/interview/session", {method: "POST", headers: {"Content-Type": "application/json"}});
  if (!response.ok) throw new Error("Could not establish a private interview session. Please retry.");
}
export function saved(key: string): string | null {
  try { return sessionStorage.getItem(`interview:${key}`); } catch { return null; }
}
export function save(key: string, value: string | null) {
  try {
    if (value === null) sessionStorage.removeItem(`interview:${key}`);
    else sessionStorage.setItem(`interview:${key}`, value);
  } catch { /* Browsers with storage disabled still support the current interview. */ }
}
