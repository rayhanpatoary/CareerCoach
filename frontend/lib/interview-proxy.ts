import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export const cookieName = process.env.NODE_ENV === "production" ? "__Host-career-session" : "career-session";
export function sameOrigin(request: Request) {
  const origin = request.headers.get("origin");
  if (!origin) return false;
  try {
    const parsed = new URL(origin);
    // Next.js can reconstruct request.url using its internal localhost hostname.
    // The incoming Host is the authority that the browser actually addressed;
    // browsers cannot forge it while sending a cross-origin request.
    return parsed.origin === origin && parsed.host === request.headers.get("host") &&
      parsed.protocol === new URL(request.url).protocol &&
      (!request.headers.get("sec-fetch-site") || ["same-origin", "none"].includes(request.headers.get("sec-fetch-site")!));
  } catch { return false; }
}
export async function proxyInterview(request: Request, path: string) {
  if (request.method !== "GET" && !sameOrigin(request)) return NextResponse.json({error: "Use this site's interview workspace."}, {status: 403});
  const credential = (await cookies()).get(cookieName)?.value;
  if (!credential || !/^[A-Za-z0-9_-]{43,128}$/.test(credential)) return NextResponse.json({error: "Your private session is missing. Start a new interview in this browser."}, {status: 401});
  const base = process.env.BACKEND_API_URL;
  if (!base) return NextResponse.json({error: "The backend URL is not configured."}, {status: 503});
  let body: string | undefined;
  if (request.method === "POST") {
    if (!request.headers.get("content-type")?.includes("application/json")) return NextResponse.json({error: "Send JSON."}, {status: 415});
    body = await request.text();
    if (new TextEncoder().encode(body).length > 40000) return NextResponse.json({error: "The request is too large."}, {status: 413});
    try { JSON.parse(body); } catch { return NextResponse.json({error: "Send valid JSON."}, {status: 400}); }
  }
  try {
    const upstream = await fetch(`${base.replace(/\/$/, "")}/api/interview/${path}`, {
      method: request.method, headers: {"Content-Type": "application/json", Authorization: `Bearer ${credential}`},
      body, cache: "no-store", signal: AbortSignal.timeout(70000), redirect: "error"});
    if (upstream.status === 204) return new NextResponse(null, {status: 204, headers: {"Cache-Control": "no-store"}});
    const data: unknown = await upstream.json();
    if (!upstream.ok) {
      const detail = data && typeof data === "object" && "detail" in data ? data.detail : null;
      const message = typeof detail === "string" && detail.length < 500 ? detail : "The request could not be accepted. Check your settings and retry.";
      return NextResponse.json({error: message}, {status: upstream.status, headers: {"Cache-Control": "no-store", ...(upstream.headers.has("retry-after") ? {"Retry-After": upstream.headers.get("retry-after")!} : {})}});
    }
    return NextResponse.json(data, {headers: {"Cache-Control": "no-store"}});
  } catch {
    return NextResponse.json({error: "The service could not respond in time. Your progress is safe. Retry the same action."}, {status: 503});
  }
}
