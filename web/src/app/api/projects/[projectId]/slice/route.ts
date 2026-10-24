import { get } from "@vercel/blob";
import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";
import { getCadServiceConfig } from "@/lib/cad-service-config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const MAX_STL_BYTES = 20 * 1024 * 1024;
const MAX_GCODE_BYTES = 40 * 1024 * 1024;
const MAX_JSON_BYTES = 16 * 1024;
const SLICE_TIMEOUT_MS = 52_000;

type Context = { params: Promise<{ projectId: string }> };
type SliceSettings = {
  layer_height: number;
  wall_thickness: number;
  infill_density: number;
  support_enabled: boolean;
};

class RouteError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function readLimitedStream(stream: ReadableStream<Uint8Array> | null, limit: number): Promise<Buffer> {
  if (!stream) return Buffer.alloc(0);
  const reader = stream.getReader();
  const chunks: Buffer[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) {
        await reader.cancel();
        throw new RouteError("The slicer response exceeded the configured size limit.", 502);
      }
      chunks.push(Buffer.from(value));
    }
    return Buffer.concat(chunks, size);
  } finally {
    reader.releaseLock();
  }
}

async function assertSliceAccess(user: { id: string; role: string }): Promise<void> {
  if (user.role === "ADMIN") return;
  const subscription = await prisma.subscription.findUnique({ where: { userId: user.id } }).catch((error) => {
    console.error("Could not check slicing subscription.", error);
    throw new RouteError("Subscription service is unavailable.", 503);
  });
  if (!(subscription?.tier === "PRO" && subscription.status === "ACTIVE")) {
    throw new RouteError("An active Pro subscription is required to prepare STL files for printing.", 402);
  }
}

async function fetchBackendHealth(): Promise<Record<string, unknown>> {
  let endpoint: URL;
  try {
    endpoint = new URL("/health", getCadServiceConfig().baseUrl);
  } catch (error) {
    throw new RouteError(error instanceof Error ? error.message : "CAD service configuration is invalid.", 503);
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 5_000);
  try {
    const response = await fetch(endpoint, { method: "GET", cache: "no-store", signal: controller.signal });
    const text = await response.text();
    if (Buffer.byteLength(text, "utf8") > MAX_JSON_BYTES) {
      throw new RouteError("CAD backend health response is too large.", 502);
    }
    let health: unknown;
    try {
      health = JSON.parse(text);
    } catch {
      throw new RouteError("CAD backend returned invalid health JSON.", 502);
    }
    if (!response.ok || !health || typeof health !== "object" || Array.isArray(health)) {
      throw new RouteError("Could not read slicing capability from the CAD backend.", 503);
    }
    return health as Record<string, unknown>;
  } catch (error) {
    if (error instanceof RouteError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new RouteError("Timed out checking slicing capability.", 503);
    }
    throw new RouteError("Could not reach the CAD backend health endpoint.", 503);
  } finally {
    clearTimeout(timeout);
  }
}

async function readRequest(request: Request): Promise<Record<string, unknown>> {
  const raw = await request.text();
  if (Buffer.byteLength(raw, "utf8") > MAX_JSON_BYTES) {
    throw new RouteError("Slicing request is too large.", 413);
  }
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new RouteError("A valid JSON request body is required.", 400);
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new RouteError("A JSON object request body is required.", 400);
  }
  return value as Record<string, unknown>;
}

function normalizeSettings(value: unknown): SliceSettings {
  const record = value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
  const numeric = (key: string, fallback: number, minimum: number, maximum: number): number => {
    const candidate = record[key] === undefined ? fallback : record[key];
    if (typeof candidate !== "number" || !Number.isFinite(candidate) || candidate < minimum || candidate > maximum) {
      throw new RouteError("Invalid " + key + " slicing setting.", 400);
    }
    return candidate;
  };
  const supportEnabled = record.supportEnabled === undefined ? false : record.supportEnabled;
  if (typeof supportEnabled !== "boolean") throw new RouteError("supportEnabled must be a boolean.", 400);
  return {
    layer_height: numeric("layerHeight", 0.2, 0.05, 1),
    wall_thickness: numeric("wallThickness", 1.2, 0.4, 40),
    infill_density: numeric("infillDensity", 20, 0, 100),
    support_enabled: supportEnabled,
  };
}

export async function GET(_request: Request, { params }: Context) {
  let user;
  try {
    user = await getCurrentUser();
  } catch (error) {
    console.error("Slicing capability request could not resolve the current user.", error);
    return NextResponse.json({ error: "Authentication service is unavailable." }, { status: 503 });
  }
  if (!user) return NextResponse.json({ error: "Authentication required." }, { status: 401 });

  try {
    const { projectId } = await params;
    const project = await prisma.project.findFirst({
      where: { id: projectId, userId: user.id },
      select: { id: true },
    });
    if (!project) throw new RouteError("Project not found.", 404);
    await assertSliceAccess(user);
    const health = await fetchBackendHealth();
    const hasCapabilityContract = typeof health.slicingAvailable === "boolean";
    return NextResponse.json({
      available: health.slicingAvailable === true,
      engine: typeof health.slicingEngine === "string" ? health.slicingEngine : null,
      reason: typeof health.slicingStatusReason === "string"
        ? health.slicingStatusReason
        : hasCapabilityContract
          ? "The CAD backend has not reported a slicing reason."
          : "The connected CAD backend is an older build. Redeploy the feature-branch backend to report slicing readiness.",
    }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    if (error instanceof RouteError) {
      return NextResponse.json({ available: false, engine: null, reason: error.message }, { status: error.status });
    }
    console.error("Slicing capability check failed.", error);
    return NextResponse.json({ available: false, engine: null, reason: "Could not check slicing capability." }, { status: 500 });
  }
}

export async function POST(request: Request, { params }: Context) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  }
  let user;
  try {
    user = await getCurrentUser();
  } catch (error) {
    console.error("Slicing request could not resolve the current user.", error);
    return NextResponse.json({ error: "Authentication service is unavailable." }, { status: 503 });
  }
  if (!user) return NextResponse.json({ error: "Sign in before slicing an STL file." }, { status: 401 });

  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    const { projectId } = await params;
    await assertSliceAccess(user);
    const body = await readRequest(request);
    const versionId = body.versionId;
    if (typeof versionId !== "string" || !versionId.trim() || versionId.length > 128) {
      throw new RouteError("Select a valid STL export version.", 400);
    }
    const settings = normalizeSettings(body.settings);
    const project = await prisma.project.findFirst({
      where: { id: projectId, userId: user.id },
      select: { id: true },
    });
    if (!project) throw new RouteError("Project not found.", 404);
    const version = await prisma.projectVersion.findFirst({
      where: { id: versionId, projectId: project.id },
      select: { id: true, version: true, stlFilePath: true },
    });
    if (!version?.stlFilePath) throw new RouteError("The selected project version has no stored STL export.", 404);

    const blobToken = process.env.PRIVATE_BLOB_READ_WRITE_TOKEN?.trim();
    if (!blobToken) throw new RouteError("Private project storage is not configured.", 503);
    const stored = await get(version.stlFilePath, { access: "private", token: blobToken });
    if (!stored || stored.statusCode !== 200 || !stored.stream) {
      throw new RouteError("The selected STL could not be read from private storage.", 404);
    }
    const stlBytes = await readLimitedStream(stored.stream, MAX_STL_BYTES);
    if (!stlBytes.length) throw new RouteError("The stored STL export is empty.", 422);

    let config: ReturnType<typeof getCadServiceConfig>;
    try {
      config = getCadServiceConfig();
    } catch (error) {
      throw new RouteError(error instanceof Error ? error.message : "CAD service configuration is invalid.", 503);
    }
    const endpoint = new URL("/api/v1/slice", config.baseUrl);
    const controller = new AbortController();
    timeout = setTimeout(() => controller.abort(), SLICE_TIMEOUT_MS);
    const upstream = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(config.token ? { Authorization: "Bearer " + config.token } : {}),
      },
      body: JSON.stringify({ stlBase64: stlBytes.toString("base64"), settings }),
      cache: "no-store",
      signal: controller.signal,
    });

    if (!upstream.ok) {
      const errorBytes = await readLimitedStream(upstream.body, MAX_JSON_BYTES);
      let detail = "The CAD slicing service failed.";
      try {
        const payload = JSON.parse(errorBytes.toString("utf8")) as Record<string, unknown>;
        if (typeof payload.detail === "string") detail = payload.detail;
        else if (typeof payload.error === "string") detail = payload.error;
      } catch {
        if (errorBytes.length) detail = errorBytes.toString("utf8").slice(0, 500);
      }
      const status = [400, 413, 422, 503].includes(upstream.status) ? upstream.status : 502;
      throw new RouteError(detail.slice(0, 1000), status);
    }

    const contentType = (upstream.headers.get("content-type") || "").toLowerCase();
    if (!contentType.includes("gcode")) {
      throw new RouteError("The CAD backend did not return a validated G-code file.", 502);
    }
    const gcodeBytes = await readLimitedStream(upstream.body, MAX_GCODE_BYTES);
    if (!gcodeBytes.length) throw new RouteError("The CAD backend returned an empty G-code file.", 502);

    const headers = new Headers({
      "Content-Type": "text/x-gcode; charset=utf-8",
      "Content-Disposition": 'attachment; filename="project-v' + version.version + '.gcode"',
      "Cache-Control": "private, no-store",
      "X-Content-Type-Options": "nosniff",
    });
    for (const name of [
      "x-slice-engine",
      "x-slice-print-time-seconds",
      "x-slice-filament-grams",
      "x-slice-filament-meters",
      "x-slice-filament-grams-estimated",
      "x-slice-layers",
    ]) {
      const value = upstream.headers.get(name);
      if (value !== null && /^[A-Za-z0-9 ._-]{1,120}$/.test(value)) headers.set(name, value);
    }

    return new Response(gcodeBytes, { status: 200, headers });
  } catch (error) {
    if (error instanceof RouteError) return NextResponse.json({ error: error.message }, { status: error.status });
    if (error instanceof Error && error.name === "AbortError") {
      return NextResponse.json({ error: "Slicing timed out at the web request limit. Try a smaller STL or a faster backend." }, { status: 504 });
    }
    console.error("Project STL slicing failed.", error);
    return NextResponse.json({ error: "Could not slice this STL. Check CAD backend health and slicer logs." }, { status: 500 });
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}
