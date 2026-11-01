import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ projectId: string }> };

/**
 * Pinning only marks a project as important for display. It never triggers deletion:
 * projects are removed only by an explicit delete, and the free plan blocks a second project.
 */
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
  const updated = await prisma.project.update({
    where: { id: project.id },
    data: { isImportant },
    select: { id: true, isImportant: true },
  });
  return NextResponse.json({ ok: true, ...updated, prunedProjectIds: [] });
}
