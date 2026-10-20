import { NextResponse } from "next/server";
import { proxyInterview } from "@/lib/interview-proxy";
export const maxDuration = 90;
async function handle(request: Request, context: {params: Promise<{segments: string[]}>}) {
  const {segments} = await context.params;
  if (!/^[0-9a-f-]{36}$/i.test(segments[0] ?? "") || segments.length > 2 ||
      (segments.length === 2 && !["answer", "finish", "feedback"].includes(segments[1])))
    return NextResponse.json({error: "Unknown interview route."}, {status: 404});
  return proxyInterview(request, segments.join("/"));
}
export const GET = handle;
export const POST = handle;
export const DELETE = handle;
