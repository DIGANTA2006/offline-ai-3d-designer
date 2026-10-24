import Link from "next/link";
import { ArrowLeft, ArrowRight, Bookmark, Box, Plus } from "lucide-react";
import { requireUser } from "@/lib/auth/server";
import { prisma } from "@/lib/prisma";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { MAX_ACTIVE_PROJECTS } from "@/lib/project-retention-core";

export const dynamic = "force-dynamic";

const statusStyle: Record<string, string> = {
  DRAFT: "border-border bg-muted text-muted-foreground",
  QUEUED: "border-primary/30 bg-primary/10 text-primary",
  PROCESSING: "border-primary/30 bg-primary/10 text-primary",
  SUCCEEDED: "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300",
  FAILED: "border-destructive/30 bg-destructive/10 text-destructive",
};

export default async function ProjectsPage() {
  const user = await requireUser();
  const projects = await prisma.project.findMany({
    where: { userId: user.id },
    orderBy: { updatedAt: "desc" },
    select: { id: true, name: true, description: true, status: true, isImportant: true, updatedAt: true },
  });

  return (
    <main className="min-h-screen bg-background px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-5xl">
        <header className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <Link href="/dashboard" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Dashboard</Link>
            <h1 className="mt-4 text-3xl font-semibold tracking-tight">My projects</h1>
            <p className="mt-2 text-sm text-muted-foreground">Your saved CAD jobs and drawing uploads.</p><p className="mt-1 text-xs text-muted-foreground">{projects.length} of {MAX_ACTIVE_PROJECTS} saved projects. Important projects are preserved; older unimportant projects may be removed automatically when the limit is reached.</p>
          </div>
          <Button asChild><Link href="/dashboard/projects/new"><Plus className="size-4" /> New project</Link></Button>
        </header>
        <div className="space-y-3">
          {projects.map((project) => (
            <Link key={project.id} href={`/dashboard/projects/${project.id}`} className="block rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary">
              <Card className="transition-colors hover:border-primary/50"><CardContent className="flex flex-wrap items-center justify-between gap-4 p-5">
                <div className="flex min-w-0 items-center gap-3"><span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-secondary text-muted-foreground"><Box className="size-5" /></span><div className="min-w-0"><h2 className="truncate font-semibold">{project.name} {project.isImportant && <span className="inline-flex items-center gap-1 text-xs font-medium text-primary"><Bookmark className="inline size-3.5" /> Important</span>}</h2><p className="mt-1 max-w-2xl truncate text-sm text-muted-foreground">{project.description || "No description"}</p><p className="mt-1 text-xs text-muted-foreground">Updated {project.updatedAt.toLocaleString("en-IN")}</p></div></div>
                <div className="flex items-center gap-3"><span className={`rounded-full border px-2.5 py-1 text-xs ${statusStyle[project.status] ?? statusStyle.DRAFT}`}>{project.status}</span><ArrowRight className="size-4 text-muted-foreground" /></div>
              </CardContent></Card>
            </Link>
          ))}
          {projects.length === 0 && <Card><CardContent className="p-10 text-center"><Box className="mx-auto size-9 text-muted-foreground" /><h2 className="mt-3 font-semibold">No projects found</h2><p className="mt-1 text-sm text-muted-foreground">Create a text-to-CAD project to generate and save your first part.</p><Button asChild className="mt-5"><Link href="/dashboard/projects/new">Create your first project</Link></Button></CardContent></Card>}
        </div>
      </div>
    </main>
  );
}
