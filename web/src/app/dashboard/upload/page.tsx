import { requireUser } from "@/lib/auth/server";
import { prisma } from "@/lib/prisma";
import { UploadPanel } from "@/components/upload/upload-panel";
import { ProjectStatus } from "@prisma/client";

export const dynamic = "force-dynamic";

export default async function UploadPage() {
  const user = await requireUser();

  // Get user's recent projects for context
  const recentProjects = await prisma.project.findMany({
    where: { userId: user.id },
    orderBy: { updatedAt: "desc" },
    take: 5,
    select: { id: true, name: true, status: true, createdAt: true, versions: { take: 1, orderBy: { version: "desc" } } },
  });

  return (
    <main className="min-h-screen bg-background px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-4xl">
        <header className="mb-8">
          <h1 className="text-3xl font-semibold tracking-tight">Upload Drawings</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Upload PDF engineering drawings, component photos, or DXF files. Our AI pipeline will extract
            dimensions, tolerances, and generate a parametric 3D model.
          </p>
        </header>

        <UploadPanel
          onUploadComplete={(projectId, versionId) => {
            // Navigation handled client-side via router in the component
            window.location.href = `/dashboard/projects/${projectId}?version=${versionId}`;
          }}
        />

        {recentProjects.length > 0 && (
          <section className="mt-10">
            <h2 className="text-lg font-semibold mb-4">Recent Projects</h2>
            <div className="grid gap-4 sm:grid-cols-2">
              {recentProjects.map((project) => (
                <a
                  key={project.id}
                  href={`/dashboard/projects/${project.id}`}
                  className="rounded-xl border border-border bg-card p-4 hover:border-primary/50 transition-colors"
                >
                  <div className="flex items-center justify-between">
                    <h3 className="font-medium truncate">{project.name}</h3>
                    <span
                      className={`text-xs px-2 py-1 rounded-full ${
                        project.status === "SUCCEEDED"
                          ? "bg-emerald-500/10 text-emerald-500"
                          : project.status === "FAILED"
                          ? "bg-destructive/10 text-destructive"
                          : project.status === "PROCESSING"
                          ? "bg-primary/10 text-primary"
                          : "bg-muted text-muted-foreground"
                      }`}
                    >
                      {project.status}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">
                    {project.versions[0] ? `v${project.versions[0].version}` : "No versions"} •{" "}
                    {project.createdAt.toLocaleDateString()}
                  </p>
                </a>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
