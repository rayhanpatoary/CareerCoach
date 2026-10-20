import { randomBytes } from "node:crypto";
import { cookies } from "next/headers";
import { NextResponse } from "next/server";
import { cookieName, sameOrigin } from "@/lib/interview-proxy";

export async function POST(request: Request) {
  if (!sameOrigin(request)) return NextResponse.json({error: "Invalid request origin."}, {status: 403});
  const response = NextResponse.json({ready: true}, {headers: {"Cache-Control": "no-store"}});
  if (!(await cookies()).get(cookieName)) response.cookies.set(cookieName, randomBytes(32).toString("base64url"), {
    httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "strict", path: "/", maxAge: 7 * 86400,
  });
  return response;
}
