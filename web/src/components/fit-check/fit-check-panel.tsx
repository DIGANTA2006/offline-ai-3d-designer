"use client";

import { type FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  ClipboardCheck,
  Ruler,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type HardwarePreset = {
  id: string;
  name: string;
  type: string;
  category: string;
  length_mm: number;
  width_mm: number;
  height_mm: number;
  clearance_mm: number;
  description: string;
  source: string;
  confirmed: boolean;
  vendor: string;
  part_number: string | null;
};

type FitResult = {
  component_id: string;
  component_name: string;
  fits: boolean;
  clearance_mm: Record<string, number>;
  shortfall_mm: Record<string, number>;
  issues: string[];
  warnings: string[];
  suggested_clearance_mm: number;
};

type FitResponse = {
  success: boolean;
  component: { id: string; name: string; width: number; depth: number; height: number };
  enclosure: { interior_width: number; interior_depth: number; interior_height: number; wall_thickness: number };
  report: {
    enclosure_name: string;
    overall_fit: boolean;
    results: FitResult[];
    summary: string;
  };
  limitations: string[];
};

function formatMm(value: number): string {
  return Number.isFinite(value) ? `${value.toFixed(2).replace(/\.00$/, "")} mm` : "—";
}

export function FitCheckPanel() {
  const [presets, setPresets] = useState<HardwarePreset[]>([]);
  const [presetId, setPresetId] = useState("");
  const [presetConfirmed, setPresetConfirmed] = useState(false);
  const [width, setWidth] = useState("40");
  const [length, setLength] = useState("70");
  const [height, setHeight] = useState("30");
  const [wallThickness, setWallThickness] = useState("2");
  const [clearance, setClearance] = useState("1.5");
  const [enclosureConfirmed, setEnclosureConfirmed] = useState(false);
  const [loadingPresets, setLoadingPresets] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<FitResponse | null>(null);

  const selectedPreset = useMemo(
    () => presets.find((item) => item.id === presetId) ?? null,
    [presets, presetId],
  );

  useEffect(() => {
    let cancelled = false;
    async function loadPresets() {
      setLoadingPresets(true);
      setError("");
      try {
        const response = await fetch("/api/cad/fit-check/presets", {
          method: "GET",
          credentials: "same-origin",
          cache: "no-store",
        });
        const payload = await response.json().catch(() => ({})) as {
          presets?: HardwarePreset[];
          detail?: string;
          error?: string;
        };
        if (!response.ok || !Array.isArray(payload.presets)) {
          throw new Error(payload.error ?? payload.detail ?? `Could not load hardware presets (HTTP ${response.status}).`);
        }
        if (!cancelled) {
          setPresets(payload.presets);
          setPresetId((current) => current || payload.presets?.[0]?.id || "");
        }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Could not load hardware presets.");
      } finally {
        if (!cancelled) setLoadingPresets(false);
      }
    }
    void loadPresets();
    return () => { cancelled = true; };
  }, []);

  function useSuggestedDimensions() {
    if (!selectedPreset) return;
    const numericClearance = Number(clearance);
    const numericWall = Number(wallThickness);
    if (!Number.isFinite(numericClearance) || numericClearance < 0) {
      setError("Clearance must be a finite, non-negative number.");
      return;
    }
    if (!Number.isFinite(numericWall) || numericWall <= 0) {
      setError("Wall thickness must be a positive number.");
      return;
    }
    setWidth(String(selectedPreset.width_mm + 2 * numericClearance));
    setLength(String(selectedPreset.length_mm + 2 * numericClearance));
    // Reserve side clearance plus the configured lid allowance; this is a sizing
    // suggestion, not a generated or manufacturing-verified enclosure.
    setHeight(String(selectedPreset.height_mm + 2 * numericClearance + 4));
    setEnclosureConfirmed(false);
    setPresetConfirmed(false);
    setResult(null);
    setError("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setResult(null);

    if (!selectedPreset) {
      setError("Choose a hardware preset first.");
      return;
    }
    const dimensions = [Number(width), Number(length), Number(height), Number(wallThickness), Number(clearance)];
    if (dimensions.some((value) => !Number.isFinite(value))) {
      setError("All dimensions must be finite numbers.");
      return;
    }
    if ([Number(width), Number(length), Number(height)].some((value) => value <= 0)) {
      setError("Interior width, length, and height must be positive.");
      return;
    }
    if (Number(wallThickness) <= 0 || Number(clearance) < 0) {
      setError("Wall thickness must be positive and clearance must be non-negative.");
      return;
    }
    if (!presetConfirmed) {
      setError("Confirm that the preset matches your exact hardware model and revision.");
      return;
    }
    if (!enclosureConfirmed) {
      setError("Confirm the enclosure interior dimensions before checking fit.");
      return;
    }

    setBusy(true);
    try {
      const response = await fetch("/api/cad/fit-check", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          presetId: selectedPreset.id,
          componentConfirmed: true,
          clearanceMm: Number(clearance),
          enclosure: {
            name: "User-specified enclosure",
            interior_width: Number(width),
            interior_depth: Number(length),
            interior_height: Number(height),
            wall_thickness: Number(wallThickness),
            confirmed: true,
          },
        }),
      });
      const payload = await response.json().catch(() => ({})) as FitResponse & { detail?: string; error?: string };
      if (!response.ok || !payload.report) {
        throw new Error(payload.error ?? payload.detail ?? `Fit check failed (HTTP ${response.status}).`);
      }
      setResult(payload);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Fit check failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const currentResult = result?.report.results[0];

  return (
    <div className="space-y-7">
      <header>
        <Link href="/dashboard" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" /> Dashboard
        </Link>
        <div className="mt-5 flex items-start gap-3">
          <span className="flex size-12 shrink-0 items-center justify-center rounded-2xl bg-primary text-primary-foreground">
            <Ruler className="size-6" />
          </span>
          <div>
            <h1 className="text-3xl font-semibold tracking-tight">Hardware fit check</h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
              Check a known component against confirmed enclosure interior dimensions. The current check is axis-aligned; it does not replace full 3D interference, mounting-pattern, thermal, or manufacturing analysis.
            </p>
          </div>
        </div>
      </header>

      {error && <div role="alert" className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">{error}</div>}

      <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <Card>
          <CardHeader>
            <CardTitle>Component and enclosure</CardTitle>
            <CardDescription>Preset values are suggestions until you verify the exact board variant and confirm the dimensions.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={submit} className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor="hardware-preset">Hardware preset</Label>
                <select
                  id="hardware-preset"
                  value={presetId}
                  onChange={(event) => { setPresetId(event.target.value); setPresetConfirmed(false); setResult(null); }}
                  disabled={loadingPresets || busy || presets.length === 0}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                >
                  {loadingPresets && <option value="">Loading presets…</option>}
                  {!loadingPresets && presets.length === 0 && <option value="">No presets available</option>}
                  {presets.map((preset) => <option key={preset.id} value={preset.id}>{preset.name}</option>)}
                </select>
              </div>

              {selectedPreset && (
                <div className="rounded-xl border border-border bg-muted/30 p-3">
                  <p className="font-medium">{selectedPreset.name}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{selectedPreset.description}</p>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
                    <div><p className="text-xs text-muted-foreground">Width</p><p className="font-semibold">{formatMm(selectedPreset.width_mm)}</p></div>
                    <div><p className="text-xs text-muted-foreground">Length</p><p className="font-semibold">{formatMm(selectedPreset.length_mm)}</p></div>
                    <div><p className="text-xs text-muted-foreground">Height</p><p className="font-semibold">{formatMm(selectedPreset.height_mm)}</p></div>
                  </div>
                  <p className="mt-2 text-xs text-muted-foreground">Source: {selectedPreset.source}. {selectedPreset.part_number ? `Part number: ${selectedPreset.part_number}.` : "No manufacturer part number provided."}</p>
                </div>
              )}

              <div className="space-y-2">
                <Label htmlFor="clearance">Required clearance per side (mm)</Label>
                <Input id="clearance" type="number" min="0" max="100" step="0.1" value={clearance} onChange={(event) => { setClearance(event.target.value); setEnclosureConfirmed(false); setResult(null); }} disabled={busy} required />
              </div>

              <Button type="button" variant="outline" className="w-full" onClick={useSuggestedDimensions} disabled={!selectedPreset || busy}>
                Use suggested interior dimensions
              </Button>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2"><Label htmlFor="interior-width">Interior width (mm)</Label><Input id="interior-width" type="number" min="0.1" step="0.1" value={width} onChange={(event) => { setWidth(event.target.value); setEnclosureConfirmed(false); setResult(null); }} disabled={busy} required /></div>
                <div className="space-y-2"><Label htmlFor="interior-length">Interior length / depth (mm)</Label><Input id="interior-length" type="number" min="0.1" step="0.1" value={length} onChange={(event) => { setLength(event.target.value); setEnclosureConfirmed(false); setResult(null); }} disabled={busy} required /></div>
                <div className="space-y-2"><Label htmlFor="interior-height">Interior height (mm)</Label><Input id="interior-height" type="number" min="0.1" step="0.1" value={height} onChange={(event) => { setHeight(event.target.value); setEnclosureConfirmed(false); setResult(null); }} disabled={busy} required /></div>
                <div className="space-y-2"><Label htmlFor="wall-thickness">Wall thickness (mm)</Label><Input id="wall-thickness" type="number" min="0.1" max="100" step="0.1" value={wallThickness} onChange={(event) => { setWallThickness(event.target.value); setEnclosureConfirmed(false); setResult(null); }} disabled={busy} required /></div>
              </div>

              <div className="space-y-4 rounded-xl border border-border p-3">
                <label className="flex items-start gap-3 text-sm leading-5">
                  <input type="checkbox" className="mt-1 size-4 accent-primary" checked={presetConfirmed} onChange={(event) => setPresetConfirmed(event.target.checked)} disabled={busy} />
                  <span><span className="font-medium">I verified the selected component.</span><span className="mt-1 block text-muted-foreground">I checked its exact model/revision and the listed dimensions and mounting pattern against a reliable source.</span></span>
                </label>
                <label className="flex items-start gap-3 text-sm leading-5">
                  <input type="checkbox" className="mt-1 size-4 accent-primary" checked={enclosureConfirmed} onChange={(event) => setEnclosureConfirmed(event.target.checked)} disabled={busy} />
                  <span><span className="font-medium">I confirm these enclosure dimensions.</span><span className="mt-1 block text-muted-foreground">The interior dimensions are the actual usable space, not the outside measurements.</span></span>
                </label>
              </div>

              <Button type="submit" className="w-full" disabled={loadingPresets || busy || !selectedPreset}>
                {busy ? "Checking fit…" : <><ClipboardCheck className="mr-2 size-4" /> Run fit check</>}
              </Button>
            </form>
          </CardContent>
        </Card>

        <div className="space-y-5">
          <Card>
            <CardHeader><CardTitle>What this check covers</CardTitle><CardDescription>Checks run by the current Python fit engine.</CardDescription></CardHeader>
            <CardContent className="space-y-3 text-sm leading-6">
              <div className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" /><p>Axis-aligned width, length, and height after the required clearance is applied.</p></div>
              <div className="flex items-start gap-2"><CheckCircle2 className="mt-0.5 size-4 shrink-0 text-primary" /><p>Shortfalls in millimetres when a component exceeds the available space.</p></div>
              <div className="flex items-start gap-2"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-600" /><p>Mounting-hole alignment is only checked when actual enclosure boss coordinates are supplied.</p></div>
              <div className="flex items-start gap-2"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-primary" /><p>A fit result does not verify strength, heat, cable access, keep-out zones, or printability.</p></div>
            </CardContent>
          </Card>

          {result && currentResult && (
            <Card className={result.report.overall_fit ? "border-emerald-500/40" : "border-destructive/40"}>
              <CardHeader>
                <div className="flex items-center gap-2">
                  {result.report.overall_fit ? <CheckCircle2 className="size-5 text-emerald-600" /> : <AlertTriangle className="size-5 text-destructive" />}
                  <CardTitle>{result.report.overall_fit ? "Dimensions fit" : "Fit check failed"}</CardTitle>
                </div>
                <CardDescription>{result.report.summary}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-3 gap-2">
                  {(["x", "y", "z"] as const).map((axis) => (
                    <div key={axis} className="rounded-lg border border-border p-3">
                      <p className="text-xs uppercase text-muted-foreground">{axis} clearance</p>
                      <p className="mt-1 font-semibold">{formatMm(currentResult.clearance_mm[axis] ?? NaN)}</p>
                      {currentResult.shortfall_mm[axis] > 0 && <p className="mt-1 text-xs text-destructive">Short by {formatMm(currentResult.shortfall_mm[axis])}</p>}
                    </div>
                  ))}
                </div>
                {currentResult.issues.length > 0 && <div className="space-y-1"><p className="text-sm font-semibold text-destructive">Issues</p><ul className="list-disc space-y-1 pl-5 text-sm text-destructive">{currentResult.issues.map((issue) => <li key={issue}>{issue}</li>)}</ul></div>}
                {currentResult.warnings.length > 0 && <div className="space-y-1"><p className="text-sm font-semibold">Warnings</p><ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">{currentResult.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></div>}
                <div className="rounded-xl bg-muted/40 p-3 text-xs leading-5 text-muted-foreground">{result.limitations.map((limitation) => <p key={limitation} className="mb-1 last:mb-0">{limitation}</p>)}</div>
              </CardContent>
            </Card>
          )}

          {!result && <div className="rounded-xl border border-dashed border-border p-8 text-center"><Ruler className="mx-auto size-8 text-muted-foreground" /><h2 className="mt-3 font-medium">Ready to verify fit</h2><p className="mt-1 text-sm leading-6 text-muted-foreground">Choose a component, confirm the source dimensions, enter the usable enclosure space, and run the check.</p></div>}
        </div>
      </div>
    </div>
  );
}
