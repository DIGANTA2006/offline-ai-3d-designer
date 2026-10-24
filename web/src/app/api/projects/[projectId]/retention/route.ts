import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";
import { MAX_ACTIVE_PROJECTS, pruneUserProjects } from "@/lib/project-retention";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ projectId: string }> };

export async function PATCH(request: Request, { params }: Context) {
  if (!isSameOriginRequest(request)) return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  let user;
  try { user = await getCurrentUser(); }
  catch { return NextResponse.json({ error: "Authentication service is unavailable." }, { status: 503 }); }
  if (!user) return NextResponse.json({ error: "Sign in before changing project retention." }, { status: 401 });

  let projectId: string;
  try { ({ projectId } = await params); }
  catch { return NextResponse.json({ error: "Invalid project URL." }, { status: 400 }); }

  let body: unknown;
  try { body = await request.json(); }
  catch { return NextResponse.json({ error: "A valid JSON body is required." }, { status: 400 }); }
  if (!body || typeof body !== "object" || Array.isArray(body) || typeof (body as Record<string, unknown>).isImportant !== "boolean") {
    return NextResponse.json({ error: "isImportant must be a boolean." }, { status: 400 });
  }

  const isImportant = (body as { isImportant: boolean }).isImportant;
  const project = await prisma.project.findFirst({ where: { id: projectId, userId: user.id }, select: { id: true } });
  if (!project) return NextResponse.json({ error: "Project not found." }, { status: 404 });
  if (isImportant) {
    const count = await prisma.project.count({ where: { userId: user.id } });
    if (count > MAX_ACTIVE_PROJECTS) {
      return NextResponse.json({
        error: "Your saved history currently exceeds the 10-project limit. Unpin or delete an older project before marking another project important.",
      }, { status: 409 });
    }
  }
  const updated = await prisma.project.update({
    where: { id: project.id },
    data: { isImportant },
    select: { id: true, isImportant: true },
  });

  let prunedProjectIds: string[] = [];
  let warning: string | undefined;
  if (!updated.isImportant) {
    const token = process.env.PRIVATE_BLOB_READ_WRITE_TOKEN?.trim();
    if (!token) {
      warning = "Project was unpinned, but automatic history cleanup requires private storage configuration.";
    } else {
      try {
        prunedProjectIds = await pruneUserProjects(user.id, token, { excludeProjectId: project.id });
      } catch (error) {
        console.error("Project retention cleanup failed after unpinning.", error);
        warning = "Project was unpinned, but the 10-project history cap could not be restored automatically.";
      }
    }
  }
  return NextResponse.json({ ok: true, ...updated, prunedProjectIds, ...(warning ? { warning } : {}) });
}
