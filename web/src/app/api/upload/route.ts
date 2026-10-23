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
        description: `Stored ${valid.length} private source file(s). Open this project to analyze supported drawings with OCR and review the extracted text before generating CAD.`,
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

    const version = await prisma.projectVersion.create({
      data: {
        projectId: project.id,
        version: 1,
        sourceFileName: uploadedFiles.map((file) => file.name).join(", "),
        spec: { uploadedFiles, rejected: rejected.map((item) => ({ name: item.file.name, reason: item.reason })) },
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
      processingAvailable: true,
      message: "Files were stored privately. Open the project to analyze supported drawings with OCR and review the extracted text before CAD generation.",
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
