import { get } from "@vercel/blob";
import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/server";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ projectId: string; fileType: string }> };

export async function GET(_request: Request, { params }: Context) {
  let user;
  try {
    user = await getCurrentUser();
  } catch (error) {
    console.error("CAD download could not resolve the current user.", error);
    return NextResponse.json({ error: "Authentication service is unavailable." }, { status: 503 });
  }
  if (!user) return NextResponse.json({ error: "Authentication required." }, { status: 401 });

  const { projectId, fileType } = await params;
  const requestedVersionId = new URL(_request.url).searchParams.get("versionId");
  if (fileType !== "step" && fileType !== "stl") {
    return NextResponse.json({ error: "Unsupported export format." }, { status: 400 });
  }

  const project = await prisma.project.findFirst({
    where: { id: projectId, userId: user.id },
    select: { id: true },
  });
  if (!project) return NextResponse.json({ error: "Project or export not found." }, { status: 404 });
  const version = requestedVersionId
    ? await prisma.projectVersion.findFirst({
        where: { id: requestedVersionId, projectId: project.id },
        select: { id: true, version: true, stepFilePath: true, stlFilePath: true },
      })
    : await prisma.projectVersion.findFirst({
        where: {
          projectId: project.id,
          ...(fileType === "step" ? { stepFilePath: { not: null } } : { stlFilePath: { not: null } }),
        },
        orderBy: [{ version: "desc" }, { createdAt: "desc" }],
        select: { id: true, version: true, stepFilePath: true, stlFilePath: true },
      });
  if (!version) return NextResponse.json({ error: "Project or export not found." }, { status: 404 });
  const pathname = fileType === "step" ? version.stepFilePath : version.stlFilePath;
  if (!pathname) return NextResponse.json({ error: "This project has no stored export in that format." }, { status: 404 });

  const token = process.env.PRIVATE_BLOB_READ_WRITE_TOKEN?.trim();
  if (!token) return NextResponse.json({ error: "Private project storage is not configured." }, { status: 503 });

  try {
    const blob = await get(pathname, { access: "private", token });
    if (!blob || blob.statusCode !== 200 || !blob.stream) {
      return NextResponse.json({ error: "The requested export was not found in private storage." }, { status: 404 });
    }
    const contentType = fileType === "step" ? "model/step" : "model/stl";
    return new Response(blob.stream, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Content-Disposition": `attachment; filename="${project.id}-v${version.version}.${fileType}"`,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
      },
    });
  } catch (error) {
    console.error("Private CAD export retrieval failed.", error);
    return NextResponse.json({ error: "Could not retrieve the export from private storage." }, { status: 502 });
  }
}
