import { difficulties, type InterviewRequest, type InterviewResponse } from "@/types/interview";
export function validRequest(value: unknown): value is InterviewRequest {
  if (!value || typeof value !== "object") return false;
  const v = value as Partial<InterviewRequest>;
  return typeof v.job_role === "string" && v.job_role.trim().length >= 2 && v.job_role.trim().length <= 100 && difficulties.includes(v.difficulty!);
}
export function validResponse(value: unknown): value is InterviewResponse {
  return validRequest(value) && typeof (value as InterviewResponse).question === "string" && !!(value as InterviewResponse).question.trim();
}
export async function startInterview(input: InterviewRequest): Promise<InterviewResponse> {
  const response = await fetch("/api/interview/start", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input), signal: AbortSignal.timeout(80000) });
  const data: unknown = await response.json();
  if (!response.ok) throw new Error(typeof (data as {error?: unknown}).error === "string" ? (data as {error: string}).error : "Unable to start the interview. Please try again.");
  if (!validResponse(data)) throw new Error("The server returned an invalid question. Please try again.");
  return data;
}
