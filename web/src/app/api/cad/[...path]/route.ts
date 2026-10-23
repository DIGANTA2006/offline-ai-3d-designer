import { NextResponse } from "next/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type CadRoute = {
  method: "GET" | "POST";
  upstreamPath: string;
  requiresUser: boolean;
};

const routes: Record<string, CadRoute> = {
  health: { method: "GET", upstreamPath: "/health", requiresUser: false },
  "text-to-cad": { method: "POST", upstreamPath: "/api/v1/text-to-cad", requiresUser: true },
  "ocr/extract": { method: "POST", upstreamPath: "/api/v1/ocr/extract", requiresUser: true },
  generate: { method: "POST", upstreamPath: "/api/v1/generate", requiresUser: true },
};

const MAX_REQUEST_BYTES = 4 * 1024 * 1024 + 128 * 1024;
const MAX_RESPONSE_BYTES = 12 * 1024 * 1024;
const UPSTREAM_TIMEOUT_MS = 35_000;

function getCadServiceBaseUrl(): string | null {
  const configured = process.env.CAD_SERVICE_URL?.trim().replace(/\/+$/, "");
  if (!configured) return process.env.NODE_ENV === "production" ? null : "http://127.0.0.1:8000";

  try {
    const url = new URL(configured);
    const loopbackHost = ["localhost", "127.0.0.1", "::1"].includes(url.hostname);
    if (url.protocol !== "https:" && !(process.env.NODE_ENV !== "production" && url.protocol === "http:" && loopbackHost)) return null;
    return url.toString().replace(/\/+$/, "");
  } catch {
    return null;
  }
}

async function handleCadProxy(request: Request): Promise<Response> {
  const pathname = new URL(request.url).pathname;
  const routeName = pathname.replace(/^\/api\/cad\/?/, "");
  const route = routes[routeName];
  if (!route) return NextResponse.json({ error: "Unknown CAD endpoint." }, { status: 404 });
  if (request.method !== route.method) {
    return NextResponse.json({ error: `Use ${route.method} for this endpoint.` }, {
      status: 405,
      headers: { Allow: route.method },
    });
  }

  // CAD generation is routed through /api/projects so billing, quota checks, and
  // private output persistence cannot be bypassed. OCR only extracts reviewable text.
  if (routeName !== "health" && routeName !== "ocr/extract") {
    return NextResponse.json(
      { error: "Direct CAD endpoints are disabled. Use POST /api/projects to create a saved, quota-managed CAD project." },
      { status: 410 },
    );
  }

  let userId: string | undefined;
  if (route.requiresUser) {
    if (!isSameOriginRequest(request)) {
      return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
    }
    try {
      const { getCurrentUser } = await import("@/lib/auth/server");
      const user = await getCurrentUser();
      if (!user) return NextResponse.json({ error: "Sign in to use CAD generation." }, { status: 401 });
      userId = user.id;
    } catch (error) {
      console.error("CAD proxy could not verify the application session.", error);
      return NextResponse.json({ error: "Authentication or database service is unavailable." }, { status: 503 });
    }
  }

  const baseUrl = getCadServiceBaseUrl();
  if (!baseUrl) {
    return NextResponse.json({ error: "CAD service is not configured." }, { status: 503 });
  }
  const token = process.env.CAD_SERVICE_TOKEN?.trim();
  if (process.env.NODE_ENV === "production" && !token) {
    return NextResponse.json({ error: "CAD_SERVICE_TOKEN is not configured on the web service." }, { status: 503 });
  }

  let body: string | undefined;
  if (request.method === "POST") {
    const contentLength = Number(request.headers.get("content-length") ?? 0);
    if (contentLength > MAX_REQUEST_BYTES) {
      return NextResponse.json({ error: "CAD request exceeds the 4.125 MiB OCR proxy limit." }, { status: 413 });
    }
    let payload: unknown;
    try {
      payload = await request.json();
    } catch {
      return NextResponse.json({ error: "A valid JSON request body is required." }, { status: 400 });
    }
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return NextResponse.json({ error: "A JSON object request body is required." }, { status: 400 });
    }
    const normalizedPayload: Record<string, unknown> = { ...(payload as Record<string, unknown>) };
    if (userId) normalizedPayload.userId = userId;
    body = JSON.stringify(normalizedPayload);
    if (Buffer.byteLength(body, "utf8") > MAX_REQUEST_BYTES) {
      return NextResponse.json({ error: "CAD request exceeds the 64 KB limit." }, { status: 413 });
    }
  }

  try {
    const upstreamUrl = new URL(route.upstreamPath, `${baseUrl}/`);
    const abortController = new AbortController();
    const timeout = setTimeout(() => abortController.abort(), UPSTREAM_TIMEOUT_MS);
    let upstream: Response;
    try {
      upstream = await fetch(upstreamUrl, {
        method: request.method,
        headers: {
          ...(body ? { "Content-Type": "application/json" } : {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        ...(body ? { body } : {}),
        cache: "no-store",
        signal: abortController.signal,
      });
    } finally {
      clearTimeout(timeout);
    }
    const responseLength = Number(upstream.headers.get("content-length") ?? 0);
    if (responseLength > MAX_RESPONSE_BYTES) {
      return NextResponse.json({ error: "CAD service response is too large." }, { status: 502 });
    }
    const responseBody = await upstream.arrayBuffer();
    if (responseBody.byteLength > MAX_RESPONSE_BYTES) {
      return NextResponse.json({ error: "CAD service response is too large." }, { status: 502 });
    }
    return new Response(responseBody, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        "Cache-Control": "no-store",
      },
    });
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "AbortError";
    console.error(`CAD upstream request failed for ${routeName}.`, error);
    return NextResponse.json(
      { error: timedOut ? "CAD service request timed out." : "CAD service is unavailable." },
      { status: timedOut ? 504 : 502 },
    );
  }
}

export const GET = handleCadProxy;
export const POST = handleCadProxy;
