import { get } from "@vercel/blob";
import { NextResponse } from "next/server";
import { getCurrentUser } from "@/lib/auth/server";
import { prisma } from "@/lib/prisma";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Context = { params: Promise<{ projectId: string; fileIndex: string }> };
type StoredSource = { pathname: string; name: string; contentType?: string };

export async function GET(_request: Request, { params }: Context) {
  let user;
  try {
    user = await getCurrentUser();
  } catch (error) {
    console.error("Source file download could not resolve the current user.", error);
    return NextResponse.json({ error: "Authentication service is unavailable." }, { status: 503 });
  }
  if (!user) return NextResponse.json({ error: "Authentication required." }, { status: 401 });

  const { projectId, fileIndex } = await params;
  const index = Number(fileIndex);
  if (!Number.isSafeInteger(index) || index < 0) return NextResponse.json({ error: "Invalid file index." }, { status: 400 });

  const project = await prisma.project.findFirst({
    where: { id: projectId, userId: user.id },
    include: { versions: { orderBy: { version: "desc" }, take: 1 } },
  });
  const version = project?.versions[0];
  if (!project || !version || !version.spec || typeof version.spec !== "object" || Array.isArray(version.spec)) {
    return NextResponse.json({ error: "Project or source file not found." }, { status: 404 });
  }
  const rawFiles = (version.spec as Record<string, unknown>).uploadedFiles;
  if (!Array.isArray(rawFiles) || index >= rawFiles.length) {
    return NextResponse.json({ error: "Source file not found." }, { status: 404 });
  }
  const file = rawFiles[index] as Partial<StoredSource>;
  if (typeof file.pathname !== "string" || typeof file.name !== "string") {
    return NextResponse.json({ error: "Source file record is invalid." }, { status: 404 });
  }

  const token = process.env.PRIVATE_BLOB_READ_WRITE_TOKEN?.trim();
  if (!token) return NextResponse.json({ error: "Private project storage is not configured." }, { status: 503 });

  try {
    const blob = await get(file.pathname, { access: "private", token });
    if (!blob || blob.statusCode !== 200 || !blob.stream) {
      return NextResponse.json({ error: "Source file not found in private storage." }, { status: 404 });
    }
    const safeName = file.name.replace(/[\r\n"\\]/g, "_").slice(0, 120) || "source-file";
    return new Response(blob.stream, {
      status: 200,
      headers: {
        "Content-Type": file.contentType || blob.blob.contentType || "application/octet-stream",
        "Content-Disposition": `attachment; filename="${safeName}"`,
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
      },
    });
  } catch (error) {
    console.error("Private source-file retrieval failed.", error);
    return NextResponse.json({ error: "Could not retrieve the source file from private storage." }, { status: 502 });
  }
}
