"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { FileSearch, LoaderCircle, ShieldCheck, WandSparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type BlueprintBodyType = "rotational_flange" | "prismatic_box" | "sheet_enclosure" | "revolved_profile";
type BlueprintProfile = "circle" | "rectangle" | "polygon" | "complex_path";
type BlueprintFeatureType = "circular_pattern_cut" | "through_hole" | "pocket" | "fillet";
type BlueprintFeature = {
  type: BlueprintFeatureType;
  count: number;
  pitch_radius: number | null;
  start_angle: number;
  angular_pitch: number | null;
  diameter: number | null;
  length: number | null;
  width: number | null;
  depth: number | null;
  radius: number | null;
  edge_scope: "all" | "top" | "bottom";
  x: number;
  y: number;
};
type Blueprint = {
  part_name: string;
  primary_body_type: BlueprintBodyType | null;
  base_sketch: {
    profile: BlueprintProfile;
    outer_diameter: number | null;
    inner_bore_diameter: number | null;
    width: number | null;
    length: number | null;
    thickness: number | null;
    wall_thickness: number | null;
    thickness_is_default: boolean;
    wall_thickness_is_default: boolean;
    points: number[][] | null;
  };
  features: BlueprintFeature[];
  warnings: string[];
  unsupported_geometry: string[];
  source_pages: number[];
  needs_review: boolean;
};

type OCRSpec = {
  blueprint?: Blueprint | null;
  dimensionInventory?: Array<{ id: string; raw: string; value: number; kind: string; page: number | null }>;
  vectorGeometry?: Array<{ page: number; kind: string; center_x_pt: number; center_y_pt: number; width_pt: number; height_pt: number; curve_segments?: number }>;
  blueprintSource?: string;
  blueprintSourcePages?: number;
  blueprintClearedFields?: string[];
  blueprintVisionModel?: string | null;
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
  confidenceMethod?: string;
  rawText?: string;
  pageCount?: number;
  needsReview?: boolean;
  limitations?: string[];
};

type SourceFile = { index: number; name: string; ocrResult?: OCRSpec };
type Props = { projectId: string; sourceFiles: SourceFile[] };
type SketchNumberKey = "outer_diameter" | "inner_bore_diameter" | "width" | "length" | "thickness" | "wall_thickness";
type FeatureNumberKey = "count" | "pitch_radius" | "start_angle" | "angular_pitch" | "diameter" | "length" | "width" | "depth" | "radius" | "x" | "y";

const blueprintSketchFields: Array<{ key: SketchNumberKey; label: string; defaultFlag?: "thickness_is_default" | "wall_thickness_is_default" }> = [
  { key: "outer_diameter", label: "Outer diameter (mm)" },
  { key: "inner_bore_diameter", label: "Central bore diameter (mm)" },
  { key: "length", label: "Length / X (mm)" },
  { key: "width", label: "Width / Y (mm)" },
  { key: "thickness", label: "Height / depth (mm)", defaultFlag: "thickness_is_default" },
  { key: "wall_thickness", label: "Enclosure wall (mm)", defaultFlag: "wall_thickness_is_default" },
];

const blueprintFeatureFields: Array<{ key: FeatureNumberKey; label: string }> = [
  { key: "count", label: "Count" },
  { key: "diameter", label: "Diameter (mm)" },
  { key: "pitch_radius", label: "Pitch radius (mm)" },
  { key: "start_angle", label: "First angle (deg)" },
  { key: "angular_pitch", label: "Angular pitch (deg)" },
  { key: "length", label: "Pocket length (mm)" },
  { key: "width", label: "Pocket width (mm)" },
  { key: "depth", label: "Blind depth (mm; blank = through)" },
  { key: "radius", label: "Fillet radius (mm)" },
  { key: "x", label: "X offset (mm)" },
  { key: "y", label: "Y offset (mm)" },
];

const blueprintInputClass = (flagged: boolean) =>
  "mt-1 w-full rounded-md border px-2 py-2 text-sm " +
  (flagged ? "border-amber-500 bg-amber-50 text-amber-950" : "border-input bg-background");

function numericInputValue(raw: string): number | null {
  if (!raw.trim()) return null;
  const value = Number(raw);
  return Number.isFinite(value) ? value : null;
}

export function DrawingProcessor({ projectId, sourceFiles }: Props) {
  const router = useRouter();
  const ocrSourceFiles = sourceFiles.filter((file) => /\.(pdf|png|jpe?g|bmp|tiff?|webp)$/i.test(file.name));
  const [selectedIndex, setSelectedIndex] = useState<number>(ocrSourceFiles[0]?.index ?? -1);
  const [results, setResults] = useState<Record<number, OCRSpec>>(() => Object.fromEntries(
    ocrSourceFiles.flatMap((file) => file.ocrResult ? [[file.index, file.ocrResult]] : []),
  ));
  const [reviewedDescription, setReviewedDescription] = useState(
    ocrSourceFiles[0]?.ocrResult?.rawText ?? "",
  );
  const [analyzing, setAnalyzing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const selected = useMemo(() => ocrSourceFiles.find((file) => file.index === selectedIndex), [ocrSourceFiles, selectedIndex]);
  const currentResult = results[selectedIndex] ?? null;
  const blueprint = currentResult?.blueprint ?? null;

  function updateCurrentResult(updater: (result: OCRSpec) => OCRSpec) {
    setResults((previous) => {
      const current = previous[selectedIndex];
      if (!current) return previous;
      return { ...previous, [selectedIndex]: updater(current) };
    });
  }

  function updateBlueprintSketch(key: SketchNumberKey, raw: string) {
    updateCurrentResult((result) => {
      if (!result.blueprint) return result;
      return {
        ...result,
        blueprint: {
          ...result.blueprint,
          base_sketch: { ...result.blueprint.base_sketch, [key]: numericInputValue(raw) },
          needs_review: true,
        },
      };
    });
  }

  function updateBlueprintFeature(index: number, key: FeatureNumberKey, raw: string) {
    updateCurrentResult((result) => {
      if (!result.blueprint) return result;
      const value = numericInputValue(raw);
      return {
        ...result,
        blueprint: {
          ...result.blueprint,
          features: result.blueprint.features.map((feature, i) => i !== index ? feature : {
            ...feature,
            [key]: key === "count" ? Math.max(1, Math.min(360, Math.round(value ?? 1))) : value,
          }),
          needs_review: true,
        },
      };
    });
  }

  function updateBlueprintBodyType(value: string) {
    const allowed: BlueprintBodyType[] = ["rotational_flange", "prismatic_box", "sheet_enclosure", "revolved_profile"];
    updateCurrentResult((result) => !result.blueprint ? result : ({
      ...result,
      blueprint: {
        ...result.blueprint,
        primary_body_type: allowed.includes(value as BlueprintBodyType) ? value as BlueprintBodyType : null,
        needs_review: true,
      },
    }));
  }

  function updateBlueprintProfile(value: string) {
    const allowed: BlueprintProfile[] = ["circle", "rectangle", "polygon", "complex_path"];
    updateCurrentResult((result) => !result.blueprint ? result : ({
      ...result,
      blueprint: {
        ...result.blueprint,
        base_sketch: {
          ...result.blueprint.base_sketch,
          profile: allowed.includes(value as BlueprintProfile) ? value as BlueprintProfile : "circle",
        },
        needs_review: true,
      },
    }));
  }

  function addBlueprintFeature() {
    updateCurrentResult((result) => {
      if (!result.blueprint || result.blueprint.features.length >= 100) return result;
      const feature: BlueprintFeature = {
        type: "through_hole", count: 1, pitch_radius: null, start_angle: 0,
        angular_pitch: null, diameter: null, length: null, width: null,
        depth: null, radius: null, edge_scope: "all", x: 0, y: 0,
      };
      return {
        ...result,
        blueprint: { ...result.blueprint, features: [...result.blueprint.features, feature], needs_review: true },
      };
    });
  }

  function removeBlueprintFeature(index: number) {
    updateCurrentResult((result) => !result.blueprint ? result : ({
      ...result,
      blueprint: {
        ...result.blueprint,
        features: result.blueprint.features.filter((_feature, i) => i !== index),
        needs_review: true,
      },
    }));
  }

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
      setNotice(
        payload.spec.blueprint
          ? "Drawing analyzed. Review the structured dimensions and warnings; no free-text prompt is required when the blueprint is valid."
          : "Text extracted. No structured blueprint is available, so review the OCR text and enter a supported part description.",
      );
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Drawing OCR failed.");
    } finally {
      setAnalyzing(false);
    }
  }

  async function generate() {
    if (!selected || !currentResult) return;
    if (!blueprint && reviewedDescription.trim().length < 5) {
      setError("A structured blueprint or a reviewed dimensioned part description is required.");
      return;
    }
    if (blueprint && !blueprint.primary_body_type) {
      setError("Select a supported primary body type after inspecting the drawing.");
      return;
    }
    if (blueprint?.unsupported_geometry.length) {
      setError("This drawing contains unsupported geometry. The generator will not substitute a simpler part; resolve those features before export.");
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
          ...(blueprint ? { reviewedBlueprint: blueprint } : {}),
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
  if (!ocrSourceFiles.length) return (
    <Card className="mt-5"><CardHeader><CardTitle>Drawing OCR unavailable for these files</CardTitle><CardDescription>Source files remain privately stored. OCR currently accepts PDF, PNG, JPEG, BMP, TIFF and WebP drawings.</CardDescription></CardHeader></Card>
  );

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
            {ocrSourceFiles.map((file) => <option key={file.index} value={file.index}>{file.name}</option>)}
          </select>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={analyze} disabled={analyzing || generating}>
              {analyzing ? <><LoaderCircle className="size-4 animate-spin" /> Analyzing drawing…</> : <><FileSearch className="size-4" /> {currentResult ? "Analyze again" : "Extract drawing text"}</>}
            </Button>
            <Button
              type="button"
              onClick={generate}
              disabled={
                !currentResult || analyzing || generating ||
                (blueprint ? (!blueprint.primary_body_type || blueprint.unsupported_geometry.length > 0) : reviewedDescription.trim().length < 5)
              }
            >
              {generating ? <><LoaderCircle className="size-4 animate-spin" /> Generating CAD…</> : <><WandSparkles className="size-4" /> Generate reviewed STEP + STL</>}
            </Button>
          </div>
        </div>

        {currentResult && (
          <div className="space-y-3 rounded-xl border border-border p-4">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <ShieldCheck className="size-4 text-primary" />
              <span className="font-medium">OCR extraction completed</span>
              <span className="text-muted-foreground">· {currentResult.confidenceMethod === "native_pdf_text" ? "native PDF text extraction" : currentResult.confidenceMethod === "mixed" ? "mixed text/OCR extraction" : `${Math.round((currentResult.confidence ?? 0) * 100)}% OCR word confidence`} · {currentResult.pageCount ?? 1} page(s)</span>
            </div>
            <p className="text-xs leading-5 text-muted-foreground">OCR confidence is not dimension accuracy. Verify units, decimal points, diameter/radius symbols, tolerances, fits, threads and every view against the source.</p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg bg-muted/40 p-3 text-sm"><span className="font-medium">Dimension triplets</span><p className="mt-1 text-muted-foreground">{(currentResult.dimensions?.triplets ?? []).map((item) => item.raw ?? (item.valuesMm ?? []).join(" × ")).join("; ") || "None recognized"}</p></div>
              <div className="rounded-lg bg-muted/40 p-3 text-sm"><span className="font-medium">Diameters / radii</span><p className="mt-1 text-muted-foreground">{[...(currentResult.dimensions?.diameters ?? []), ...(currentResult.dimensions?.radii ?? [])].map((item) => item.raw).filter(Boolean).join("; ") || "None recognized"}</p></div>
              <div className="rounded-lg bg-muted/40 p-3 text-sm"><span className="font-medium">Tolerances and fits</span><p className="mt-1 text-muted-foreground">{[...(currentResult.tolerances ?? []).map((item) => item.raw ?? ""), ...(currentResult.fits ?? [])].filter(Boolean).join("; ") || "None recognized"}</p></div>
              <div className="rounded-lg bg-muted/40 p-3 text-sm"><span className="font-medium">Threads / material / finish</span><p className="mt-1 text-muted-foreground">{[...(currentResult.threads ?? []), currentResult.material ?? "", currentResult.surfaceFinish ?? ""].filter(Boolean).join("; ") || "None recognized"}</p></div>
            </div>
            {blueprint && (
              <section className="space-y-4 rounded-xl border border-border p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h3 className="font-semibold">Structured drawing blueprint</h3>
                    <p className="text-xs text-muted-foreground">
                      {currentResult.blueprintVisionModel
                        ? "Vision model: " + currentResult.blueprintVisionModel
                        : "No vision model configured/reported; fields may be incomplete and need manual review."}
                      {" · "}{currentResult.blueprintSource ?? "drawing"}{" · "}{currentResult.blueprintSourcePages ?? 1} page(s) inspected
                    </p>
                  </div>
                  <span className="rounded-md border border-amber-400 bg-amber-50 px-2 py-1 text-xs text-amber-900">Review required</span>
                </div>

                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="text-sm font-medium">Part name
                    <input
                      className={blueprintInputClass(false)}
                      value={blueprint.part_name}
                      maxLength={120}
                      onChange={(event) => updateCurrentResult((result) => !result.blueprint ? result : ({
                        ...result,
                        blueprint: { ...result.blueprint, part_name: event.target.value.slice(0, 120), needs_review: true },
                      }))}
                    />
                  </label>
                  <label className="text-sm font-medium">Primary body type
                    <select className={blueprintInputClass(!blueprint.primary_body_type)} value={blueprint.primary_body_type ?? ""} onChange={(event) => updateBlueprintBodyType(event.target.value)}>
                      <option value="">Unresolved — choose after reviewing</option>
                      <option value="rotational_flange">Rotational flange / plate</option>
                      <option value="prismatic_box">Prismatic box / plate</option>
                      <option value="sheet_enclosure">Open-top sheet enclosure</option>
                      <option value="revolved_profile">Revolved profile</option>
                    </select>
                  </label>
                  <label className="text-sm font-medium">Base profile
                    <select className={blueprintInputClass(false)} value={blueprint.base_sketch.profile} onChange={(event) => updateBlueprintProfile(event.target.value)}>
                      <option value="circle">Circle</option>
                      <option value="rectangle">Rectangle</option>
                      <option value="polygon">Polygon</option>
                      <option value="complex_path">Complex path (limited)</option>
                    </select>
                  </label>
                </div>

                <div>
                  <h4 className="mb-2 text-sm font-semibold">Base sketch dimensions (mm)</h4>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {blueprintSketchFields.map(({ key, label, defaultFlag }) => {
                      const isDefault = defaultFlag ? Boolean(blueprint.base_sketch[defaultFlag]) : false;
                      const cleared = (currentResult.blueprintClearedFields ?? []).some((field) => field.startsWith("base_sketch." + key + "="));
                      return (
                        <label key={key} className="text-sm font-medium">
                          {label}
                          {isDefault && <span className="ml-1 text-amber-700">(default)</span>}
                          {cleared && <span className="ml-1 text-amber-700">(not grounded)</span>}
                          <input
                            type="number"
                            step="0.01"
                            className={blueprintInputClass(isDefault || cleared || blueprint.base_sketch[key] === null)}
                            value={blueprint.base_sketch[key] ?? ""}
                            onChange={(event) => updateBlueprintSketch(key, event.target.value)}
                          />
                        </label>
                      );
                    })}
                  </div>
                  {blueprint.base_sketch.points && (
                    <p className="mt-2 text-xs text-muted-foreground">
                      {blueprint.base_sketch.points.length} profile points extracted. Point-by-point editing is not available in this UI pass; inspect those coordinates before export.
                    </p>
                  )}
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold">Features ({blueprint.features.length})</h4>
                    <Button type="button" size="sm" variant="outline" onClick={addBlueprintFeature} disabled={blueprint.features.length >= 100 || generating}>Add feature</Button>
                  </div>
                  {blueprint.features.length === 0 && <p className="text-sm text-muted-foreground">No machinable features were identified. Check the drawing views before exporting.</p>}
                  {blueprint.features.map((feature, index) => (
                    <fieldset key={index} className="space-y-3 rounded-md border p-3">
                      <legend className="px-1 text-sm font-medium">Feature {index + 1}</legend>
                      <div className="flex items-center justify-between gap-2">
                        <label className="block flex-1 text-sm font-medium">Feature type
                          <select
                            className={blueprintInputClass(false)}
                            value={feature.type}
                            onChange={(event) => updateCurrentResult((result) => {
                              if (!result.blueprint) return result;
                              const allowed: BlueprintFeatureType[] = ["circular_pattern_cut", "through_hole", "pocket", "fillet"];
                              const type = allowed.includes(event.target.value as BlueprintFeatureType) ? event.target.value as BlueprintFeatureType : "through_hole";
                              return {
                                ...result,
                                blueprint: {
                                  ...result.blueprint,
                                  features: result.blueprint.features.map((item, i) => i === index ? { ...item, type } : item),
                                  needs_review: true,
                                },
                              };
                            })}
                          >
                            <option value="circular_pattern_cut">Circular hole pattern</option>
                            <option value="through_hole">Through hole</option>
                            <option value="pocket">Pocket</option>
                            <option value="fillet">Fillet</option>
                          </select>
                        </label>
                        <Button type="button" size="sm" variant="ghost" onClick={() => removeBlueprintFeature(index)} disabled={generating}>Remove</Button>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        {blueprintFeatureFields.filter(({ key }) => {
                          if (feature.type === "circular_pattern_cut") return ["count", "diameter", "pitch_radius", "start_angle", "angular_pitch", "depth", "x", "y"].includes(key);
                          if (feature.type === "through_hole") return ["diameter", "depth", "x", "y"].includes(key);
                          if (feature.type === "pocket") return ["diameter", "length", "width", "depth", "x", "y"].includes(key);
                          return key === "radius";
                        }).map(({ key, label }) => {
                          const cleared = (currentResult.blueprintClearedFields ?? []).some((field) => field.startsWith("features[" + index + "]." + key + "="));
                          return (
                            <label key={key} className="text-sm font-medium">
                              {label}
                              <input
                                type="number"
                                step={key === "count" ? "1" : "0.01"}
                                className={blueprintInputClass(cleared || feature[key] === null)}
                                value={feature[key] ?? ""}
                                onChange={(event) => updateBlueprintFeature(index, key, event.target.value)}
                              />
                            </label>
                          );
                        })}
                      </div>
                      {feature.type === "fillet" && (
                        <label className="block text-sm font-medium">Edge scope
                          <select
                            className={blueprintInputClass(false)}
                            value={feature.edge_scope}
                            onChange={(event) => updateCurrentResult((result) => !result.blueprint ? result : ({
                              ...result,
                              blueprint: {
                                ...result.blueprint,
                                features: result.blueprint.features.map((item, i) => i === index ? { ...item, edge_scope: event.target.value as BlueprintFeature["edge_scope"] } : item),
                                needs_review: true,
                              },
                            }))}
                          >
                            <option value="all">All edges</option>
                            <option value="top">Top edges</option>
                            <option value="bottom">Bottom edges</option>
                          </select>
                        </label>
                      )}
                    </fieldset>
                  ))}
                </div>

                {blueprint.warnings.length > 0 && (
                  <div className="rounded-lg border border-amber-400 bg-amber-50 p-3 text-sm text-amber-950">
                    <p className="mb-1 flex items-center gap-2 font-semibold"><AlertTriangle className="size-4" />Blueprint warnings — verify before export</p>
                    <ul className="list-disc space-y-1 pl-5">{blueprint.warnings.map((warning, i) => <li key={String(i) + "-" + warning}>{warning}</li>)}</ul>
                  </div>
                )}
                {blueprint.unsupported_geometry.length > 0 && (
                  <div role="alert" className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
                    <p className="font-semibold">Generation blocked: unsupported geometry</p>
                    <ul className="mt-1 list-disc pl-5">{blueprint.unsupported_geometry.map((item, i) => <li key={String(i) + "-" + item}>{item}</li>)}</ul>
                    <p className="mt-2">The engine will not replace teeth, bends or other unsupported shapes with a simpler part.</p>
                  </div>
                )}
                <p className="text-xs leading-5 text-muted-foreground">
                  Numeric values not grounded in drawing text are cleared and highlighted. Defaulted heights/walls are highlighted. Editing a value is an explicit override, not proof that it matches the drawing.
                </p>
              </section>
            )}

            {currentResult.vectorGeometry && currentResult.vectorGeometry.length > 0 && (
              <details className="rounded-md border p-3">
                <summary className="cursor-pointer text-sm font-medium">Vector PDF geometry candidates ({currentResult.vectorGeometry.length})</summary>
                <p className="mt-1 text-xs text-muted-foreground">These are path-shape candidates measured in PDF points, not confirmed CAD features or millimetre dimensions.</p>
                <div className="mt-2 max-h-40 overflow-auto text-xs">
                  {currentResult.vectorGeometry.map((item, i) => (
                    <p key={String(i) + "-" + item.page + "-" + item.kind} className="py-1 text-muted-foreground">
                      Page {item.page}: {item.kind}, {item.width_pt} × {item.height_pt} pt, center ({item.center_x_pt}, {item.center_y_pt})
                    </p>
                  ))}
                </div>
              </details>
            )}

            {currentResult.dimensionInventory && currentResult.dimensionInventory.length > 0 && (
              <details className="rounded-md border p-3">
                <summary className="cursor-pointer text-sm font-medium">Grounded dimension inventory ({currentResult.dimensionInventory.length})</summary>
                <div className="mt-2 max-h-48 overflow-auto text-xs">
                  {currentResult.dimensionInventory.map((item) => (
                    <p key={item.id} className="py-1 text-muted-foreground">{item.id}: {item.raw} → {item.value} mm ({item.kind}, page {item.page ?? "unknown"})</p>
                  ))}
                </div>
              </details>
            )}

            {!blueprint && (
            <div className="space-y-2">
              <label htmlFor="reviewed-cad-description" className="text-sm font-medium">Review/edit the part description</label>
              <textarea id="reviewed-cad-description" value={reviewedDescription} onChange={(event) => setReviewedDescription(event.target.value)} maxLength={4000} rows={6} disabled={analyzing || generating} className="flex w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring" placeholder="Rewrite the OCR result into a clear description with all required dimensions and an explicit shape." />
              <p className="text-xs leading-5 text-muted-foreground">Only supported, fully dimensioned primitive descriptions are currently converted to CAD. If the text is ambiguous or lacks dimensions, generation returns an error rather than inventing the missing geometry.</p>
            </div>
            )}
          </div>
        )}

        {error && <div role="alert" className="rounded-xl border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}{error.includes("Pro subscription") && <Link href="/dashboard/billing" className="mt-2 block font-semibold underline">View Pro plan and subscribe</Link>}</div>}
        {notice && <div role="status" className="rounded-xl border border-primary/20 bg-primary/5 p-3 text-sm leading-6">{notice}</div>}
      </CardContent>
    </Card>
  );
}
