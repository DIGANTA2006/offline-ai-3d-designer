import { get } from "@vercel/blob";
import { NextResponse } from "next/server";
import type { Prisma } from "@prisma/client";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const MAX_SOURCE_BYTES = 5 * 1024 * 1024;
const MAX_OCR_RESPONSE_BYTES = 1024 * 1024;
const OCR_TIMEOUT_MS = 50_000;

type Context = { params: Promise<{ projectId: string }> };
type StoredSource = {
  pathname: string;
  name: string;
  contentType?: string;
  size?: number;
};
type OCRSpec = {
  dimensions: Record<string, unknown>;
  tolerances: unknown[];
  fits: string[];
  material?: string | null;
  surfaceFinish?: string | null;
  threads: string[];
  views: string[];
  annotations: Array<{ type: string; text: string }>;
  confidence: number;
  rawText: string;
  pageCount: number;
  needsReview: boolean;
  limitations: string[];
};

type OCRResponse = {
  success: boolean;
  spec?: OCRSpec;
  error?: string;
  detail?: string;
  jobId: string;
};

class RouteError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function readLimitedStream(stream: ReadableStream<Uint8Array>, limit: number): Promise<Buffer> {
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
        throw new RouteError("Source drawing exceeds the 5 MiB OCR input limit.", 413);
      }
      chunks.push(Buffer.from(value));
    }
    return Buffer.concat(chunks, size);
  } finally {
    reader.releaseLock();
  }
}

function getCadEndpoint(): URL {
  const raw = process.env.CAD_SERVICE_URL?.trim();
  if (!raw) throw new RouteError("CAD_SERVICE_URL is not configured.", 503);
  let base: URL;
  try {
    base = new URL(raw);
  } catch {
    throw new RouteError("CAD_SERVICE_URL is invalid.", 503);
  }
  if (base.protocol !== "https:" && !(process.env.NODE_ENV !== "production" && base.protocol === "http:" && ["localhost", "127.0.0.1", "::1"].includes(base.hostname))) {
    throw new RouteError("The production CAD service must use HTTPS.", 503);
  }
  return new URL("/api/v1/ocr/extract", base);
}

export async function POST(request: Request, { params }: Context) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  }

  let user;
  try {
    user = await getCurrentUser();
  } catch (error) {
    console.error("Drawing OCR could not resolve the current user.", error);
    return NextResponse.json({ error: "Authentication or database service is unavailable." }, { status: 503 });
  }
  if (!user) return NextResponse.json({ error: "Sign in before analyzing a drawing." }, { status: 401 });

  let projectId: string;
  try {
    ({ projectId } = await params);
  } catch {
    return NextResponse.json({ error: "Invalid project URL." }, { status: 400 });
  }

  try {
    const project = await prisma.project.findFirst({
      where: { id: projectId, userId: user.id },
      include: { versions: { orderBy: { version: "desc" }, take: 1 } },
    });
    const version = project?.versions[0];
    if (!project || !version || !version.spec || typeof version.spec !== "object" || Array.isArray(version.spec)) {
      throw new RouteError("Project or source drawing not found.", 404);
    }

    const subscription = user.role === "ADMIN" ? null : await prisma.subscription.findUnique({ where: { userId: user.id } });
    if (user.role !== "ADMIN" && !(subscription?.tier === "PRO" && subscription.status === "ACTIVE")) {
      throw new RouteError("An active Pro subscription is required to analyze engineering drawings.", 402);
    }

    const rawBody = await request.text();
    if (Buffer.byteLength(rawBody, "utf8") > 8 * 1024) throw new RouteError("OCR request is too large.", 413);
    let body: unknown;
    try { body = JSON.parse(rawBody); } catch { throw new RouteError("A valid JSON body is required.", 400); }
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new RouteError("A JSON object is required.", 400);
    const fileIndex = (body as Record<string, unknown>).fileIndex;
    if (!Number.isSafeInteger(fileIndex) || (fileIndex as number) < 0) {
      throw new RouteError("fileIndex must be a non-negative integer.", 400);
    }

    const storedSpec = version.spec as Record<string, unknown>;
    const sourceFiles = storedSpec.uploadedFiles;
    if (!Array.isArray(sourceFiles) || (fileIndex as number) >= sourceFiles.length) {
      throw new RouteError("Source drawing not found.", 404);
    }
    const source = sourceFiles[fileIndex as number] as Partial<StoredSource>;
    if (typeof source.pathname !== "string" || typeof source.name !== "string") {
      throw new RouteError("Stored source metadata is invalid.", 422);
    }
    if (typeof source.size === "number" && source.size > MAX_SOURCE_BYTES) {
      throw new RouteError("Source drawing exceeds the OCR size limit.", 413);
    }

    const blobToken = process.env.PRIVATE_BLOB_READ_WRITE_TOKEN?.trim();
    if (!blobToken) throw new RouteError("Private source storage is not configured.", 503);

    const blob = await get(source.pathname, { access: "private", token: blobToken });
    if (!blob || blob.statusCode !== 200 || !blob.stream) throw new RouteError("Source drawing could not be read from private storage.", 404);
    const bytes = await readLimitedStream(blob.stream, MAX_SOURCE_BYTES);
    const mimeType = (source.contentType || blob.blob.contentType || "application/octet-stream").split(";", 1)[0].trim().toLowerCase();

    let endpoint: URL;
    try { endpoint = getCadEndpoint(); }
    catch (error) {
      if (error instanceof RouteError) throw error;
      throw new RouteError("CAD service is not configured.", 503);
    }
    const serviceToken = process.env.CAD_SERVICE_TOKEN?.trim();
    if (!serviceToken) throw new RouteError("CAD_SERVICE_TOKEN is not configured on the web deployment.", 503);

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), OCR_TIMEOUT_MS);
    let upstream: Response;
    try {
      upstream = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${serviceToken}` },
        body: JSON.stringify({ fileBase64: bytes.toString("base64"), fileName: source.name, mimeType }),
        cache: "no-store",
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timeout);
    }
    const stated = Number(upstream.headers.get("content-length") ?? 0);
    if (stated > MAX_OCR_RESPONSE_BYTES) throw new RouteError("OCR service response exceeded the configured size limit.", 502);
    const responseText = await upstream.text();
    if (Buffer.byteLength(responseText, "utf8") > MAX_OCR_RESPONSE_BYTES) throw new RouteError("OCR service response exceeded the configured size limit.", 502);
    let result: OCRResponse;
    try { result = JSON.parse(responseText) as OCRResponse; }
    catch { throw new RouteError("OCR service returned an invalid response.", 502); }
    if (!upstream.ok || !result.success || !result.spec) {
      const detail = result.detail || result.error || "The OCR service could not analyze this drawing.";
      throw new RouteError(detail.slice(0, 300), upstream.status >= 400 && upstream.status < 500 ? upstream.status : 502);
    }

    const previousResults = Array.isArray(storedSpec.ocrResults) ? storedSpec.ocrResults : [];
    const nextResults = previousResults.filter((item) =>
      !item || typeof item !== "object" || (item as Record<string, unknown>).fileIndex !== fileIndex
    );
    nextResults.push({
      fileIndex,
      name: source.name,
      jobId: result.jobId,
      extractedAt: new Date().toISOString(),
      spec: result.spec,
    });
    await prisma.projectVersion.update({
      where: { id: version.id },
      data: {
        spec: { ...storedSpec, ocrResults: nextResults } as Prisma.InputJsonValue,
        confidence: result.spec.confidence,
        isApproximation: true,
      },
    });

    try {
      await prisma.auditLog.create({
        data: {
          userId: user.id,
          agent: "drawing-ocr",
          provider: "python-backend-tesseract",
          action: "drawing_ocr_completed",
          status: "success",
          details: { projectId, versionId: version.id, fileIndex, confidence: result.spec.confidence, pageCount: result.spec.pageCount },
        },
      });
    } catch (error) { console.error("OCR succeeded but audit logging failed.", error); }

    return NextResponse.json({
      ok: true,
      projectId,
      versionId: version.id,
      fileIndex,
      name: source.name,
      spec: result.spec,
      needsReview: true,
    }, { status: 200 });
  } catch (error) {
    console.error("Drawing OCR request failed.", error);
    if (error instanceof RouteError) return NextResponse.json({ error: error.message }, { status: error.status });
    if (error instanceof Error && error.name === "AbortError") {
      return NextResponse.json({ error: "Drawing OCR timed out. Try a smaller or clearer drawing." }, { status: 504 });
    }
    return NextResponse.json({ error: "Drawing OCR failed. Check CAD service health and deployment logs." }, { status: 500 });
  }
}
