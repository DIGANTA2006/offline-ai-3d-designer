import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Box, Download, FileText, RefreshCw } from "lucide-react";
import { requireUser } from "@/lib/auth/server";
import { prisma } from "@/lib/prisma";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ projectId: string }> };

export default async function ProjectDetailPage({ params }: Props) {
  const { projectId } = await params;
  const user = await requireUser();
  const project = await prisma.project.findFirst({
    where: { id: projectId, userId: user.id },
    include: { versions: { orderBy: { version: "desc" }, take: 1 } },
  });
  if (!project) notFound();
  const version = project.versions[0] ?? null;
  const rawSourceFiles = version?.spec && typeof version.spec === "object" && !Array.isArray(version.spec)
    ? (version.spec as Record<string, unknown>).uploadedFiles
    : undefined;
  const sourceFiles = Array.isArray(rawSourceFiles)
    ? rawSourceFiles.flatMap((item, index) => {
        if (!item || typeof item !== "object" || Array.isArray(item)) return [];
        const name = (item as Record<string, unknown>).name;
        return typeof name === "string" ? [{ index, name }] : [];
      })
    : [];

  const versionSpec = version?.spec && typeof version.spec === "object" && !Array.isArray(version.spec)
    ? version.spec as Record<string, unknown>
    : {};
  const ocrResultValue = versionSpec.ocrResult;
  const ocrResult = ocrResultValue && typeof ocrResultValue === "object" && !Array.isArray(ocrResultValue)
    ? ocrResultValue as Record<string, unknown>
    : null;
  const ocrSpecValue = ocrResult?.spec;
  const ocrSpec = ocrSpecValue && typeof ocrSpecValue === "object" && !Array.isArray(ocrSpecValue)
    ? ocrSpecValue as Record<string, unknown>
    : null;
  const ocrDimensionsValue = ocrSpec?.dimensions;
  const ocrDimensions = ocrDimensionsValue && typeof ocrDimensionsValue === "object" && !Array.isArray(ocrDimensionsValue)
    ? ocrDimensionsValue as Record<string, unknown>
    : {};
  const dimensionCandidates = Array.isArray(ocrDimensions.candidates)
    ? ocrDimensions.candidates.flatMap((value) => {
        if (!value || typeof value !== "object" || Array.isArray(value)) return [];
        const item = value as Record<string, unknown>;
        if (typeof item.raw !== "string") return [];
        return [{
          raw: item.raw,
          value: typeof item.value === "number" ? item.value : null,
          unit: typeof item.unit === "string" ? item.unit : "unspecified",
          kind: typeof item.kind === "string" ? item.kind : "dimension",
          tolerance: typeof item.tolerance === "string" ? item.tolerance : null,
        }];
      })
    : [];
  const dimensionTriples = Array.isArray(ocrDimensions.dimensionTriples)
    ? ocrDimensions.dimensionTriples.flatMap((value) => {
        if (!value || typeof value !== "object" || Array.isArray(value)) return [];
        const item = value as Record<string, unknown>;
        const values = item.values;
        if (!Array.isArray(values) || !values.every((entry) => typeof entry === "number")) return [];
        return [{
          values: values as number[],
          unit: typeof item.unit === "string" ? item.unit : "unspecified",
          raw: typeof item.raw === "string" ? item.raw : values.join(" × "),
          interpretation: typeof item.interpretation === "string" ? item.interpretation : "Confirm axis order.",
        }];
      })
    : [];
  const ocrAnnotations = Array.isArray(ocrSpec?.annotations)
    ? ocrSpec.annotations.filter((value): value is string => typeof value === "string")
    : [];
  const ocrRawText = typeof ocrSpec?.rawText === "string" ? ocrSpec.rawText : "";
  const ocrError = typeof ocrResult?.error === "string" ? ocrResult.error : "OCR did not return a result.";
  const ocrSucceeded = ocrResult?.success === true && ocrSpec !== null;
  const rawConfidence = ocrSpec?.confidence;
  const ocrConfidence = typeof rawConfidence === "number" && Number.isFinite(rawConfidence)
    ? Math.round(Math.min(1, Math.max(0, rawConfidence)) * 100)
    : null;
  const ocrSourceFileName = typeof versionSpec.ocrSourceFileName === "string" ? versionSpec.ocrSourceFileName : null;
  const ocrTolerancesValue = ocrSpec?.tolerances;
  const ocrTolerances = ocrTolerancesValue && typeof ocrTolerancesValue === "object" && !Array.isArray(ocrTolerancesValue)
    ? ocrTolerancesValue as Record<string, unknown>
    : {};
  const numericTolerances = Array.isArray(ocrTolerances.numericCandidates)
    ? ocrTolerances.numericCandidates.filter((value): value is string => typeof value === "string")
    : [];
  const fitCandidates = Array.isArray(ocrSpec?.fits)
    ? ocrSpec.fits.filter((value): value is string => typeof value === "string")
    : [];
  const threadCandidates = Array.isArray(ocrSpec?.threads)
    ? ocrSpec.threads.filter((value): value is string => typeof value === "string")
    : [];
  const detectedMaterial = typeof ocrSpec?.material === "string" ? ocrSpec.material : null;
  const detectedSurfaceFinish = typeof ocrSpec?.surfaceFinish === "string" ? ocrSpec.surfaceFinish : null;

  return (
    <main className="min-h-screen bg-background px-4 py-8 sm:px-8">
      <div className="mx-auto max-w-4xl">
        <Link href="/dashboard/projects" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" /> Projects</Link>
        <header className="mt-5 flex flex-wrap items-start justify-between gap-4"><div><div className="flex items-center gap-2"><Box className="size-6 text-primary" /><h1 className="text-3xl font-semibold tracking-tight">{project.name}</h1></div><p className="mt-2 text-sm text-muted-foreground">Created {project.createdAt.toLocaleString("en-IN")} · Status: {project.status}</p></div><Button variant="outline" asChild><Link href="/dashboard/projects/new"><RefreshCw className="size-4" /> New generation</Link></Button></header>

        <Card className="mt-7"><CardHeader><CardTitle>Input description</CardTitle><CardDescription>Keep this prompt with the exported model so its assumptions are visible.</CardDescription></CardHeader><CardContent><p className="whitespace-pre-wrap text-sm leading-7">{project.description || "No description was saved."}</p></CardContent></Card>

        {sourceFiles.length > 0 && <Card className="mt-5"><CardHeader><CardTitle>Original source files</CardTitle><CardDescription>Files are privately stored and downloads are restricted to your account.</CardDescription></CardHeader><CardContent className="space-y-3">{sourceFiles.map((file) => <a key={file.index} href={`/api/projects/${project.id}/files/source/${file.index}`} className="flex items-center gap-3 rounded-xl border border-border p-4 hover:border-primary/50"><Download className="size-5 text-primary" /><span className="truncate text-sm font-medium">{file.name}</span></a>)}</CardContent></Card>}

        {ocrResult && (
          <Card className="mt-5">
            <CardHeader>
              <CardTitle>OCR extraction preview</CardTitle>
              <CardDescription>
                {ocrSourceFileName ? `Source: ${ocrSourceFileName}. ` : ""}
                Extracted text and dimensions are provisional candidates, not verified engineering measurements.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {ocrSucceeded ? (
                <>
                  <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm">
                    OCR completed
                    {ocrConfidence !== null ? ` · ${ocrConfidence}% average OCR character confidence (not measurement accuracy)` : ""}
                  </div>

                  {dimensionTriples.length > 0 && (
                    <section className="space-y-2">
                      <h3 className="font-semibold">Three-number dimension candidates</h3>
                      <div className="space-y-2">
                        {dimensionTriples.map((item, index) => (
                          <div key={index} className="rounded-lg border border-border p-3">
                            <p className="font-mono text-sm">{item.values.join(" × ")} {item.unit !== "unspecified" ? item.unit : ""}</p>
                            <p className="mt-1 text-xs text-muted-foreground">{item.interpretation} · Source text: {item.raw}</p>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {dimensionCandidates.length > 0 && (
                    <section className="space-y-2">
                      <h3 className="font-semibold">Individual dimension candidates</h3>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {dimensionCandidates.slice(0, 100).map((item, index) => (
                          <div key={index} className="rounded-lg border border-border p-3 text-sm">
                            <p className="font-mono">{item.raw}</p>
                            <p className="mt-1 text-xs text-muted-foreground">
                              {item.kind}: {item.value ?? "unparsed"} {item.unit}
                              {item.tolerance ? ` · tolerance ${item.tolerance}` : ""}
                            </p>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {(numericTolerances.length > 0 || fitCandidates.length > 0 || threadCandidates.length > 0 || detectedMaterial || detectedSurfaceFinish) && (
                    <section className="space-y-2">
                      <h3 className="font-semibold">Other annotation candidates</h3>
                      <div className="flex flex-wrap gap-2">
                        {numericTolerances.map((value, index) => <span key={`tol-${index}`} className="rounded-full border border-border px-3 py-1 text-sm">Tolerance: {value}</span>)}
                        {fitCandidates.map((value, index) => <span key={`fit-${index}`} className="rounded-full border border-border px-3 py-1 text-sm">Fit: {value}</span>)}
                        {threadCandidates.map((value, index) => <span key={`thread-${index}`} className="rounded-full border border-border px-3 py-1 text-sm">Thread: {value}</span>)}
                        {detectedMaterial && <span className="rounded-full border border-border px-3 py-1 text-sm">Material candidate: {detectedMaterial}</span>}
                        {detectedSurfaceFinish && <span className="rounded-full border border-border px-3 py-1 text-sm">Surface finish: {detectedSurfaceFinish}</span>}
                      </div>
                    </section>
                  )}

                  {ocrAnnotations.length > 0 && (
                    <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3">
                      <h3 className="font-semibold text-sm">Review warnings</h3>
                      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                        {ocrAnnotations.map((annotation, index) => <li key={index}>{annotation}</li>)}
                      </ul>
                    </div>
                  )}

                  <details className="rounded-xl border border-border p-3">
                    <summary className="cursor-pointer font-semibold text-sm">Show raw OCR text</summary>
                    <pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs leading-5">{ocrRawText || "No text was recognized."}</pre>
                  </details>
                </>
              ) : (
                <div role="status" className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 text-sm">
                  <p className="font-semibold">OCR was not completed</p>
                  <p className="mt-1 text-muted-foreground">{ocrError}</p>
                  <p className="mt-2 text-muted-foreground">Your original file remains stored privately. No CAD geometry was generated from this upload.</p>
                </div>
              )}
              <p className="text-sm leading-6 text-muted-foreground">
                Safety note: OCR does not determine an unambiguous 3D shape from a drawing. Verify every dimension, unit, tolerance, fit, datum, and view association against the original. Automatic drawing-to-parametric-CAD generation is not implemented yet. You can use the reviewed text as a starting point in <Link className="underline" href="/dashboard/projects/new">New text-to-CAD project</Link>, but only supported dimensioned shapes will generate.
              </p>
            </CardContent>
          </Card>
        )}

        {project.status === "SUCCEEDED" && version ? (
          <Card className="mt-5"><CardHeader><CardTitle>Generated exports</CardTitle><CardDescription>Version {version.version} · Download links are authenticated and limited to your account.</CardDescription></CardHeader><CardContent className="grid gap-3 sm:grid-cols-2">
            {version.stepFilePath && <a href={`/api/projects/${project.id}/files/step`} className="flex items-center gap-3 rounded-xl border border-border p-4 hover:border-primary/50"><Download className="size-5 text-primary" /><span><span className="block font-semibold">STEP file</span><span className="mt-1 block text-xs text-muted-foreground">CAD interchange format</span></span></a>}
            {version.stlFilePath && <a href={`/api/projects/${project.id}/files/stl`} className="flex items-center gap-3 rounded-xl border border-border p-4 hover:border-primary/50"><Download className="size-5 text-primary" /><span><span className="block font-semibold">STL file</span><span className="mt-1 block text-xs text-muted-foreground">3D printing mesh</span></span></a>}
            {!version.stepFilePath && !version.stlFilePath && <p className="text-sm text-muted-foreground">This version has no generated CAD exports.</p>}
          </CardContent></Card>
        ) : project.status === "FAILED" ? (
          <Card className="mt-5 border-destructive/30"><CardHeader><CardTitle className="text-destructive">Generation failed</CardTitle><CardDescription>No successful export was stored. Review the description or check the deployment&apos;s CAD service logs.</CardDescription></CardHeader><CardContent><Button asChild><Link href="/dashboard/projects/new">Try again</Link></Button></CardContent></Card>
        ) : (
          <Card className="mt-5"><CardHeader><CardTitle>Project files</CardTitle><CardDescription>This project has not generated CAD exports yet.</CardDescription></CardHeader><CardContent><div className="flex items-start gap-3 text-sm leading-6 text-muted-foreground"><FileText className="mt-1 size-5 shrink-0" /> This upload has not generated CAD exports. Review the OCR candidates above if available, or use New Project for supported dimensioned text-to-CAD. Automatic drawing-to-parametric-CAD generation is still incomplete.</div></CardContent></Card>
        )}
      </div>
    </main>
  );
}
