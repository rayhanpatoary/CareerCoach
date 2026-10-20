import { NextResponse } from "next/server";
import { validRequest, validResponse } from "@/lib/interview";
import { proxyInterview } from "@/lib/interview-proxy";
export const maxDuration = 90;
export async function POST(request: Request) {
  const copy = request.clone();
  let input: unknown;
  try { input = await request.json(); } catch { return NextResponse.json({error: "Send a valid JSON request."}, {status: 400}); }
  if (input && typeof input === "object" && "persistent" in input && input.persistent === true) return proxyInterview(copy, "start");
  if (!validRequest(input)) return NextResponse.json({error: "Enter a role between 2 and 100 characters and select a valid difficulty."}, {status: 400});
  try {
    const base = process.env.BACKEND_API_URL;
    if (!base) return NextResponse.json({error: "The backend URL is not configured."}, {status: 503});
    const response = await fetch(`${base.replace(/\/$/, "")}/api/interview/start`, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...input, job_role: input.job_role.trim()}), signal: AbortSignal.timeout(70000), cache: "no-store"});
    if (!response.ok) return NextResponse.json({error: response.status === 422 ? "The backend could not accept these interview settings." : "The AI service could not generate a question. Please try again."}, {status: response.status === 422 ? 422 : 502});
    const data: unknown = await response.json();
    if (!validResponse(data)) return NextResponse.json({error: "The backend returned an invalid question. Please try again."}, {status: 502});
    return NextResponse.json(data);
  } catch (error) {
    const timeout = error instanceof Error && ["TimeoutError", "AbortError"].includes(error.name);
    return NextResponse.json({error: timeout ? "Question generation took too long. Please try again." : "Cannot reach FastAPI. Make sure the backend is running and try again."}, {status: timeout ? 504 : 503});
  }
}
