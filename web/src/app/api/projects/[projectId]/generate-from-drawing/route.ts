import { put } from "@vercel/blob";
import { NextResponse } from "next/server";
import type { Prisma } from "@prisma/client";
import { randomUUID } from "node:crypto";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const MAX_BODY_BYTES = 16 * 1024;
const MAX_CAD_RESPONSE_BYTES = 15 * 1024 * 1024;
const MAX_BASE64_LENGTH = 10 * 1024 * 1024;
const CAD_TIMEOUT_MS = 50_000;

type Context = { params: Promise<{ projectId: string }> };
type OCRSpec = Record<string, unknown> & { rawText?: string; confidence?: number };
type SavedOCRResult = {
  fileIndex: number;
  name: string;
  jobId?: string;
  extractedAt?: string;
  spec: OCRSpec;
};
type CadResponse = {
  success: boolean;
  jobId?: string;
  partSpec?: Record<string, unknown>;
  stepBase64?: string;
  stlBase64?: string;
  fitReport?: string;
  isApproximation?: boolean;
  validationErrors?: string[];
  error?: string;
  detail?: string;
};
type StoredSource = { pathname: string; name: string; contentType?: string; size?: number };

class RouteError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

function getGenerateEndpoint(): URL {
  const raw = process.env.CAD_SERVICE_URL?.trim();
  if (!raw) throw new RouteError("CAD_SERVICE_URL is not configured.", 503);
  let base: URL;
  try { base = new URL(raw); }
  catch { throw new RouteError("CAD_SERVICE_URL is invalid.", 503); }
  if (base.protocol !== "https:" && !(process.env.NODE_ENV !== "production" && base.protocol === "http:" && ["localhost", "127.0.0.1", "::1"].includes(base.hostname))) {
    throw new RouteError("The production CAD service must use HTTPS.", 503);
  }
  return new URL("/api/v1/generate", base);
}

async function readLimitedText(response: Response, limit: number): Promise<string> {
  const statedLength = Number(response.headers.get("content-length") ?? 0);
  if (statedLength > limit) throw new RouteError("CAD service response exceeded the configured size limit.", 502);
  if (!response.body) return "";
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let size = 0;
  let output = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) {
        await reader.cancel();
        throw new RouteError("CAD service response exceeded the configured size limit.", 502);
      }
      output += decoder.decode(value, { stream: true });
    }
    output += decoder.decode();
    return output;
  } finally {
    reader.releaseLock();
  }
}

function decodeBase64(value: unknown, label: string): Buffer {
  if (typeof value !== "string" || value.length === 0 || value.length > MAX_BASE64_LENGTH) {
    throw new RouteError(`CAD service did not return a valid ${label} export.`, 502);
  }
  if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) {
    throw new RouteError(`CAD service returned invalid Base64 for ${label}.`, 502);
  }
  const bytes = Buffer.from(value, "base64");
  if (!bytes.length) throw new RouteError(`CAD service returned an empty ${label} export.`, 502);
  return bytes;
}

function getOcrResult(specValue: unknown, fileIndex: number): SavedOCRResult | null {
  if (!specValue || typeof specValue !== "object" || Array.isArray(specValue)) return null;
  const root = specValue as Record<string, unknown>;
  const results = root.ocrResults;
  if (!Array.isArray(results)) return null;
  for (const item of results) {
    if (!item || typeof item !== "object" || Array.isArray(item)) continue;
    const result = item as Record<string, unknown>;
    if (result.fileIndex !== fileIndex || !result.spec || typeof result.spec !== "object" || Array.isArray(result.spec)) continue;
    return result as unknown as SavedOCRResult;
  }
  return null;
}

export async function POST(request: Request, { params }: Context) {
  if (!isSameOriginRequest(request)) return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  let user;
  try { user = await getCurrentUser(); }
  catch (error) {
    console.error("Drawing CAD generation could not resolve the current user.", error);
    return NextResponse.json({ error: "Authentication or database service is unavailable." }, { status: 503 });
  }
  if (!user) return NextResponse.json({ error: "Sign in before generating CAD from a drawing." }, { status: 401 });

  let projectId: string;
  try { ({ projectId } = await params); }
  catch { return NextResponse.json({ error: "Invalid project URL." }, { status: 400 }); }

  let usageReserved = false;
  let projectMarkedProcessing = false;
  let periodStart: Date | null = null;

  try {
    const statedLength = Number(request.headers.get("content-length") ?? 0);
    if (statedLength > MAX_BODY_BYTES) throw new RouteError("Generation request is too large.", 413);
    const rawBody = await request.text();
    if (Buffer.byteLength(rawBody, "utf8") > MAX_BODY_BYTES) throw new RouteError("Generation request is too large.", 413);
    let body: unknown;
    try { body = JSON.parse(rawBody); } catch { throw new RouteError("A valid JSON body is required.", 400); }
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new RouteError("A JSON object is required.", 400);
    const input = body as Record<string, unknown>;
    if (input.reviewed !== true) throw new RouteError("Review the extracted text, dimensions and shape assumptions before generation.", 409);
    if (typeof input.reviewedDescription !== "string" || input.reviewedDescription.trim().length < 5 || input.reviewedDescription.length > 4000) {
      throw new RouteError("Provide a reviewed dimensioned description between 5 and 4,000 characters.", 400);
    }
    if (typeof input.fileIndex !== "number" || !Number.isSafeInteger(input.fileIndex) || input.fileIndex < 0) {
      throw new RouteError("fileIndex must be a non-negative integer.", 400);
    }
    const reviewedDescription = input.reviewedDescription.trim();
    const fileIndex = input.fileIndex;

    const blobToken = process.env.PRIVATE_BLOB_READ_WRITE_TOKEN?.trim();
    const serviceToken = process.env.CAD_SERVICE_TOKEN?.trim();
    if (!blobToken) throw new RouteError("Private project storage is not configured.", 503);
    if (!serviceToken) throw new RouteError("CAD_SERVICE_TOKEN is not configured on the web deployment.", 503);

    const project = await prisma.project.findFirst({
      where: { id: projectId, userId: user.id },
      include: { versions: { orderBy: { version: "desc" }, take: 1 } },
    });
    const sourceVersion = project?.versions[0];
    if (!project || !sourceVersion || !sourceVersion.spec || typeof sourceVersion.spec !== "object" || Array.isArray(sourceVersion.spec)) {
      throw new RouteError("Project or OCR result not found. Analyze the source drawing first.", 404);
    }

    const subscription = user.role === "ADMIN" ? null : await prisma.subscription.findUnique({ where: { userId: user.id } });
    if (user.role !== "ADMIN" && !(subscription?.tier === "PRO" && subscription.status === "ACTIVE")) {
      throw new RouteError("An active Pro subscription is required to generate CAD files.", 402);
    }

    const storedSpec = sourceVersion.spec as Record<string, unknown>;
    const ocrResult = getOcrResult(storedSpec, fileIndex);
    if (!ocrResult) throw new RouteError("No stored OCR result exists for this file. Analyze it first.", 409);
    const rawSources = storedSpec.uploadedFiles;
    const source = Array.isArray(rawSources) ? rawSources[fileIndex] as Partial<StoredSource> | undefined : undefined;
    if (!source || typeof source.name !== "string") throw new RouteError("Source file metadata is invalid.", 422);

    const period = new Date();
    periodStart = new Date(Date.UTC(period.getUTCFullYear(), period.getUTCMonth(), 1));
    if (user.role !== "ADMIN") {
      const usageWhere = { userId_action_periodStart: { userId: user.id, action: "generation", periodStart } };
      await prisma.usageRecord.upsert({
        where: usageWhere,
        update: {},
        create: { userId: user.id, action: "generation", periodStart, count: 0 },
      });
      const reservation = await prisma.usageRecord.updateMany({
        where: { userId: user.id, action: "generation", periodStart },
        data: { count: { increment: 1 } },
      });
      if (reservation.count !== 1) throw new RouteError("Could not reserve the CAD generation allowance; retry shortly.", 503);
      usageReserved = true;
    }

    await prisma.project.update({ where: { id: project.id }, data: { status: "PROCESSING" } });
    projectMarkedProcessing = true;

    let endpoint: URL;
    try { endpoint = getGenerateEndpoint(); }
    catch (error) {
      if (error instanceof RouteError) throw error;
      throw new RouteError("CAD service is not configured.", 503);
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), CAD_TIMEOUT_MS);
    let upstream: Response;
    try {
      upstream = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${serviceToken}` },
        body: JSON.stringify({
          spec: ocrResult.spec,
          jobId: randomUUID(),
          userId: user.id,
          reviewed: true,
          reviewedDescription,
        }),
        cache: "no-store",
        signal: controller.signal,
      });
    } finally { clearTimeout(timeout); }

    const responseText = await readLimitedText(upstream, MAX_CAD_RESPONSE_BYTES);
    let cad: CadResponse;
    try { cad = JSON.parse(responseText) as CadResponse; }
    catch { throw new RouteError("CAD service returned an invalid generation response.", 502); }
    if (!upstream.ok) {
      throw new RouteError((cad.detail || cad.error || "CAD service request failed.").slice(0, 300), upstream.status >= 500 ? 503 : upstream.status);
    }
    if (!cad.success) throw new RouteError((cad.error || cad.validationErrors?.join("; ") || "Reviewed drawing could not be converted to supported CAD.").slice(0, 500), 422);

    const stepBytes = decodeBase64(cad.stepBase64, "STEP");
    const stlBytes = decodeBase64(cad.stlBase64, "STL");
    const nextVersion = sourceVersion.version + 1;
    const basePath = `projects/${user.id}/${project.id}/v${nextVersion}`;
    const [stepBlob, stlBlob] = await Promise.all([
      put(`${basePath}/part-${randomUUID()}.step`, stepBytes, { access: "private", token: blobToken, contentType: "model/step", addRandomSuffix: true }),
      put(`${basePath}/part-${randomUUID()}.stl`, stlBytes, { access: "private", token: blobToken, contentType: "model/stl", addRandomSuffix: true }),
    ]);

    const sourceRecords = Array.isArray(storedSpec.uploadedFiles) ? storedSpec.uploadedFiles : [];
    const nextSpec = {
      uploadedFiles: sourceRecords,
      rejected: storedSpec.rejected ?? [],
      ocrResults: Array.isArray(storedSpec.ocrResults) ? storedSpec.ocrResults : [],
      sourceOCR: ocrResult.spec,
      reviewedDescription,
      partSpec: cad.partSpec ?? {},
      fitReport: cad.fitReport ?? null,
    };
    const version = await prisma.projectVersion.create({
      data: {
        projectId: project.id,
        version: nextVersion,
        inputText: reviewedDescription,
        sourceFileName: source.name,
        spec: nextSpec as Prisma.InputJsonValue,
        stepFilePath: stepBlob.pathname,
        stlFilePath: stlBlob.pathname,
        confidence: typeof ocrResult.spec.confidence === "number" ? ocrResult.spec.confidence : null,
        isApproximation: true,
      },
      select: { id: true, version: true },
    });
    await prisma.project.update({ where: { id: project.id }, data: { status: "SUCCEEDED" } });

    try {
      await prisma.auditLog.create({
        data: {
          userId: user.id,
          agent: "drawing-to-cad",
          provider: "python-backend",
          action: "drawing_cad_generated",
          status: "success",
          details: { projectId, versionId: version.id, sourceVersionId: sourceVersion.id, fileIndex, isApproximation: true },
        },
      });
    } catch (error) { console.error("Drawing CAD generation succeeded but audit logging failed.", error); }

    return NextResponse.json({
      ok: true,
      projectId,
      versionId: version.id,
      version: version.version,
      status: "SUCCEEDED",
      isApproximation: true,
      message: "CAD exports were stored. Compare the model against the reviewed drawing; this is not a certified interpretation.",
    }, { status: 201 });
  } catch (error) {
    console.error("Drawing-to-CAD generation failed.", error);
    if (projectMarkedProcessing) {
      try { await prisma.project.update({ where: { id: projectId }, data: { status: "FAILED" } }); }
      catch (updateError) { console.error("Could not mark drawing CAD project failed.", updateError); }
    }
    if (usageReserved && periodStart) {
      try {
        await prisma.usageRecord.updateMany({
          where: { userId: user.id, action: "generation", periodStart, count: { gt: 0 } },
          data: { count: { decrement: 1 } },
        });
      } catch (usageError) { console.error("Could not release failed drawing-generation reservation.", usageError); }
    }
    const status = error instanceof RouteError ? error.status : error instanceof Error && error.name === "AbortError" ? 504 : 500;
    const message = error instanceof Error && error.name === "AbortError" ? "Drawing CAD generation timed out. Try a simpler description." : error instanceof RouteError ? error.message : "Drawing CAD generation failed. Check service logs.";
    return NextResponse.json({ error: message }, { status });
  }
}
