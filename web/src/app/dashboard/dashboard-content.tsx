import Link from "next/link";
import {
  ArrowRight,
  Box,
  Clock3,
  CreditCard,
  FileUp,
  FolderKanban,
  LayoutDashboard,
  Plus,
  Ruler,
  Settings2,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ThemeToggle } from "@/components/theme-toggle";
import { SignOutButton } from "@/components/sign-out-button";

type ProjectPreview = {
  id: string;
  name: string;
  status: "DRAFT" | "QUEUED" | "PROCESSING" | "SUCCEEDED" | "FAILED";
  updatedAt: Date;
};

type DashboardProps = {
  user: { displayName: string | null; email: string | null; role: "USER" | "ADMIN" };
  projects: ProjectPreview[];
  stats: { totalProjects: number; activeJobs: number; completedProjects: number };
};

function statusClass(status: ProjectPreview["status"]): string {
  if (status === "SUCCEEDED") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300";
  if (status === "FAILED") return "border-destructive/30 bg-destructive/10 text-destructive";
  if (status === "PROCESSING" || status === "QUEUED") return "border-primary/30 bg-primary/10 text-primary";
  return "border-border bg-muted text-muted-foreground";
}

export default function DashboardContent({ user, projects, stats }: DashboardProps) {
  return (
    <main className="min-h-screen bg-background">
      <div className="flex min-h-screen">
        <aside className="hidden w-64 shrink-0 flex-col border-r border-border bg-card/50 p-5 lg:flex">
          <Link href="/" className="flex items-center gap-3 font-semibold tracking-tight">
            <span className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground"><Box className="size-5" /></span>
            <span className="leading-tight">Offline AI<br /><span className="text-muted-foreground">3D Designer</span></span>
          </Link>
          <p className="mb-3 mt-10 px-3 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Workspace</p>
          <nav className="space-y-1">
            <Link href="/dashboard" className="flex items-center gap-3 rounded-xl bg-primary/10 px-3 py-2.5 text-sm font-medium text-primary"><LayoutDashboard className="size-4" /> Overview</Link>
            <Link href="/dashboard/projects" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"><FolderKanban className="size-4" /> Projects</Link>
            <Link href="/dashboard/projects" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"><Workflow className="size-4" /> CAD jobs</Link>
            <Link href="/dashboard/fit-check" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"><Ruler className="size-4" /> Hardware fit check</Link>
          </nav>
          <p className="mb-3 mt-8 px-3 text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">Account</p>
          <nav className="space-y-1">
            <Link href="/profile" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"><Settings2 className="size-4" /> Profile & settings</Link>
            {user.role === "ADMIN" && <Link href="/admin" className="flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"><ShieldCheck className="size-4" /> Admin panel</Link>}
          </nav>
          <div className="mt-auto rounded-2xl border border-border bg-background p-4">
            <p className="text-sm font-semibold">CAD workspace</p>
            <p className="mt-2 text-xs leading-5 text-muted-foreground">Text-to-CAD and reviewable drawing OCR are available for supported inputs. General single-image-to-parametric-CAD reconstruction remains unsupported.</p>
          </div>
        </aside>

        <section className="min-w-0 flex-1">
          <header className="flex items-center justify-between border-b border-border px-5 py-4 sm:px-8">
            <div>
              <p className="text-sm text-muted-foreground">Workspace / Overview</p>
              <h1 className="mt-1 text-xl font-semibold tracking-tight">Engineering dashboard</h1>
            </div>
            <div className="flex items-center gap-2">
              <ThemeToggle />
              <span className="hidden max-w-48 truncate text-sm text-muted-foreground xl:inline">{user.displayName ?? user.email ?? "Signed in"}</span>
              <Button variant="outline" asChild><Link href="/dashboard/billing"><CreditCard className="mr-1 size-4" /> Billing & plan</Link></Button>
              <Button variant="outline" asChild><Link href="/profile">Profile</Link></Button>
              {user.role === "ADMIN" && <Button variant="outline" asChild><Link href="/admin">Admin</Link></Button>}
              <SignOutButton />
            </div>
          </header>

          <div className="mx-auto max-w-7xl space-y-8 p-5 sm:p-8">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
              <div>
                <div className="inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1.5 text-xs font-medium text-primary"><Sparkles className="size-3.5" /> CAD workspace</div>
                <h2 className="mt-4 text-3xl font-semibold tracking-tight">Build your next part.</h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">Describe a dimensioned part to generate STEP and STL files through the configured Python CAD engine. Review every output before manufacturing.</p>
              </div>
              <Button asChild><Link href="/dashboard/projects/new"><Plus className="size-4" /> New project <ArrowRight className="size-4" /></Link></Button>
            </div>

            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Projects" value={String(stats.totalProjects)} detail="Your saved workspaces" icon={<FolderKanban className="size-4 text-primary" />} />
              <StatCard label="Active CAD jobs" value={String(stats.activeJobs)} detail="Queued or processing" icon={<Clock3 className="size-4 text-primary" />} />
              <StatCard label="Generated projects" value={String(stats.completedProjects)} detail="STEP/STL generation completed" icon={<Box className="size-4 text-primary" />} />
              <StatCard label="Create a part" value="Text → CAD" detail="Dimensioned descriptions" icon={<Sparkles className="size-4 text-primary" />} />
            </div>

            <div className="grid gap-5 xl:grid-cols-[1.4fr_0.6fr]">
              <Card>
                <CardHeader className="flex-row items-center justify-between gap-4">
                  <div><CardTitle>Recent projects</CardTitle><p className="mt-1 text-sm text-muted-foreground">Only projects actually saved to your account are shown.</p></div>
                  <Button variant="outline" size="sm" asChild><Link href="/dashboard/projects">View all</Link></Button>
                </CardHeader>
                <CardContent className="space-y-3">
                  {projects.map((project) => (
                    <Link key={project.id} href={`/dashboard/projects/${project.id}`} className="flex items-center justify-between gap-4 rounded-xl border border-border bg-background/60 p-4 transition-colors hover:border-primary/50">
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-secondary text-muted-foreground"><Box className="size-5" /></span>
                        <div className="min-w-0"><p className="truncate text-sm font-semibold">{project.name}</p><p className="mt-1 truncate text-xs text-muted-foreground">Updated {project.updatedAt.toLocaleDateString("en-IN")}</p></div>
                      </div>
                      <span className={`shrink-0 rounded-full border px-2.5 py-1 text-xs ${statusClass(project.status)}`}>{project.status}</span>
                    </Link>
                  ))}
                  {projects.length === 0 && <div className="rounded-xl border border-dashed border-border p-8 text-center"><Box className="mx-auto size-8 text-muted-foreground" /><p className="mt-3 font-medium">No projects yet</p><p className="mt-1 text-sm text-muted-foreground">Create your first dimensioned part to start a real CAD job.</p><Button asChild className="mt-4"><Link href="/dashboard/projects/new">Create project</Link></Button></div>}
                </CardContent>
              </Card>

              <Card>
                <CardHeader><CardTitle>Start a workflow</CardTitle><p className="text-sm text-muted-foreground">Choose an implemented action.</p></CardHeader>
                <CardContent className="space-y-3">
                  <div className="rounded-xl border border-border bg-background/60 p-4">
                    <Sparkles className="size-5 text-primary" />
                    <p className="mt-3 text-sm font-semibold">Describe a part</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">Create a project, generate geometry, and save STEP/STL exports.</p>
                    <Button className="mt-4 w-full" asChild><Link href="/dashboard/projects/new">New project</Link></Button>
                  </div>
                  <div className="rounded-xl border border-border bg-background/60 p-4">
                    <FileUp className="size-5 text-primary" />
                    <p className="mt-3 text-sm font-semibold">Store an engineering drawing</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">Extract drawing text and review a structured blueprint. Only supported, confirmed dimensions can be used for generation.</p>
                    <Button className="mt-4 w-full" variant="outline" asChild><Link href="/dashboard/upload">Upload drawing</Link></Button>
                  </div>
                  <div className="rounded-xl border border-border bg-background/60 p-4">
                    <Ruler className="size-5 text-primary" />
                    <p className="mt-3 text-sm font-semibold">Check component fit</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">Compare a confirmed hardware preset with usable enclosure dimensions and review shortfalls.</p>
                    <Button className="mt-4 w-full" variant="outline" asChild><Link href="/dashboard/fit-check">Open fit checker</Link></Button>
                  </div>
                </CardContent>
              </Card>
            </div>

            <div className="flex items-start gap-3 rounded-2xl border border-border bg-card p-4 text-sm leading-6 text-muted-foreground">
              <Workflow className="mt-0.5 size-5 shrink-0 text-primary" />
              <p><strong className="text-foreground">Engineering safety:</strong> this MVP supports the primitives and dimensions understood by the configured parser. Inspect the model, units, features, and exports; generated geometry is not a substitute for professional design review.</p>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

function StatCard({ label, value, detail, icon }: { label: string; value: string; detail: string; icon: ReactNode }) {
  return <Card><CardContent className="p-5"><div className="flex items-center justify-between"><span className="text-sm text-muted-foreground">{label}</span>{icon}</div><p className="mt-4 text-xl font-semibold">{value}</p><p className="mt-1 text-xs text-muted-foreground">{detail}</p></CardContent></Card>;
}
