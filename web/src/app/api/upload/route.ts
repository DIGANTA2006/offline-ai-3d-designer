import { put } from "@vercel/blob";
import { NextResponse } from "next/server";
import { randomUUID } from "node:crypto";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { validateFiles } from "@/lib/upload/validation";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Vercel Functions have a 4.5 MB request-body limit. Leave space for multipart headers.
const MAX_BATCH_BYTES = 3 * 1024 * 1024;
const OCR_TIMEOUT_MS = 35_000;

type StoredOcrResult = {
  success: boolean;
  jobId?: string;
  spec?: Record<string, unknown>;
  error?: string;
};

function getOcrMimeType(file: File): string | null {
  const extension = file.name.toLowerCase().split(".").pop();
  const raw = file.type.toLowerCase().split(";", 1)[0].trim();
  const mime = raw === "image/jpg" ? "image/jpeg" : raw;
  if (mime === "application/pdf" || mime === "image/png" || mime === "image/jpeg" || mime === "image/webp") return mime;
  if (extension === "pdf") return "application/pdf";
  if (extension === "png") return "image/png";
  if (extension === "jpg" || extension === "jpeg") return "image/jpeg";
  if (extension === "webp") return "image/webp";
  return null;
}

async function runDrawingOcr(file: File): Promise<StoredOcrResult> {
  const mimeType = getOcrMimeType(file);
  if (!mimeType) {
    return { success: false, error: "OCR supports PDF, PNG, JPEG, and WEBP. The file was stored privately but not processed." };
  }

  const configured = process.env.CAD_SERVICE_URL?.trim().replace(/\\/+$/, "");
  if (!configured) return { success: false, error: "CAD_SERVICE_URL is not configured; source file was stored privately." };
  let baseUrl: URL;
  try {
    baseUrl = new URL(configured);
  } catch {
    return { success: false, error: "CAD_SERVICE_URL is invalid; source file was stored privately." };
  }
  const loopback = ["localhost", "127.0.0.1", "::1"].includes(baseUrl.hostname);
  if (baseUrl.protocol !== "https:" && !(process.env.NODE_ENV !== "production" && baseUrl.protocol === "http:" && loopback)) {
    return { success: false, error: "CAD service must use HTTPS in production; source file was stored privately." };
  }
  const token = process.env.CAD_SERVICE_TOKEN?.trim();
  if (!token) return { success: false, error: "CAD_SERVICE_TOKEN is not configured; source file was stored privately." };

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), OCR_TIMEOUT_MS);
  try {
    const encoded = Buffer.from(await file.arrayBuffer()).toString("base64");
    const upstream = await fetch(new URL("/api/v1/ocr/extract", baseUrl), {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify({ fileBase64: encoded, fileName: file.name.slice(0, 240), mimeType }),
      cache: "no-store",
      signal: controller.signal,
    });
    const result = await upstream.json().catch(() => ({})) as StoredOcrResult & { detail?: string };
    if (!upstream.ok) {
      return { success: false, error: result.error ?? result.detail ?? `OCR service returned HTTP ${upstream.status}; the file was still stored privately.` };
    }
    return result;
  } catch (error) {
    const timedOut = error instanceof Error && error.name === "AbortError";
    return {
      success: false,
      error: timedOut
        ? "OCR timed out. The drawing was stored privately; try a clearer or smaller file."
        : "OCR service is unavailable. The drawing was stored privately and can be retried later.",
    };
  } finally {
    clearTimeout(timeout);
  }
}

export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  }

  let user;
  try {
    user = await getCurrentUser();
  } catch (error) {
    console.error("Upload API could not resolve the current user.", error);
    return NextResponse.json({ error: "Authentication or database service is unavailable." }, { status: 503 });
  }
  if (!user) return NextResponse.json({ error: "Sign in before uploading files." }, { status: 401 });

  const privateBlobToken = process.env.PRIVATE_BLOB_READ_WRITE_TOKEN?.trim();
  if (!privateBlobToken) {
    return NextResponse.json({ error: "Private file storage is not configured. Connect a private Vercel Blob store first." }, { status: 503 });
  }
  const contentLength = Number(request.headers.get("content-length") ?? 0);
  if (contentLength > MAX_BATCH_BYTES + 64 * 1024) {
    return NextResponse.json({ error: "This upload route accepts up to 3 MiB total per batch. Larger files require the secure direct-upload flow." }, { status: 413 });
  }

  let projectId: string | null = null;
  try {
    const formData = await request.formData();
    const values = formData.getAll("files");
    if (!values.length || values.some((value) => typeof value === "string" || !(value instanceof File))) {
      return NextResponse.json({ error: "Upload one or more files using the files field." }, { status: 400 });
    }
    const files = values as File[];
    const totalSize = files.reduce((total, file) => total + file.size, 0);
    if (totalSize > MAX_BATCH_BYTES) {
      return NextResponse.json({ error: "This upload route accepts up to 3 MiB total per batch." }, { status: 413 });
    }

    const { valid, rejected } = validateFiles(files);
    if (!valid.length) {
      return NextResponse.json({ error: "No supported files were found.", rejected: rejected.map((item) => ({ name: item.file.name, reason: item.reason })) }, { status: 400 });
    }

    const project = await prisma.project.create({
      data: {
        userId: user.id,
        name: valid[0].file.name.replace(/\.[^.]+$/, "").slice(0, 80) || "Engineering drawing upload",
        description: `Stored ${valid.length} source file(s). OCR extraction is provisional and requires manual verification before CAD generation.`,
        status: "DRAFT",
      },
      select: { id: true },
    });
    projectId = project.id;

    const uploadedFiles: Array<{ pathname: string; name: string; type: string; size: number; contentType: string }> = [];
    for (const item of valid) {
      const originalName = item.file.name.replace(/[\\/\x00-\x1f]/g, "_").slice(0, 120) || "drawing";
      const blob = await put(`projects/${user.id}/${project.id}/source/${randomUUID()}-${originalName}`, item.file, {
        access: "private",
        token: privateBlobToken,
        addRandomSuffix: true,
        contentType: item.file.type || "application/octet-stream",
      });
      uploadedFiles.push({ pathname: blob.pathname, name: originalName, type: item.type, size: item.size, contentType: item.file.type || "application/octet-stream" });
    }

    // OCR only the first supported raster/PDF drawing in a batch. This bounds
    // request duration while preserving every uploaded source file privately.
    // OCR results are candidates, not manufacturing-authoritative dimensions.
    const ocrSource = valid.find((item) => getOcrMimeType(item.file) !== null);
    const ocrResult = ocrSource
      ? await runDrawingOcr(ocrSource.file)
      : { success: false, error: "Files were stored privately, but this batch contains no PDF or supported raster drawing for OCR." };

    const version = await prisma.projectVersion.create({
      data: {
        projectId: project.id,
        version: 1,
        sourceFileName: uploadedFiles.map((file) => file.name).join(", "),
        spec: {
          uploadedFiles,
          rejected: rejected.map((item) => ({ name: item.file.name, reason: item.reason })),
          ocrSourceFileName: ocrSource?.file.name ?? null,
          ocrResult,
        },
      },
      select: { id: true, version: true },
    });

    await prisma.auditLog.create({
      data: {
        userId: user.id,
        agent: "upload",
        provider: "vercel-private-blob",
        action: "files_uploaded",
        status: "success",
        details: { projectId: project.id, versionId: version.id, fileCount: uploadedFiles.length },
      },
    }).catch((error) => console.error("Upload succeeded but audit logging failed.", error));

    return NextResponse.json({
      projectId: project.id,
      versionId: version.id,
      version: version.version,
      uploadedFiles: uploadedFiles.map(({ name, type, size }) => ({ name, type, size })),
      rejected: rejected.map((item) => ({ name: item.file.name, reason: item.reason })),
      ocrResult,
      processingAvailable: Boolean(ocrResult.success),
      message: ocrResult.success
        ? "Files were stored privately and OCR candidates were extracted. Verify all dimensions manually; drawing-to-parametric-CAD generation is not automated yet."
        : `Files were stored privately. OCR was not completed: ${ocrResult.error ?? "unknown OCR error"}`,
    }, { status: 201 });
  } catch (error) {
    console.error("Private drawing upload failed.", error);
    if (projectId) {
      try { await prisma.project.update({ where: { id: projectId }, data: { status: "FAILED" } }); }
      catch (updateError) { console.error("Could not mark failed upload project.", updateError); }
    }
    return NextResponse.json({ error: "Upload failed. Check private Blob storage configuration and deployment logs." }, { status: 500 });
  }
}
