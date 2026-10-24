import { del } from "@vercel/blob";
import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";
import { pruneProjectVersions } from "@/lib/project-retention";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ projectId: string; versionId: string }> };

const isGenerated = (version: { stepFilePath: string | null; stlFilePath: string | null; glbFilePath: string | null }) =>
  Boolean(version.stepFilePath || version.stlFilePath || version.glbFilePath);

export async function PATCH(request: Request, { params }: Context) {
  if (!isSameOriginRequest(request)) return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  let user;
  try { user = await getCurrentUser(); }
  catch { return NextResponse.json({ error: "Authentication service is unavailable." }, { status: 503 }); }
  if (!user) return NextResponse.json({ error: "Sign in before changing export retention." }, { status: 401 });

  let projectId: string, versionId: string;
  try { ({ projectId, versionId } = await params); }
  catch { return NextResponse.json({ error: "Invalid export URL." }, { status: 400 }); }
  let body: unknown;
  try { body = await request.json(); }
  catch { return NextResponse.json({ error: "A valid JSON body is required." }, { status: 400 }); }
  if (!body || typeof body !== "object" || Array.isArray(body) || typeof (body as Record<string, unknown>).isProtected !== "boolean") {
    return NextResponse.json({ error: "isProtected must be a boolean." }, { status: 400 });
  }
  const ownedProject = await prisma.project.findFirst({ where: { id: projectId, userId: user.id }, select: { id: true } });
  if (!ownedProject) return NextResponse.json({ error: "Project not found." }, { status: 404 });
  const version = await prisma.projectVersion.findFirst({
    where: { id: versionId, projectId: ownedProject.id },
    select: { id: true, version: true, isProtected: true, stepFilePath: true, stlFilePath: true, glbFilePath: true },
  });
  if (!version || !isGenerated(version)) return NextResponse.json({ error: "Generated export version not found." }, { status: 404 });
  const updated = await prisma.projectVersion.update({
    where: { id: version.id },
    data: { isProtected: (body as { isProtected: boolean }).isProtected },
    select: { id: true, version: true, isProtected: true },
  });

  let prunedVersions: number[] = [];
  let cleanupWarning: string | undefined;
  if (!updated.isProtected) {
    const token = process.env.PRIVATE_BLOB_READ_WRITE_TOKEN?.trim();
    if (!token) cleanupWarning = "Protection was removed, but automatic cleanup is pending storage configuration.";
    else {
      try { prunedVersions = await pruneProjectVersions(projectId, user.id, token); }
      catch (error) {
        console.error("Unprotected CAD version cleanup failed.", error);
        cleanupWarning = "Protection was updated, but automatic pruning failed. Retry later.";
      }
    }
  }
  return NextResponse.json({ ok: true, ...updated, prunedVersions, ...(cleanupWarning ? { warning: cleanupWarning } : {}) });
}

export async function DELETE(request: Request, { params }: Context) {
  if (!isSameOriginRequest(request)) return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  let user;
  try { user = await getCurrentUser(); }
  catch { return NextResponse.json({ error: "Authentication service is unavailable." }, { status: 503 }); }
  if (!user) return NextResponse.json({ error: "Sign in before deleting exports." }, { status: 401 });

  let projectId: string, versionId: string;
  try { ({ projectId, versionId } = await params); }
  catch { return NextResponse.json({ error: "Invalid export URL." }, { status: 400 }); }

  const ownedProject = await prisma.project.findFirst({ where: { id: projectId, userId: user.id }, select: { id: true } });
  if (!ownedProject) return NextResponse.json({ error: "Project not found." }, { status: 404 });
  const version = await prisma.projectVersion.findFirst({
    where: { id: versionId, projectId: ownedProject.id },
    select: { id: true, version: true, stepFilePath: true, stlFilePath: true, glbFilePath: true },
  });
  if (!version || !isGenerated(version)) return NextResponse.json({ error: "Generated export version not found." }, { status: 404 });
  const token = process.env.PRIVATE_BLOB_READ_WRITE_TOKEN?.trim();
  if (!token) return NextResponse.json({ error: "Private storage is not configured." }, { status: 503 });

  const prefix = `projects/${user.id}/${projectId}/`;
  const paths = [version.stepFilePath, version.stlFilePath, version.glbFilePath]
    .filter((path): path is string => typeof path === "string" && path.startsWith(prefix) && !path.includes(".."));
  try {
    if (paths.length) await del([...new Set(paths)], { token });
    await prisma.projectVersion.delete({ where: { id: version.id } });
    const remaining = await prisma.projectVersion.findFirst({
      where: {
        projectId,
        OR: [{ stepFilePath: { not: null } }, { stlFilePath: { not: null } }, { glbFilePath: { not: null } }],
      },
      select: { id: true },
    });
    await prisma.project.update({ where: { id: projectId }, data: { status: remaining ? "SUCCEEDED" : "DRAFT" } });
    return NextResponse.json({ ok: true, deletedVersion: version.version });
  } catch (error) {
    console.error("Manual CAD export deletion failed.", error);
    return NextResponse.json({ error: "Could not delete this export from storage. The database record was preserved where possible." }, { status: 502 });
  }
}
