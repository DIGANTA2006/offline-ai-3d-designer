"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FileSearch, LoaderCircle, ShieldCheck, WandSparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type OCRSpec = {
  dimensions?: {
    triplets?: Array<{ valuesMm?: number[]; raw?: string }>;
    linear?: Array<{ valueMm?: number; raw?: string }>;
    diameters?: Array<{ value?: number; unit?: string; raw?: string }>;
    radii?: Array<{ value?: number; unit?: string; raw?: string }>;
  };
  tolerances?: Array<{ raw?: string }>;
  fits?: string[];
  material?: string | null;
  surfaceFinish?: string | null;
  threads?: string[];
  views?: string[];
  annotations?: Array<{ type: string; text: string }>;
  confidence?: number;
  rawText?: string;
  pageCount?: number;
  needsReview?: boolean;
  limitations?: string[];
};

type SourceFile = { index: number; name: string; ocrResult?: OCRSpec };
type Props = { projectId: string; sourceFiles: SourceFile[] };

export function DrawingProcessor({ projectId, sourceFiles }: Props) {
  const router = useRouter();
  const [selectedIndex, setSelectedIndex] = useState<number>(sourceFiles[0]?.index ?? 0);
  const [results, setResults] = useState<Record<number, OCRSpec>>(() => Object.fromEntries(
    sourceFiles.flatMap((file) => file.ocrResult ? [[file.index, file.ocrResult]] : []),
  ));
  const [reviewedDescription, setReviewedDescription] = useState(
    sourceFiles[0]?.ocrResult?.rawText ?? "",
  );
  const [analyzing, setAnalyzing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const selected = useMemo(() => sourceFiles.find((file) => file.index === selectedIndex), [sourceFiles, selectedIndex]);
  const currentResult = results[selectedIndex] ?? null;

  function changeSource(value: string) {
    const index = Number(value);
    setSelectedIndex(index);
    setReviewedDescription(results[index]?.rawText ?? "");
    setError("");
    setNotice("");
  }

  async function analyze() {
    if (!selected) return;
    setAnalyzing(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/ocr`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fileIndex: selected.index }),
      });
      const payload = await response.json().catch(() => ({})) as { error?: string; spec?: OCRSpec; needsReview?: boolean };
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (response.status === 402) {
        throw new Error("Drawing OCR requires an active Pro subscription or administrator access.");
      }
      if (!response.ok || !payload.spec) throw new Error(payload.error ?? `Drawing OCR failed (HTTP ${response.status}).`);
      setResults((previous) => ({ ...previous, [selected.index]: payload.spec! }));
      setReviewedDescription(payload.spec.rawText ?? "");
      setNotice("Text extracted. Review every dimension and edit the part description before generating CAD.");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Drawing OCR failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  async function generate() {
    if (!selected || !currentResult) return;
    if (reviewedDescription.trim().length < 5) {
      setError("Enter a reviewed dimensioned part description before generating CAD.");
      return;
    }
    setGenerating(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/generate-from-drawing`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fileIndex: selected.index,
          reviewed: true,
          reviewedDescription: reviewedDescription.trim(),
        }),
      });
      const payload = await response.json().catch(() => ({})) as { error?: string; ok?: boolean; version?: number; message?: string };
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (response.status === 402) {
        throw new Error("Generating CAD requires an active Pro subscription or administrator access.");
      }
      if (!response.ok || !payload.ok) throw new Error(payload.error ?? `CAD generation failed (HTTP ${response.status}).`);
      setNotice(`CAD exports saved as project version ${payload.version ?? "new"}. The result is approximate; compare it against the original drawing.`);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Drawing-to-CAD generation failed.");
    } finally {
      setGenerating(false);
    }
  }

  if (!sourceFiles.length) return null;

  return (
    <Card className="mt-5">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><FileSearch className="size-5 text-primary" />Drawing OCR and reviewed CAD generation</CardTitle>
        <CardDescription>OCR extracts visible text and recognizable annotations. It cannot determine every hidden surface or guarantee engineering accuracy; review all values before generating a model.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="space-y-2">
          <label htmlFor="drawing-source" className="text-sm font-medium">Source drawing</label>
          <select id="drawing-source" value={selectedIndex} onChange={(event) => changeSource(event.target.value)} disabled={analyzing || generating} className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm">
            {sourceFiles.map((file) => <option key={file.index} value={file.index}>{file.name}</option>)}
          </select>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={analyze} disabled={analyzing || generating}>
              {analyzing ? <><LoaderCircle className="size-4 animate-spin" /> Analyzing drawing…</> : <><FileSearch className="size-4" /> {currentResult ? "Analyze again" : "Extract drawing text"}</>}
            </Button>
            <Button type="button" onClick={generate} disabled={!currentResult || analyzing || generating || reviewedDescription.trim().length < 5}>
              {generating ? <><LoaderCircle className="size-4 animate-spin" /> Generating CAD…</> : <><WandSparkles className="size-4" /> Generate reviewed STEP + STL</>}
            </Button>
          </div>
        </div>

        {currentResult && (
          <div className="space-y-3 rounded-xl border border-border p-4">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <ShieldCheck className="size-4 text-primary" />
              <span className="font-medium">OCR extraction completed</span>
              <span className="text-muted-foreground">· {Math.round((currentResult.confidence ?? 0) * 100)}% OCR word confidence · {currentResult.pageCount ?? 1} page(s)</span>
            </div>
            <p className="text-xs leading-5 text-muted-foreground">OCR confidence is not dimension accuracy. Verify units, decimal points, diameter/radius symbols, tolerances, fits, threads and every view against the source.</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg bg-muted/40 p-3 text-sm"><span className="font-medium">Dimension triplets</span><p className="mt-1 text-muted-foreground">{(currentResult.dimensions?.triplets ?? []).map((item) => item.raw ?? (item.valuesMm ?? []).join(" × ")).join("; ") || "None recognized"}</p></div>
              <div className="rounded-lg bg-muted/40 p-3 text-sm"><span className="font-medium">Diameters / radii</span><p className="mt-1 text-muted-foreground">{[...(currentResult.dimensions?.diameters ?? []), ...(currentResult.dimensions?.radii ?? [])].map((item) => item.raw).filter(Boolean).join("; ") || "None recognized"}</p></div>
              <div className="rounded-lg bg-muted/40 p-3 text-sm"><span className="font-medium">Tolerances and fits</span><p className="mt-1 text-muted-foreground">{[...(currentResult.tolerances ?? []).map((item) => item.raw ?? ""), ...(currentResult.fits ?? [])].filter(Boolean).join("; ") || "None recognized"}</p></div>
              <div className="rounded-lg bg-muted/40 p-3 text-sm"><span className="font-medium">Threads / material / finish</span><p className="mt-1 text-muted-foreground">{[...(currentResult.threads ?? []), currentResult.material ?? "", currentResult.surfaceFinish ?? ""].filter(Boolean).join("; ") || "None recognized"}</p></div>
            </div>
            <div className="space-y-2">
              <label htmlFor="reviewed-cad-description" className="text-sm font-medium">Review/edit the part description</label>
              <textarea id="reviewed-cad-description" value={reviewedDescription} onChange={(event) => setReviewedDescription(event.target.value)} maxLength={4000} rows={6} disabled={analyzing || generating} className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" placeholder="Rewrite the OCR result into a clear description with all required dimensions and an explicit shape." />
              <p className="text-xs leading-5 text-muted-foreground">Only supported, fully dimensioned primitive descriptions are currently converted to CAD. If the text is ambiguous or lacks dimensions, generation returns an error rather than inventing the missing geometry.</p>
            </div>
          </div>
        )}

        {error && <div role="alert" className="rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}{error.includes("Pro subscription") && <Link href="/dashboard/billing" className="mt-2 block font-semibold underline">View Pro plan and subscribe</Link>}</div>}
        {notice && <div role="status" className="rounded-xl border border-primary/20 bg-primary/5 p-3 text-sm leading-6">{notice}</div>}
      </CardContent>
    </Card>
  );
}
