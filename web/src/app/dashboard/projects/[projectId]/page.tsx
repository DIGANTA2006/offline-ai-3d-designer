import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Box, Download, FileText, RefreshCw, ShieldCheck } from "lucide-react";
import { requireUser } from "@/lib/auth/server";
import { prisma } from "@/lib/prisma";
import { Button } from "@/components/ui/button";
import { DrawingProcessor } from "@/components/projects/drawing-processor";
import { SlicePanel } from "@/components/projects/slice-panel";
import { PrintabilityPanel } from "@/components/projects/printability-panel";
import { ProjectImportanceToggle, ProjectVersionActions } from "@/components/projects/project-retention-controls";
import { ProjectDeleteButton } from "@/components/projects/project-delete-button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ projectId: string }> };

export default async function ProjectDetailPage({ params }: Props) {
  const { projectId } = await params;
  const user = await requireUser();
  const project = await prisma.project.findFirst({
    where: { id: projectId, userId: user.id },
    include: {
      versions: {
        orderBy: [{ version: "desc" }, { createdAt: "desc" }],
        select: {
          id: true, version: true, createdAt: true, isProtected: true,
          stepFilePath: true, stlFilePath: true, glbFilePath: true,
        },
      },
    },
  });
  if (!project) notFound();
  const versions = project.versions;
  const generatedVersions = versions.filter((item) => item.stepFilePath || item.stlFilePath || item.glbFilePath);
  const latestVersionData = await prisma.projectVersion.findFirst({
    where: { projectId: project.id },
    orderBy: [{ version: "desc" }, { createdAt: "desc" }],
    select: { spec: true },
  });
  const storedVersionSpec = latestVersionData?.spec && typeof latestVersionData.spec === "object" && !Array.isArray(latestVersionData.spec)
    ? latestVersionData.spec as Record<string, unknown>
    : undefined;
  const rawSourceFiles = storedVersionSpec?.uploadedFiles;
  const rawOcrResults = Array.isArray(storedVersionSpec?.ocrResults) ? storedVersionSpec.ocrResults : [];
  const sourceFiles = Array.isArray(rawSourceFiles)
    ? rawSourceFiles.flatMap((item, index) => {
        if (!item || typeof item !== "object" || Array.isArray(item)) return [];
        const record = item as Record<string, unknown>;
        const name = record.name;
        if (typeof name !== "string") return [];
        const saved = rawOcrResults.find((candidate) =>
          !!candidate && typeof candidate === "object" && !Array.isArray(candidate)
          && (candidate as Record<string, unknown>).fileIndex === index
          && !!(candidate as Record<string, unknown>).spec
          && typeof (candidate as Record<string, unknown>).spec === "object"
          && !Array.isArray((candidate as Record<string, unknown>).spec)
        ) as Record<string, unknown> | undefined;
        return [{
          index,
          name,
          type: typeof record.type === "string" ? record.type : undefined,
          contentType: typeof record.contentType === "string" ? record.contentType : undefined,
          ocrResult: saved?.spec ? saved.spec as {
            rawText?: string;
            confidence?: number;
            confidenceMethod?: string;
            pageCount?: number;
            dimensions?: { triplets?: Array<{ valuesMm?: number[]; raw?: string }>; linear?: Array<{ valueMm?: number; raw?: string }>; diameters?: Array<{ value?: number; unit?: string; raw?: string }>; radii?: Array<{ value?: number; unit?: string; raw?: string }> };
            tolerances?: Array<{ raw?: string }>;
            fits?: string[];
            material?: string | null;
            surfaceFinish?: string | null;
            threads?: string[];
            views?: string[];
            annotations?: Array<{ type: string; text: string }>;
            needsReview?: boolean;
            limitations?: string[];
          } : undefined,
          measurementReviews: Array.isArray(saved?.visualMeasurementReviews)
            ? saved.visualMeasurementReviews as Array<{
                measurementIndex: number;
                decision: "confirmed_reading" | "rejected";
                value?: number | null;
                unit?: string | null;
                featureDescription?: string | null;
                note?: string | null;
              }>
            : [],
        }];
      })
    : [];

  return (
    <main className="min-h-screen bg-background px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-4xl">
        <Link href="/dashboard/projects" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Projects</Link>
        <header className="mt-5 flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-2"><Box className="size-6 text-primary" /><h1 className="text-3xl font-semibold tracking-tight">{project.name}</h1></div><p className="mt-2 text-sm text-muted-foreground">Created {project.createdAt.toLocaleString("en-IN")} · Status: {project.status}</p></div><div className="flex flex-wrap items-center gap-2"><ProjectImportanceToggle projectId={project.id} initialImportant={project.isImportant} /><Button variant="outline" asChild><Link href="/dashboard/projects/new"><RefreshCw className="size-4" /> New generation</Link></Button><ProjectDeleteButton projectId={project.id} projectName={project.name} /></div></header>

        <Card className="mt-7"><CardHeader><CardTitle>Input description</CardTitle><CardDescription>Keep this prompt with the exported model so its assumptions are visible.</CardDescription></CardHeader><CardContent><p className="whitespace-pre-wrap text-sm leading-7">{project.description || "No description was saved."}</p></CardContent></Card>

        {sourceFiles.length > 0 && <Card className="mt-5"><CardHeader><CardTitle>Original source files</CardTitle><CardDescription>Files are privately stored and downloads are restricted to your account.</CardDescription></CardHeader><CardContent className="space-y-3">{sourceFiles.map((file) => <a key={file.index} href={`/api/projects/${project.id}/files/source/${file.index}`} className="flex items-center gap-3 rounded-xl border border-border p-4 hover:border-primary/50"><Download className="size-5 text-primary" /><span className="truncate text-sm font-medium">{file.name}</span></a>)}</CardContent></Card>}
        {sourceFiles.length > 0 && <DrawingProcessor projectId={project.id} sourceFiles={sourceFiles} />}

        {generatedVersions.length > 0 ? (
          <Card className="mt-5">
            <CardHeader>
              <CardTitle>Generated exports</CardTitle>
              <CardDescription>{generatedVersions.length} retained output version(s). The two newest unprotected versions are kept automatically; protected versions remain until you delete them.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {generatedVersions.map((output) => (
                <section key={output.id} className="rounded-xl border border-border p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <h3 className="font-semibold">Version {output.version}</h3>
                      <p className="mt-1 text-xs text-muted-foreground">Generated {output.createdAt.toLocaleString("en-IN")}</p>
                      {output.isProtected && <p className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary"><ShieldCheck className="size-3.5" /> Protected from automatic deletion</p>}
                    </div>
                    <ProjectVersionActions projectId={project.id} versionId={output.id} versionNumber={output.version} initialProtected={output.isProtected} />
                  </div>
                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    {output.stepFilePath && <a href={`/api/projects/${project.id}/files/step?versionId=${encodeURIComponent(output.id)}`} className="flex items-center gap-3 rounded-xl border border-border p-3 hover:border-primary/50"><Download className="size-5 text-primary" /><span><span className="block font-semibold">STEP file</span><span className="mt-1 block text-xs text-muted-foreground">CAD interchange format</span></span></a>}
                    {output.stlFilePath && <a href={`/api/projects/${project.id}/files/stl?versionId=${encodeURIComponent(output.id)}`} className="flex items-center gap-3 rounded-xl border border-border p-3 hover:border-primary/50"><Download className="size-5 text-primary" /><span><span className="block font-semibold">STL file</span><span className="mt-1 block text-xs text-muted-foreground">3D printing mesh</span></span></a>}
                  </div>
                </section>
              ))}
            </CardContent>
          </Card>
        ) : project.status === "FAILED" ? (
          <Card className="mt-5 border-destructive/30"><CardHeader><CardTitle className="text-destructive">Generation failed</CardTitle><CardDescription>No successful export was stored. Review the description or check the deployment&apos;s CAD service logs.</CardDescription></CardHeader><CardContent><Button asChild><Link href="/dashboard/projects/new">Try again</Link></Button></CardContent></Card>
        ) : (
          <Card className="mt-5"><CardHeader><CardTitle>Project files</CardTitle><CardDescription>This project has not generated CAD exports yet.</CardDescription></CardHeader><CardContent><div className="flex items-start gap-3 text-sm leading-6 text-muted-foreground"><FileText className="mt-1 size-5 shrink-0" /> Upload a source drawing and use the OCR panel above to extract and review its text. CAD generation remains limited to supported, fully dimensioned descriptions.</div></CardContent></Card>
        )}
        {generatedVersions.some((output) => output.stepFilePath || output.stlFilePath) && (
          <PrintabilityPanel
            projectId={project.id}
            versions={generatedVersions
              .filter((output) => output.stepFilePath || output.stlFilePath)
              .map((output) => ({ id: output.id, version: output.version }))}
          />
        )}
        {generatedVersions.some((output) => output.stlFilePath) && (
          <SlicePanel
            projectId={project.id}
            versions={generatedVersions.filter((output) => output.stlFilePath).map((output) => ({ id: output.id, version: output.version }))}
          />
        )}
      </div>
    </main>
  );
}
