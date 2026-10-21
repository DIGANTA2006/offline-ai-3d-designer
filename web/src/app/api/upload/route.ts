import { NextResponse } from "next/server";
import { requireUser } from "@/lib/auth/server";
import { validateFiles } from "@/lib/upload/validation";
import { prisma } from "@/lib/prisma";
import { v4 as uuidv4 } from "uuid";
import { put } from "@vercel/blob";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * POST /api/upload
 * Accepts multipart/form-data with files.
 * Validates, stores in Vercel Blob (or local fallback), creates Project + ProjectVersion records.
 * Returns projectId and version for the client to poll status.
 */
export async function POST(request: Request) {
  const user = await requireUser();

  // Check subscription limits (free tier: 3 generations/month, 5 MB per file)
  const subscription = await prisma.subscription.findUnique({ where: { userId: user.id } });
  const isPro = subscription?.tier === "PRO" && subscription?.status === "ACTIVE";
  const freeFileSizeLimit = 5 * 1024 * 1024; // 5 MB
  const freeMonthlyGenerations = 3;

  if (!isPro) {
    // Check monthly generation count
    const periodStart = new Date();
    periodStart.setDate(1);
    periodStart.setHours(0, 0, 0, 0);
    const usage = await prisma.usageRecord.findUnique({
      where: { userId_action_periodStart: { userId: user.id, action: "generation", periodStart } },
    });
    if (usage && usage.count >= freeMonthlyGenerations) {
      return NextResponse.json(
        { error: "Free tier limit reached. Upgrade to Pro for unlimited generations." },
        { status: 403 }
      );
    }
  }

  try {
    const formData = await request.formData();
    const files = formData.getAll("files") as File[];

    if (!files.length) {
      return NextResponse.json({ error: "No files provided" }, { status: 400 });
    }

    // Validate files
    const { valid, rejected } = validateFiles(files);
    if (!valid.length) {
      return NextResponse.json(
        { error: "All files rejected", rejected: rejected.map((r) => ({ name: r.file.name, reason: r.reason })) },
        { status: 400 }
      );
    }

    // Enforce free tier per-file size limit
    if (!isPro) {
      const oversized = valid.filter((v) => v.size > freeFileSizeLimit);
      if (oversized.length) {
        return NextResponse.json(
          { error: "Free tier limited to 5 MB per file. Upgrade to Pro for 25 MB files." },
          { status: 403 }
        );
      }
    }

    // Create project
    const project = await prisma.project.create({
      data: {
        userId: user.id,
        name: valid[0].file.name.replace(/\.[^.]+$/, ""),
        description: `Uploaded ${valid.length} file(s)`,
        status: "QUEUED",
      },
    });

    // Upload files to blob storage and create version records
    const uploadedFiles: Array<{ url: string; name: string; type: string; size: number }> = [];
    for (const v of valid) {
      const blob = await put(`projects/${project.id}/${uuidv4()}-${v.file.name}`, v.file, {
        access: "public",
        addRandomSuffix: true,
      });
      uploadedFiles.push({ url: blob.url, name: v.file.name, type: v.type, size: v.size });
    }

    // Create initial version with source file references
    const version = await prisma.projectVersion.create({
      data: {
        projectId: project.id,
        version: 1,
        sourceFileName: uploadedFiles.map((f) => f.name).join(", "),
        spec: { uploadedFiles, rejected: rejected.map((r) => ({ name: r.file.name, reason: r.reason })) },
      },
    });

    // Increment usage counter
    const periodStart = new Date();
    periodStart.setDate(1);
    periodStart.setHours(0, 0, 0, 0);
    await prisma.usageRecord.upsert({
      where: { userId_action_periodStart: { userId: user.id, action: "generation", periodStart } },
      update: { count: { increment: 1 } },
      create: { userId: user.id, action: "generation", periodStart, count: 1 },
    });

    // Log audit
    await prisma.auditLog.create({
      data: {
        userId: user.id,
        agent: "upload",
        provider: "vercel-blob",
        action: "files_uploaded",
        status: "success",
        details: { projectId: project.id, versionId: version.id, fileCount: valid.length },
      },
    });

    return NextResponse.json({
      projectId: project.id,
      versionId: version.id,
      version: version.version,
      uploadedFiles: uploadedFiles.map((f) => ({ name: f.name, url: f.url, type: f.type })),
      rejected: rejected.map((r) => ({ name: r.file.name, reason: r.reason })),
    });
  } catch (error) {
    console.error("Upload error:", error);
    return NextResponse.json({ error: "Upload failed. Please try again." }, { status: 500 });
  }
}
