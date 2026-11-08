import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";
import { getCadServiceConfig } from "@/lib/cad-service-config";
import { checkPaidFeatureAccess } from "@/lib/billing/paid-access";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

type Context = { params: Promise<{ projectId: string }> };
type Operation = "check" | "fix" | "checkBlueprint";

const MAX_REQUEST_BYTES = 8 * 1024;
const MAX_RESPONSE_BYTES = 1024 * 1024;
const BACKEND_TIMEOUT_MS = 30_000;

class RouteError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function readJson(request: Request): Promise<Record<string, unknown>> {
  const contentLength = Number(request.headers.get("content-length") ?? 0);
  if (contentLength > MAX_REQUEST_BYTES) {
    throw new RouteError("Printability request is too large.", 413);
  }

  const raw = await request.text();
  if (Buffer.byteLength(raw, "utf8") > MAX_REQUEST_BYTES) {
    throw new RouteError("Printability request is too large.", 413);
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

async function readLimitedText(response: Response): Promise<string> {
  const declared = Number(response.headers.get("content-length") ?? 0);
  if (declared > MAX_RESPONSE_BYTES) {
    throw new RouteError("The CAD printability response exceeded the size limit.", 502);
  }
  if (!response.body) return "";

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let size = 0;
  let text = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_RESPONSE_BYTES) {
        await reader.cancel();
        throw new RouteError("The CAD printability response exceeded the size limit.", 502);
      }
      text += decoder.decode(value, { stream: true });
    }
    text += decoder.decode();
    return text;
  } finally {
    reader.releaseLock();
  }
}

type SavedGeometry =
  | { kind: "partSpec"; value: Record<string, unknown>; name: string; notices: string[] }
  | { kind: "blueprint"; value: Record<string, unknown>; name: string; notices: string[] };

function getSavedGeometry(value: unknown, ownerUserId: string): SavedGeometry {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new RouteError("This project version has no saved CAD specification.", 422);
  }

  const record = value as Record<string, unknown>;
  const candidate = record.partSpec && typeof record.partSpec === "object" && !Array.isArray(record.partSpec)
    ? record.partSpec as Record<string, unknown>
    : record;

  // Legacy text-to-CAD projects use the canonical PartSpec contract.
  if (
    typeof candidate.name === "string" &&
    Array.isArray(candidate.features) &&
    candidate.features.length > 0
  ) {
    return { kind: "partSpec", value: candidate, name: candidate.name, notices: [] };
  }

  // Drawing-to-CAD projects intentionally persist a distinct Blueprint. Do not
  // relabel it as a PartSpec; send it to the blueprint-native geometry checker.
  const blueprintValue = record.reviewedBlueprint && typeof record.reviewedBlueprint === "object" && !Array.isArray(record.reviewedBlueprint)
    ? record.reviewedBlueprint as Record<string, unknown>
    : candidate;
  const allowedBodies = ["rotational_flange", "prismatic_box", "sheet_enclosure", "revolved_profile"];
  const sketch = blueprintValue.base_sketch;
  if (
    typeof blueprintValue.part_name === "string" &&
    typeof blueprintValue.primary_body_type === "string" &&
    allowedBodies.includes(blueprintValue.primary_body_type) &&
    !!sketch && typeof sketch === "object" && !Array.isArray(sketch) &&
    Array.isArray(blueprintValue.features)
  ) {
    const unsupported = blueprintValue.unsupported_geometry;
    if (Array.isArray(unsupported) && unsupported.length > 0) {
      throw new RouteError(
        "This drawing contains unsupported geometry. It cannot be treated as a printable model.",
        422,
      );
    }
    const notices: string[] = [];
    const sketchRecord = sketch as Record<string, unknown>;
    const rawConfirmations = record.confirmedProvisionalDefaults;
    const confirmations = Array.isArray(rawConfirmations)
      ? rawConfirmations.filter((item): item is Record<string, unknown> =>
          !!item && typeof item === "object" && !Array.isArray(item))
      : [];

    const hasMatchingConfirmation = (field: string, value: number) =>
      confirmations.some((item) =>
        item.field === field &&
        item.value === value &&
        item.unit === "mm" &&
        item.source === "provisional_default" &&
        item.confirmedBy === ownerUserId &&
        typeof item.confirmedAt === "string" &&
        Number.isFinite(Date.parse(item.confirmedAt)),
      );

    const provisionalFields = [
      { flag: "thickness_is_default", valueKey: "thickness", field: "base_sketch.thickness", label: "Height/depth" },
      { flag: "wall_thickness_is_default", valueKey: "wall_thickness", field: "base_sketch.wall_thickness", label: "Enclosure wall thickness" },
    ];

    for (const item of provisionalFields) {
      if (sketchRecord[item.flag] !== true) continue;
      const value = sketchRecord[item.valueKey];
      if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
        notices.push(item.label + " is flagged as a provisional default, but its saved value is missing or invalid. Resolve it before manufacturing.");
        continue;
      }
      if (hasMatchingConfirmation(item.field, value)) {
        notices.push(item.label + " " + value + " mm remains a provisional default, not a drawing-derived measurement; this saved version records an explicit confirmation of that exact value.");
      } else {
        notices.push(item.label + " " + value + " mm is flagged as a provisional default, but this saved version has no matching user-confirmation record. A passing printability check does not approve this value; review it before manufacturing.");
      }
    }

    if (blueprintValue.needs_review === true) {
      notices.push("This drawing blueprint is flagged as needing review. Passing printability checks do not constitute approval of its dimensions or interpretation.");
    }

    return { kind: "blueprint", value: blueprintValue, name: blueprintValue.part_name, notices };
  }

  throw new RouteError(
    "This project version does not contain a supported saved CAD specification or resolved drawing blueprint.",
    422,
  );
}

async function loadOwnedVersion(
  projectId: string,
  userId: string,
  versionId?: string,
): Promise<{ id: string; version: number; geometry: SavedGeometry }> {
  const project = await prisma.project.findFirst({
    where: { id: projectId, userId },
    select: { id: true },
  });
  if (!project) throw new RouteError("Project not found.", 404);

  const version = versionId
    ? await prisma.projectVersion.findFirst({
        where: { id: versionId, projectId: project.id },
        select: { id: true, version: true, spec: true, stepFilePath: true, stlFilePath: true },
      })
    : await prisma.projectVersion.findFirst({
        where: { projectId: project.id },
        orderBy: [{ version: "desc" }, { createdAt: "desc" }],
        select: { id: true, version: true, spec: true, stepFilePath: true, stlFilePath: true },
      });

  if (!version) throw new RouteError("Project version not found.", 404);
  if (!version.stepFilePath && !version.stlFilePath) {
    throw new RouteError("The selected project version has no generated CAD export.", 422);
  }

  return {
    id: version.id,
    version: version.version,
    geometry: getSavedGeometry(version.spec, userId),
  };
}

async function requireSignedInUser() {
  try {
    const user = await getCurrentUser();
    if (!user) throw new RouteError("Sign in before running printability checks.", 401);
    return user;
  } catch (error) {
    if (error instanceof RouteError) throw error;
    console.error("Printability route could not resolve the current user.", error);
    throw new RouteError("Authentication service is unavailable.", 503);
  }
}

async function requirePaidAccess(user: { id: string; role: string }) {
  const paid = await checkPaidFeatureAccess(
    user,
    "An active Pro subscription is required to run printability checks and preview fixes.",
  );
  if (!paid.allowed) throw new RouteError(paid.message, paid.status);
}

async function callCadService(operation: Operation, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  let config: ReturnType<typeof getCadServiceConfig>;
  try {
    config = getCadServiceConfig();
  } catch (error) {
    throw new RouteError(error instanceof Error ? error.message : "CAD service configuration is invalid.", 503);
  }
  if (process.env.NODE_ENV === "production" && !config.token) {
    throw new RouteError("CAD service token is not configured on the web deployment.", 503);
  }

  const path = operation === "check"
    ? "/api/v1/printability/check"
    : operation === "checkBlueprint"
      ? "/api/v1/printability/check-blueprint"
      : "/api/v1/printability/fix";
  const endpoint = new URL(path, config.baseUrl);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), BACKEND_TIMEOUT_MS);

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(config.token ? { Authorization: "Bearer " + config.token } : {}),
      },
      body: JSON.stringify(payload),
      cache: "no-store",
      signal: controller.signal,
    });

    const responseText = await readLimitedText(response);
    let body: unknown;
    try {
      body = JSON.parse(responseText);
    } catch {
      throw new RouteError("The CAD backend returned an invalid printability response.", 502);
    }
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      throw new RouteError("The CAD backend returned an invalid printability response.", 502);
    }

    const result = body as Record<string, unknown>;
    if (!response.ok) {
      const detail = typeof result.detail === "string"
        ? result.detail
        : typeof result.error === "string"
          ? result.error
          : "The CAD printability service rejected the request.";
      if (response.status === 404) {
        throw new RouteError(
          "The connected CAD backend does not yet expose printability endpoints. Deploy the matching CAD backend update before retrying.",
          503,
        );
      }
      const safeStatus = [400, 413, 422, 503].includes(response.status) ? response.status : 502;
      throw new RouteError(detail.slice(0, 700), safeStatus);
    }
    if (result.success !== true) {
      throw new RouteError(
        typeof result.error === "string" ? result.error.slice(0, 700) : "The CAD backend could not complete the printability request.",
        422,
      );
    }
    return result;
  } catch (error) {
    if (error instanceof RouteError) throw error;
    if (error instanceof Error && error.name === "AbortError") {
      throw new RouteError("The printability check timed out. Try a simpler part or retry shortly.", 504);
    }
    console.error("CAD printability service request failed.", error);
    throw new RouteError("Could not reach the CAD printability service.", 503);
  } finally {
    clearTimeout(timeout);
  }
}

function toResponse(error: unknown) {
  if (error instanceof RouteError) {
    return NextResponse.json({ error: error.message }, { status: error.status });
  }
  console.error("Project printability operation failed.", error);
  return NextResponse.json({ error: "Could not complete the printability operation." }, { status: 500 });
}

export async function GET(request: Request, { params }: Context) {
  try {
    const user = await requireSignedInUser();
    await requirePaidAccess(user);

    const { projectId } = await params;
    if (!projectId || projectId.length > 128) throw new RouteError("Invalid project URL.", 400);

    const url = new URL(request.url);
    const versionId = url.searchParams.get("versionId") || undefined;
    if (versionId && versionId.length > 128) throw new RouteError("Invalid project version.", 400);

    const version = await loadOwnedVersion(projectId, user.id, versionId);
    const result = version.geometry.kind === "blueprint"
      ? await callCadService("checkBlueprint", { blueprint: version.geometry.value })
      : await callCadService("check", { partSpec: version.geometry.value });
    const backendNotices = Array.isArray(result.notices)
      ? result.notices.filter((notice): notice is string => typeof notice === "string")
      : [];
    return NextResponse.json({
      ...result,
      notices: Array.from(new Set([...backendNotices, ...version.geometry.notices])).slice(0, 16),
      versionId: version.id,
      versionNumber: version.version,
      partSpecName: version.geometry.name,
      sourceGeometryType: version.geometry.kind,
      limitations: [
        "The current default bed size is 220 × 220 × 250 mm unless a printer-specific bed size is supplied.",
        "These deterministic FDM checks are guidance, not printer/material certification or a guarantee of a successful physical print.",
      ],
    }, { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    return toResponse(error);
  }
}

export async function POST(request: Request, { params }: Context) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  }

  try {
    const user = await requireSignedInUser();
    await requirePaidAccess(user);

    const { projectId } = await params;
    if (!projectId || projectId.length > 128) throw new RouteError("Invalid project URL.", 400);

    const body = await readJson(request);
    const versionId = body.versionId;
    if (typeof versionId !== "string" || !versionId.trim() || versionId.length > 128) {
      throw new RouteError("Select a valid project export version.", 400);
    }
    if (typeof body.action !== "string" || body.action.length > 64) {
      throw new RouteError("Select a valid printability fix action.", 400);
    }
    if (typeof body.checkId !== "string" || body.checkId.length > 64) {
      throw new RouteError("Select a valid printability check.", 400);
    }
    if (
      body.parameters !== undefined &&
      (!body.parameters || typeof body.parameters !== "object" || Array.isArray(body.parameters))
    ) {
      throw new RouteError("Fix parameters must be a JSON object.", 400);
    }

    const version = await loadOwnedVersion(projectId, user.id, versionId);
    if (version.geometry.kind === "blueprint") {
      throw new RouteError(
        "One-click fixes for drawing blueprints are not enabled yet. Review the checks and edit the blueprint before generating a new version.",
        409,
      );
    }
    const result = await callCadService("fix", {
      partSpec: version.geometry.value,
      action: body.action,
      checkId: body.checkId,
      ...(body.parameters ? { parameters: body.parameters } : {}),
    });

    const backendNotices = Array.isArray(result.notices)
      ? result.notices.filter((notice): notice is string => typeof notice === "string").slice(0, 8)
      : [];
    return NextResponse.json({
      ...result,
      versionId: version.id,
      versionNumber: version.version,
      proposalOnly: true,
      notices: [
        ...backendNotices,
        "This is a review-only proposal. It has not changed the saved project specification or the existing STEP/STL exports.",
      ],
    }, { headers: { "Cache-Control": "private, no-store" } });
  } catch (error) {
    return toResponse(error);
  }
}
