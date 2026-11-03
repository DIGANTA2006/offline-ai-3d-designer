"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, LoaderCircle, ShieldAlert, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type Version = { id: string; version: number };
type CheckStatus = "pass" | "fail" | "warning" | "skipped";
type Check = {
  check_id: string;
  name: string;
  status: CheckStatus;
  value: number | null;
  threshold: number | null;
  unit: string;
  details: string;
  explanation?: { what?: string; why?: string; fix?: string; learn_more?: string };
  available_fixes?: string[];
};
type Summary = { total: number; pass: number; fail: number; warning: number; skipped: number };
type Report = {
  success: boolean;
  checks: Check[];
  summary: Summary;
  versionId: string;
  versionNumber: number;
  partSpecName: string;
  limitations?: string[];
};
type FixPreview = {
  success: boolean;
  proposalOnly: true;
  result?: {
    action: string;
    check_id: string;
    modified_spec: Record<string, unknown>;
    new_checks: Check[];
  };
  notices?: string[];
  versionNumber: number;
};

const FIX_LABELS: Record<string, string> = {
  rotate: "Check rotated proposal",
  thicken: "Check wall-thickening proposal",
  enlarge: "Check enlargement proposal",
  split: "Review split proposal",
  add_support: "Review support proposal",
};

const STATUS_CLASS: Record<CheckStatus, string> = {
  pass: "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-300",
  fail: "border-red-200 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300",
  warning: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-300",
  skipped: "border-border bg-muted text-muted-foreground",
};

function summarize(checks: Check[]): Summary {
  return {
    total: checks.length,
    pass: checks.filter((check) => check.status === "pass").length,
    fail: checks.filter((check) => check.status === "fail").length,
    warning: checks.filter((check) => check.status === "warning").length,
    skipped: checks.filter((check) => check.status === "skipped").length,
  };
}

function CheckList({ checks, onPreviewFix, busyKey }: {
  checks: Check[];
  onPreviewFix?: (checkId: string, action: string) => void;
  busyKey?: string | null;
}) {
  return (
    <div className="space-y-3">
      {checks.map((check) => (
        <article key={check.check_id} className="rounded-xl border border-border p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <h4 className="font-semibold">{check.name}</h4>
              <p className="mt-1 text-sm text-muted-foreground">{check.details}</p>
              {check.value !== null && check.threshold !== null && (
                <p className="mt-2 text-xs text-muted-foreground">
                  Measured: {check.value} {check.unit} · Threshold: {check.threshold} {check.unit}
                </p>
              )}
            </div>
            <span className={"shrink-0 rounded-full border px-2.5 py-1 text-xs font-semibold uppercase " + STATUS_CLASS[check.status]}>
              {check.status}
            </span>
          </div>

          {check.explanation && (
            <div className="mt-3 space-y-1 border-t border-border pt-3 text-sm">
              {check.explanation.what && <p><strong>Finding:</strong> {check.explanation.what}</p>}
              {check.explanation.why && <p><strong>Why it matters:</strong> {check.explanation.why}</p>}
              {check.explanation.fix && <p><strong>Suggested response:</strong> {check.explanation.fix}</p>}
              {check.explanation.learn_more && <p className="text-muted-foreground">{check.explanation.learn_more}</p>}
            </div>
          )}

          {onPreviewFix && check.available_fixes && check.available_fixes.length > 0 && check.status !== "pass" && check.status !== "skipped" && (
            <div className="mt-3 flex flex-wrap gap-2 border-t border-border pt-3">
              {check.available_fixes.map((action) => {
                const key = check.check_id + ":" + action;
                const isBusy = busyKey === key;
                return (
                  <Button
                    key={action}
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={!!busyKey}
                    onClick={() => onPreviewFix(check.check_id, action)}
                  >
                    {isBusy ? <LoaderCircle className="size-4 animate-spin" /> : <Wrench className="size-4" />}
                    {FIX_LABELS[action] ?? "Preview " + action}
                  </Button>
                );
              })}
            </div>
          )}
        </article>
      ))}
    </div>
  );
}

export function PrintabilityPanel({ projectId, versions }: { projectId: string; versions: Version[] }) {
  const [selectedVersionId, setSelectedVersionId] = useState(versions[0]?.id ?? "");
  const [report, setReport] = useState<Report | null>(null);
  const [preview, setPreview] = useState<FixPreview | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function runChecks() {
    if (!selectedVersionId) return;
    setBusy("check");
    setError("");
    setPreview(null);
    try {
      const response = await fetch(
        "/api/projects/" + encodeURIComponent(projectId) + "/printability?versionId=" + encodeURIComponent(selectedVersionId),
        { method: "GET", credentials: "same-origin", cache: "no-store" },
      );
      const payload = await response.json().catch(() => null) as Report | { error?: string } | null;
      if (!response.ok) throw new Error(payload && "error" in payload && typeof payload.error === "string" ? payload.error : "Printability checks failed.");
      if (!payload || !("checks" in payload) || !Array.isArray(payload.checks)) {
        throw new Error("The printability service returned an invalid report.");
      }
      setReport(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not run printability checks.");
      setReport(null);
    } finally {
      setBusy(null);
    }
  }

  async function previewFix(checkId: string, action: string) {
    if (!selectedVersionId) return;
    const key = checkId + ":" + action;
    setBusy(key);
    setError("");
    setPreview(null);
    try {
      const response = await fetch("/api/projects/" + encodeURIComponent(projectId) + "/printability", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ versionId: selectedVersionId, checkId, action }),
      });
      const payload = await response.json().catch(() => null) as FixPreview | { error?: string } | null;
      if (!response.ok) throw new Error(payload && "error" in payload && typeof payload.error === "string" ? payload.error : "Could not preview this fix.");
      if (!payload || !("result" in payload) || !payload.result || !Array.isArray(payload.result.new_checks)) {
        throw new Error("The printability service returned an invalid fix preview.");
      }
      setPreview(payload);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not preview this fix.");
    } finally {
      setBusy(null);
    }
  }

  const previewChecks = preview?.result?.new_checks ?? [];
  const previewSummary = previewChecks.length > 0 ? summarize(previewChecks) : null;

  return (
    <Card className="mt-5">
      <CardHeader>
        <div className="flex items-center gap-2">
          <ShieldAlert className="size-5 text-primary" />
          <CardTitle>Printability checks</CardTitle>
        </div>
        <CardDescription>
          Run deterministic FDM checks on a saved CAD version. Available actions evaluate a proposed PartSpec change and re-run the checks; they do not render a replacement mesh.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <label className="min-w-56 flex-1 space-y-1.5 text-sm font-medium">
            CAD export version
            <select
              value={selectedVersionId}
              onChange={(event) => {
                setSelectedVersionId(event.target.value);
                setReport(null);
                setPreview(null);
                setError("");
              }}
              className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm font-normal"
              aria-label="CAD export version for printability checks"
            >
              {versions.map((version) => (
                <option key={version.id} value={version.id}>Version {version.version}</option>
              ))}
            </select>
          </label>
          <Button type="button" onClick={runChecks} disabled={!selectedVersionId || !!busy}>
            {busy === "check" ? <LoaderCircle className="size-4 animate-spin" /> : <CheckCircle2 className="size-4" />}
            {busy === "check" ? "Checking…" : "Run printability checks"}
          </Button>
        </div>

        {error && <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">{error}</p>}

        <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <p>Default assumptions include a 220 × 220 × 250 mm build volume and generic FDM thresholds. These checks are guidance, not printer-specific validation or a guarantee of a successful physical print.</p>
        </div>

        {report && (
          <section className="space-y-3" aria-live="polite">
            <div>
              <h3 className="font-semibold">Version {report.versionNumber}: {report.partSpecName}</h3>
              <p className="text-sm text-muted-foreground">
                {report.summary.total} checks · {report.summary.pass} pass · {report.summary.fail} fail · {report.summary.warning} warning · {report.summary.skipped} skipped
              </p>
            </div>
            <CheckList checks={report.checks} onPreviewFix={previewFix} busyKey={busy} />
            {report.limitations?.map((limitation) => (
              <p key={limitation} className="text-xs text-muted-foreground">{limitation}</p>
            ))}
          </section>
        )}

        {preview && (
          <section className="space-y-3 rounded-xl border border-primary/30 p-4" aria-live="polite">
            <div>
              <h3 className="font-semibold">Proposal check results — {preview.result?.action.replaceAll("_", " ")}</h3>
              {previewSummary && (
                <p className="text-sm text-muted-foreground">
                  {previewSummary.total} checks after proposal · {previewSummary.pass} pass · {previewSummary.fail} fail · {previewSummary.warning} warning
                </p>
              )}
            </div>
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
              These results evaluate the proposed PartSpec against the printability checks only. No replacement 3D mesh is rendered, and the saved specification and existing STEP/STL files have not changed.
            </div>
            {preview.notices?.map((notice) => <p key={notice} className="text-sm text-muted-foreground">{notice}</p>)}
            <CheckList checks={previewChecks} />
          </section>
        )}
      </CardContent>
    </Card>
  );
}
