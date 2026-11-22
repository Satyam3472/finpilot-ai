import { readFile } from "node:fs/promises";
import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const rules: Record<string, RegExp> = {
  GET: /^(health(?:\/(live|ready))?|auth\/session|dashboard\/summary|transactions|imports|budgets|analytics\/(trends|comparison|anomalies)|insights\/savings|chat\/sessions(?:\/[a-fA-F0-9-]{36})?)$/,
  POST: /^(auth\/(login|logout)|statements\/upload|chat\/sessions(?:\/[a-fA-F0-9-]{36}\/messages)?)$/,
  PUT: /^budgets\/[0-9]{4}-[0-9]{2}\/[a-zA-Z_]{1,30}$/,
  DELETE: /^budgets\/[0-9]{4}-[0-9]{2}\/[a-zA-Z_]{1,30}$/,
};

function error(status: number, message: string) {
  return Response.json({ error: { code: "proxy_error", message } }, {
    status, headers: { "Cache-Control": "no-store" },
  });
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const path = (await context.params).path.join("/");
  if (!rules[request.method]?.test(path)) return error(404, "API route not found.");

  try {
    const backend = new URL(process.env.FINPILOT_BACKEND_URL ?? "http://127.0.0.1:8000");
    if (backend.protocol !== "http:" || !["backend", "127.0.0.1", "localhost", "[::1]"].includes(backend.hostname)
      || backend.username || backend.password || backend.pathname !== "/" || backend.search || backend.hash) {
      return error(503, "FinPilot API is unavailable.");
    }
    const target = new URL(`/api/${path}`, backend);
    target.search = request.nextUrl.search;
    const headers = new Headers();
    for (const name of ["content-type", "cookie", "origin", "x-csrf-token"]) {
      const value = request.headers.get(name);
      if (value) headers.set(name, value);
    }
    const secretPath = process.env.FINPILOT_PROXY_SECRET_FILE;
    if (secretPath) headers.set("x-finpilot-proxy", (await readFile(secretPath, "utf8")).trim());

    const options: RequestInit & { duplex?: "half" } = {
      method: request.method, headers, signal: request.signal, cache: "no-store", redirect: "error",
    };
    if (request.body) {
      options.body = request.body;
      options.duplex = "half";
    }
    const upstream = await fetch(target, options);
    const responseHeaders = new Headers({ "Cache-Control": "no-store" });
    for (const name of ["content-type", "retry-after", "x-request-id", "x-accel-buffering"]) {
      const value = upstream.headers.get(name);
      if (value) responseHeaders.set(name, value);
    }
    for (const cookie of upstream.headers.getSetCookie()) responseHeaders.append("Set-Cookie", cookie);
    return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
  } catch {
    return error(503, "FinPilot API is unavailable. Try again shortly.");
  }
}

export { proxy as GET, proxy as POST, proxy as PUT, proxy as DELETE };
