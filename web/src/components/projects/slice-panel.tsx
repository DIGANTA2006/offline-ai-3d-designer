"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Layers, LoaderCircle, Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type SliceVersion = { id: string; version: number };
type Capability = { loading: boolean; available: boolean; engine: string | null; reason: string };
type Estimate = {
  printTimeSeconds: number | null;
  filamentGrams: number | null;
  filamentMeters: number | null;
  layers: number | null;
  massEstimated: boolean;
};

const initialEstimate: Estimate = {
  printTimeSeconds: null,
  filamentGrams: null,
  filamentMeters: null,
  layers: null,
  massEstimated: false,
};

function finiteHeader(value: string | null): number | null {
  if (value === null || value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null) return "Not reported by slicer";
  const rounded = Math.round(seconds);
  const hours = Math.floor(rounded / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const remainder = rounded % 60;
  if (hours > 0) return hours + "h " + minutes + "m";
  if (minutes > 0) return minutes + "m " + remainder + "s";
  return remainder + "s";
}

export function SlicePanel({ projectId, versions }: { projectId: string; versions: SliceVersion[] }) {
  const [selectedVersionId, setSelectedVersionId] = useState(versions[0]?.id ?? "");
  const [layerHeight, setLayerHeight] = useState("0.2");
  const [wallThickness, setWallThickness] = useState("1.2");
  const [infillDensity, setInfillDensity] = useState("20");
  const [supportEnabled, setSupportEnabled] = useState(false);
  const [capability, setCapability] = useState<Capability>({
    loading: true,
    available: false,
    engine: null,
    reason: "Checking the connected CAD backend.",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [estimate, setEstimate] = useState<Estimate>(initialEstimate);

  useEffect(() => {
    let active = true;
    fetch("/api/projects/" + encodeURIComponent(projectId) + "/slice", {
      method: "GET",
      credentials: "same-origin",
      cache: "no-store",
    }).then(async (response) => {
      const payload = await response.json().catch(() => null) as Record<string, unknown> | null;
      if (!active) return;
      if (!response.ok) {
        setCapability({
          loading: false,
          available: false,
          engine: null,
          reason: typeof payload?.reason === "string" ? payload.reason : "Could not check slicing access or backend readiness.",
        });
        return;
      }
      setCapability({
        loading: false,
        available: payload?.available === true,
        engine: typeof payload?.engine === "string" ? payload.engine : null,
        reason: typeof payload?.reason === "string" ? payload.reason : "No additional capability details were reported.",
      });
    }).catch(() => {
      if (!active) return;
      setCapability({
        loading: false,
        available: false,
        engine: null,
        reason: "Could not reach the project's slicing status endpoint.",
      });
    });
    return () => { active = false; };
  }, [projectId]);

  async function slice() {
    setBusy(true);
    setError("");
    setNotice("");
    setEstimate(initialEstimate);
    try {
      const response = await fetch("/api/projects/" + encodeURIComponent(projectId) + "/slice", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          versionId: selectedVersionId,
          settings: {
            layerHeight: Number(layerHeight),
            wallThickness: Number(wallThickness),
            infillDensity: Number(infillDensity),
            supportEnabled,
          },
        }),
      });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as Record<string, unknown> | null;
        throw new Error(typeof payload?.error === "string" ? payload.error : "Slicing failed. Check backend readiness and logs.");
      }

      const gcode = await response.blob();
      if (gcode.size === 0) throw new Error("The slicer returned an empty G-code file.");
      const objectUrl = URL.createObjectURL(gcode);
      const anchor = document.createElement("a");
      const versionNumber = versions.find((item) => item.id === selectedVersionId)?.version ?? "export";
      anchor.href = objectUrl;
      anchor.download = "project-v" + versionNumber + ".gcode";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);

      setEstimate({
        printTimeSeconds: finiteHeader(response.headers.get("x-slice-print-time-seconds")),
        filamentGrams: finiteHeader(response.headers.get("x-slice-filament-grams")),
        filamentMeters: finiteHeader(response.headers.get("x-slice-filament-meters")),
        layers: finiteHeader(response.headers.get("x-slice-layers")),
        massEstimated: response.headers.get("x-slice-filament-grams-estimated") === "true",
      });
      const engine = response.headers.get("x-slice-engine") || "configured slicer";
      setNotice("Validated G-code generated by " + engine + " and downloaded. Estimates come from slicer output; filament mass may be approximate.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Slicing failed unexpectedly.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="mt-5">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Printer className="size-5 text-primary" />
          <CardTitle>Slice STL / 3D Print Prep</CardTitle>
        </div>
        <CardDescription>
          Generate printer G-code from a retained STL. Estimates are sourced from the configured slicer rather than guessed by the web app.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {capability.loading ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircle className="size-4 animate-spin" /> Checking CuraEngine and printer profile availability…
          </p>
        ) : capability.available ? (
          <p className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400">
            <CheckCircle2 className="size-4" /> {capability.engine || "Slicer"} is configured and reported ready.
          </p>
        ) : (
          <div className="flex items-start gap-2 rounded-xl border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" />
            <div>
              <p className="font-medium">Slicing is not available on the connected backend.</p>
              <p className="mt-1 text-muted-foreground">{capability.reason}</p>
              <p className="mt-2 text-muted-foreground">
                Readiness requires CuraEngine and a compatible Cura printer/extruder definition. No placeholder G-code will be generated.
              </p>
            </div>
          </div>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <label className="space-y-1.5 text-sm">
            <span className="font-medium">STL export version</span>
            <select
              value={selectedVersionId}
              onChange={(event) => setSelectedVersionId(event.target.value)}
              className="h-10 w-full rounded-xl border border-input bg-background px-3"
              disabled={busy}
            >
              {versions.map((version) => (
                <option key={version.id} value={version.id}>Version {version.version}</option>
              ))}
            </select>
          </label>
          <label className="space-y-1.5 text-sm">
            <span className="font-medium">Layer height (mm)</span>
            <input
              type="number" min="0.05" max="1" step="0.05" value={layerHeight}
              onChange={(event) => setLayerHeight(event.target.value)}
              className="h-10 w-full rounded-xl border border-input bg-background px-3"
              disabled={busy}
            />
          </label>
          <label className="space-y-1.5 text-sm">
            <span className="font-medium">Wall thickness (mm)</span>
            <input
              type="number" min="0.4" max="40" step="0.2" value={wallThickness}
              onChange={(event) => setWallThickness(event.target.value)}
              className="h-10 w-full rounded-xl border border-input bg-background px-3"
              disabled={busy}
            />
          </label>
          <label className="space-y-1.5 text-sm">
            <span className="font-medium">Infill (%)</span>
            <input
              type="number" min="0" max="100" step="5" value={infillDensity}
              onChange={(event) => setInfillDensity(event.target.value)}
              className="h-10 w-full rounded-xl border border-input bg-background px-3"
              disabled={busy}
            />
          </label>
        </div>

        <label className="flex items-center gap-3 text-sm">
          <input
            type="checkbox"
            checked={supportEnabled}
            onChange={(event) => setSupportEnabled(event.target.checked)}
            className="size-4 accent-primary"
            disabled={busy}
          />
          <span>
            <span className="block font-medium">Enable support structures</span>
            <span className="text-muted-foreground">Uses the configured Cura profile's support strategy.</span>
          </span>
        </label>

        <Button onClick={slice} disabled={!capability.available || busy || !selectedVersionId}>
          {busy ? <LoaderCircle className="size-4 animate-spin" /> : <Layers className="size-4" />}
          {busy ? "Slicing STL…" : "Slice STL and download G-code"}
        </Button>

        {error && <p role="alert" className="rounded-xl border border-destructive/40 p-3 text-sm text-destructive">{error}</p>}
        {notice && <p role="status" className="rounded-xl border border-border p-3 text-sm">{notice}</p>}

        {(estimate.printTimeSeconds !== null || estimate.filamentGrams !== null || estimate.filamentMeters !== null || estimate.layers !== null) && (
          <div className="space-y-3 rounded-xl border border-border p-4">
            <h4 className="font-semibold">Slicer estimates</h4>
            <div className="grid gap-3 sm:grid-cols-2">
              <div><p className="text-xs text-muted-foreground">Print time</p><p className="font-medium">{formatDuration(estimate.printTimeSeconds)}</p></div>
              <div>
                <p className="text-xs text-muted-foreground">Filament mass{estimate.massEstimated ? " (approx.)" : ""}</p>
                <p className="font-medium">{estimate.filamentGrams === null ? "Not reported by slicer" : (estimate.massEstimated ? "≈ " : "") + estimate.filamentGrams.toFixed(2) + " g"}</p>
              </div>
              <div><p className="text-xs text-muted-foreground">Filament length</p><p className="font-medium">{estimate.filamentMeters === null ? "Not reported by slicer" : estimate.filamentMeters.toFixed(3) + " m"}</p></div>
              <div><p className="text-xs text-muted-foreground">Layers</p><p className="font-medium">{estimate.layers === null ? "Not reported by slicer" : estimate.layers.toLocaleString()}</p></div>
            </div>
            {estimate.massEstimated && (
              <p className="text-xs text-muted-foreground">
                Mass is calculated from Cura-reported filament length, diameter, and a PLA-like density of 1.24 g/cm³. Verify it against your actual material.
              </p>
            )}
          </div>
        )}
        <p className="text-xs text-muted-foreground">
          Review the G-code in a slicer preview and verify printer model, firmware, temperatures, and start/end G-code before physical printing.
        </p>
      </CardContent>
    </Card>
  );
}
