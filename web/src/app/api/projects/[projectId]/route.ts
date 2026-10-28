import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";
import { deleteProjectAndBlobs } from "@/lib/project-retention";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
type Context = { params: Promise<{ projectId: string }> };

export async function DELETE(request: Request, { params }: Context) {
  if (!isSameOriginRequest(request)) return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  let user;
  try { user = await getCurrentUser(); }
  catch { return NextResponse.json({ error: "Authentication service is unavailable." }, { status: 503 }); }
  if (!user) return NextResponse.json({ error: "Sign in before deleting a project." }, { status: 401 });

  let projectId: string;
  try { ({ projectId } = await params); }
  catch { return NextResponse.json({ error: "Invalid project URL." }, { status: 400 }); }

  const project = await prisma.project.findFirst({ where: { id: projectId, userId: user.id }, select: { id: true, status: true } });
  if (!project) return NextResponse.json({ error: "Project not found." }, { status: 404 });
  if (project.status === "QUEUED" || project.status === "PROCESSING") {
    return NextResponse.json({ error: "This project is still generating. Wait for it to finish, then delete it." }, { status: 409 });
  }

  const token = process.env.PRIVATE_BLOB_READ_WRITE_TOKEN?.trim();
  if (!token) return NextResponse.json({ error: "Private storage is not configured." }, { status: 503 });

  try {
    const deleted = await deleteProjectAndBlobs(project.id, user.id, token);
    if (!deleted) return NextResponse.json({ error: "Project not found." }, { status: 404 });
    return NextResponse.json({ ok: true, deletedProjectId: project.id });
  } catch (error) {
    console.error("Project deletion failed.", error);
    return NextResponse.json({ error: "Could not delete this project. Try again in a moment." }, { status: 502 });
  }
}
