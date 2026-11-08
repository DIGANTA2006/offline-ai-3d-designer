"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AlertTriangle, FileSearch, LoaderCircle, ShieldCheck, WandSparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { isOcrSourceFile } from "@/lib/upload/ocr-source-support";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

type BlueprintBodyType = "rotational_flange" | "prismatic_box" | "sheet_enclosure" | "revolved_profile";
type BlueprintProfile = "circle" | "rectangle" | "polygon" | "complex_path";
type BlueprintFeatureType = "circular_pattern_cut" | "hole_pattern" | "radial_cutout_pattern" | "ring_step" | "through_hole" | "pocket" | "fillet";
type BlueprintFeature = {
  type: BlueprintFeatureType;
  count: number;
  pitch_radius: number | null;
  start_angle: number;
  angular_pitch: number | null;
  diameter: number | null;
  inner_diameter: number | null;
  root_radius: number | null;
  ring_mode: "cut" | "boss";
  length: number | null;
  width: number | null;
  depth: number | null;
  radius: number | null;
  edge_scope: "all" | "top" | "bottom";
  x: number;
  y: number;
};
type MeasurementBinding =
  | { scope: "base_sketch"; field: SketchNumberKey }
  | { scope: "feature"; featureIndex: number; field: Exclude<FeatureNumberKey, "x" | "y"> };

type VisualMeasurement = {
  dimension_name: string;
  raw_callout: string;
  value: number | null;
  unit: string;
  kind: string;
  feature?: string | null;
  source_page: number;
  source_view: string;
  confidence: number;
  region?: { x: number; y: number; width: number; height: number } | null;
  verification_status: "vision_only" | "ocr_value_match";
  ocr_inventory_id?: string | null;
  reviewStatus?: "pending" | "confirmed" | "rejected";
  reviewedValue?: number | null;
  reviewedUnit?: string;
  reviewedFeature?: string | null;
  reviewNote?: string;
  targetBinding?: MeasurementBinding | null;
  reviewPersisted?: boolean;
};

type StoredMeasurementReview = {
  measurementIndex: number;
  decision: "confirmed_reading" | "rejected";
  value?: number | null;
  unit?: string | null;
  featureDescription?: string | null;
  targetBinding?: MeasurementBinding | null;
  note?: string | null;
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
  visual_measurements?: VisualMeasurement[];
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

type SourceFile = {
  index: number;
  name: string;
  type?: "pdf" | "image" | "dxf" | string;
  contentType?: string;
  ocrResult?: OCRSpec;
  measurementReviews?: StoredMeasurementReview[];
};
type Props = { projectId: string; sourceFiles: SourceFile[] };
type SketchNumberKey = "outer_diameter" | "inner_bore_diameter" | "width" | "length" | "thickness" | "wall_thickness";
type FeatureNumberKey = "count" | "pitch_radius" | "start_angle" | "angular_pitch" | "diameter" | "inner_diameter" | "root_radius" | "length" | "width" | "depth" | "radius" | "x" | "y";
type DefaultFieldKey = "base_sketch.thickness" | "base_sketch.wall_thickness";
type BindingOption = { value: string; label: string; binding: MeasurementBinding };

const baseBindingFields: Array<{
  field: SketchNumberKey;
  label: string;
  kind: "linear" | "diameter";
  bodies: BlueprintBodyType[];
}> = [
  { field: "outer_diameter", label: "Base sketch · outer diameter", kind: "diameter", bodies: ["rotational_flange"] },
  { field: "inner_bore_diameter", label: "Base sketch · central bore diameter", kind: "diameter", bodies: ["rotational_flange"] },
  { field: "length", label: "Base sketch · overall length", kind: "linear", bodies: ["prismatic_box", "sheet_enclosure"] },
  { field: "width", label: "Base sketch · overall width", kind: "linear", bodies: ["prismatic_box", "sheet_enclosure"] },
  { field: "thickness", label: "Base sketch · solid thickness", kind: "linear", bodies: ["rotational_flange", "prismatic_box", "sheet_enclosure"] },
  { field: "wall_thickness", label: "Base sketch · enclosure wall thickness", kind: "linear", bodies: ["sheet_enclosure"] },
];

const featureBindingFields: Record<BlueprintFeatureType, Array<{
  field: Exclude<FeatureNumberKey, "x" | "y">;
  label: string;
  kind: "linear" | "diameter" | "radius" | "angle" | "count";
}>> = {
  circular_pattern_cut: [
    { field: "count", label: "count", kind: "count" },
    { field: "diameter", label: "hole diameter", kind: "diameter" },
    { field: "pitch_radius", label: "pattern radius (explicit R callout)", kind: "radius" },
    { field: "start_angle", label: "pattern start angle", kind: "angle" },
    { field: "angular_pitch", label: "pattern angular pitch", kind: "angle" },
    { field: "depth", label: "cut depth", kind: "linear" },
  ],
  hole_pattern: [
    { field: "count", label: "hole count", kind: "count" },
    { field: "diameter", label: "hole diameter", kind: "diameter" },
    { field: "pitch_radius", label: "pattern radius (PCD / 2)", kind: "radius" },
    { field: "start_angle", label: "pattern start angle", kind: "angle" },
    { field: "angular_pitch", label: "pattern angular pitch", kind: "angle" },
    { field: "depth", label: "hole depth", kind: "linear" },
  ],
  radial_cutout_pattern: [
    { field: "count", label: "cutout count", kind: "count" },
    { field: "radius", label: "cutout / gullet radius", kind: "radius" },
    { field: "root_radius", label: "root radius", kind: "radius" },
    { field: "pitch_radius", label: "cutter-centre radius", kind: "radius" },
    { field: "start_angle", label: "pattern start angle", kind: "angle" },
    { field: "angular_pitch", label: "pattern angular pitch", kind: "angle" },
  ],
  ring_step: [
    { field: "diameter", label: "ring outer diameter", kind: "diameter" },
    { field: "inner_diameter", label: "ring inner diameter", kind: "diameter" },
    { field: "depth", label: "ring recess / boss depth", kind: "linear" },
  ],
  through_hole: [
    { field: "diameter", label: "hole diameter", kind: "diameter" },
    { field: "depth", label: "hole depth", kind: "linear" },
  ],
  pocket: [
    { field: "diameter", label: "circular pocket diameter", kind: "diameter" },
    { field: "length", label: "pocket length", kind: "linear" },
    { field: "width", label: "pocket width", kind: "linear" },
    { field: "depth", label: "pocket depth", kind: "linear" },
  ],
  fillet: [{ field: "radius", label: "fillet radius", kind: "radius" }],
};

function bindingValue(binding: MeasurementBinding): string {
  return binding.scope === "base_sketch"
    ? `base_sketch.${binding.field}`
    : `features[${binding.featureIndex}].${binding.field}`;
}

function getMeasurementBindingOptions(blueprint: Blueprint, kind: string): BindingOption[] {
  const options: BindingOption[] = [];
  for (const item of baseBindingFields) {
    if (item.kind !== kind || !item.bodies.includes(blueprint.primary_body_type ?? "revolved_profile")) continue;
    const binding: MeasurementBinding = { scope: "base_sketch", field: item.field };
    options.push({ value: bindingValue(binding), label: item.label, binding });
  }
  blueprint.features.forEach((feature, featureIndex) => {
    if (blueprint.primary_body_type === "revolved_profile" || !blueprint.primary_body_type) return;
    if (
      ["hole_pattern", "radial_cutout_pattern", "ring_step"].includes(feature.type)
      && blueprint.primary_body_type !== "rotational_flange"
    ) return;
    for (const item of featureBindingFields[feature.type] ?? []) {
      if (item.kind !== kind) continue;
      const binding: MeasurementBinding = { scope: "feature", featureIndex, field: item.field };
      options.push({ value: bindingValue(binding), label: `Feature ${featureIndex + 1} (${feature.type}) · ${item.label}`, binding });
    }
  });
  return options;
}

function measurementValueInBlueprintUnits(measurement: VisualMeasurement): number | null {
  const value = measurement.reviewedValue;
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  if (measurement.kind === "linear" || measurement.kind === "diameter" || measurement.kind === "radius") {
    const unit = measurement.reviewedUnit ?? measurement.unit;
    const multiplier = unit === "mm" ? 1 : unit === "cm" ? 10 : unit === "m" ? 1000 : unit === "in" || unit === "inch" ? 25.4 : NaN;
    const converted = value * multiplier;
    return Number.isFinite(converted) && converted > 0 && converted <= 1_000_000 ? converted : null;
  }
  if (measurement.kind === "angle" && ["deg", "°"].includes(measurement.reviewedUnit ?? measurement.unit)) {
    return value >= 0 && value <= 360 ? value : null;
  }
  if (measurement.kind === "count" && (measurement.reviewedUnit ?? measurement.unit) === "count") {
    return Number.isInteger(value) && value >= 1 && value <= 360 ? value : null;
  }
  return null;
}

function applySavedMeasurementBindings(source: Blueprint): Blueprint {
  const blueprint: Blueprint = {
    ...source,
    base_sketch: { ...source.base_sketch },
    features: source.features.map((feature) => ({ ...feature })),
    visual_measurements: [...(source.visual_measurements ?? [])],
  };
  const usedTargets = new Set<string>();
  for (const measurement of blueprint.visual_measurements ?? []) {
    const binding = measurement.targetBinding;
    if (measurement.reviewStatus !== "confirmed" || measurement.reviewPersisted !== true || !binding) continue;
    const target = bindingValue(binding);
    const value = measurementValueInBlueprintUnits(measurement);
    if (usedTargets.has(target) || value === null) continue;
    usedTargets.add(target);
    if (binding.scope === "base_sketch") {
      blueprint.base_sketch[binding.field] = value;
      if (binding.field === "thickness") blueprint.base_sketch.thickness_is_default = false;
      if (binding.field === "wall_thickness") blueprint.base_sketch.wall_thickness_is_default = false;
    } else if (blueprint.features[binding.featureIndex]) {
      blueprint.features[binding.featureIndex] = {
        ...blueprint.features[binding.featureIndex],
        [binding.field]: value,
      };
    }
  }
  if (usedTargets.size > 0) blueprint.needs_review = true;
  return blueprint;
}


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
  { key: "inner_diameter", label: "Inner diameter (mm)" },
  { key: "root_radius", label: "Root radius (mm)" },
  { key: "pitch_radius", label: "Pattern / cutter-centre radius (mm)" },
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

function attachSavedMeasurementReviews(spec: OCRSpec, reviews: StoredMeasurementReview[] = []): OCRSpec {
  if (!spec.blueprint?.visual_measurements?.length) return spec;
  const byIndex = new Map(reviews.map((review) => [review.measurementIndex, review]));
  return {
    ...spec,
    blueprint: {
      ...spec.blueprint,
      visual_measurements: spec.blueprint.visual_measurements.map((measurement, index) => {
        const saved = byIndex.get(index);
        const savedBinding = saved?.targetBinding ?? null;
        const bindingIsStillValid = !savedBinding || getMeasurementBindingOptions(spec.blueprint!, measurement.kind)
          .some((option) => option.value === bindingValue(savedBinding));
        return {
          ...measurement,
          reviewStatus: saved?.decision === "confirmed_reading" ? "confirmed"
            : saved?.decision === "rejected" ? "rejected" : "pending",
          reviewedValue: saved && Object.hasOwn(saved, "value") ? saved.value ?? null : measurement.value,
          reviewedUnit: saved?.unit ?? measurement.unit,
          reviewedFeature: saved?.featureDescription ?? measurement.feature ?? "",
          reviewNote: saved?.note ?? "",
          targetBinding: bindingIsStillValid ? savedBinding : null,
          reviewPersisted: Boolean(saved && bindingIsStillValid),
        };
      }),
    },
  };
}

function canConfirmMeasurementReading(measurement: VisualMeasurement): boolean {
  const value = measurement.reviewedValue;
  const unit = measurement.reviewedUnit ?? "unknown";
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1_000_000) return false;
  if (measurement.kind === "linear" || measurement.kind === "diameter" || measurement.kind === "radius") {
    return value > 0 && ["mm", "cm", "m", "in", "inch"].includes(unit);
  }
  if (measurement.kind === "angle") return ["deg", "°"].includes(unit);
  if (measurement.kind === "count") return Number.isInteger(value) && value >= 1 && unit === "count";
  return false;
}

function getCanonicalBlueprintForGeneration(source: Blueprint): Blueprint {
  const blueprint = applySavedMeasurementBindings(source);
  return {
    ...blueprint,
    visual_measurements: (blueprint.visual_measurements ?? []).map((measurement) => {
      const {
        reviewStatus: _reviewStatus,
        reviewedValue: _reviewedValue,
        reviewedUnit: _reviewedUnit,
        reviewedFeature: _reviewedFeature,
        reviewNote: _reviewNote,
        targetBinding: _targetBinding,
        reviewPersisted: _reviewPersisted,
        ...candidate
      } = measurement;
      return candidate;
    }),
  };
}

function getProvisionalDefaultFields(blueprint: Blueprint | null): Array<{ field: DefaultFieldKey; label: string; value: number | null }> {
  if (!blueprint) return [];
  const fields: Array<{ field: DefaultFieldKey; label: string; value: number | null }> = [];
  const confirmedBindings = new Set(
    (blueprint.visual_measurements ?? [])
      .filter((measurement) => measurement.reviewStatus === "confirmed" && measurement.reviewPersisted === true && measurement.targetBinding)
      .map((measurement) => measurement.targetBinding ? bindingValue(measurement.targetBinding) : ""),
  );
  if (blueprint.primary_body_type !== "revolved_profile" && blueprint.base_sketch.thickness_is_default && !confirmedBindings.has("base_sketch.thickness")) {
    fields.push({
      field: "base_sketch.thickness",
      label: "height / depth",
      value: typeof blueprint.base_sketch.thickness === "number" && Number.isFinite(blueprint.base_sketch.thickness) && blueprint.base_sketch.thickness > 0
        ? blueprint.base_sketch.thickness
        : null,
    });
  }
  if (blueprint.primary_body_type === "sheet_enclosure" && blueprint.base_sketch.wall_thickness_is_default && !confirmedBindings.has("base_sketch.wall_thickness")) {
    fields.push({
      field: "base_sketch.wall_thickness",
      label: "enclosure wall thickness",
      value: typeof blueprint.base_sketch.wall_thickness === "number" && Number.isFinite(blueprint.base_sketch.wall_thickness) && blueprint.base_sketch.wall_thickness > 0
        ? blueprint.base_sketch.wall_thickness
        : null,
    });
  }
  return fields;
}


export function DrawingProcessor({ projectId, sourceFiles }: Props) {
  const router = useRouter();
  const ocrSourceFiles = sourceFiles.filter(isOcrSourceFile);
  const [selectedIndex, setSelectedIndex] = useState<number>(ocrSourceFiles[0]?.index ?? -1);
  const [results, setResults] = useState<Record<number, OCRSpec>>(() => Object.fromEntries(
    ocrSourceFiles.flatMap((file) => file.ocrResult ? [[file.index, attachSavedMeasurementReviews(file.ocrResult, file.measurementReviews)]] : []),
  ));
  const [reviewedDescription, setReviewedDescription] = useState(
    (ocrSourceFiles[0]?.ocrResult?.rawText ?? "").slice(0, 4000),
  );
  const [analyzing, setAnalyzing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [savingMeasurementReviews, setSavingMeasurementReviews] = useState(false);
  const [measurementReviewsDirty, setMeasurementReviewsDirty] = useState<Record<number, boolean>>({});
  const [confirmedDefaultFields, setConfirmedDefaultFields] = useState<Record<number, DefaultFieldKey[]>>({});
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const selected = useMemo(() => ocrSourceFiles.find((file) => file.index === selectedIndex), [ocrSourceFiles, selectedIndex]);
  const currentResult = results[selectedIndex] ?? null;
  const blueprint = currentResult?.blueprint ?? null;
  const provisionalDefaultFields = getProvisionalDefaultFields(blueprint);
  const confirmedDefaultsForSelected = confirmedDefaultFields[selectedIndex] ?? [];
  const defaultConfirmationsComplete = provisionalDefaultFields.every(
    (item) => item.value !== null && confirmedDefaultsForSelected.includes(item.field),
  );

  function updateCurrentResult(updater: (result: OCRSpec) => OCRSpec) {
    setResults((previous) => {
      const current = previous[selectedIndex];
      if (!current) return previous;
      return { ...previous, [selectedIndex]: updater(current) };
    });
  }

  function invalidateMeasurementBinding(target: string) {
    const hasSavedBinding = (blueprint?.visual_measurements ?? []).some(
      (measurement) => measurement.targetBinding && bindingValue(measurement.targetBinding) === target,
    );
    if (hasSavedBinding) {
      setMeasurementReviewsDirty((previous) => ({ ...previous, [selectedIndex]: true }));
    }
    updateCurrentResult((result) => {
      if (!result.blueprint?.visual_measurements) return result;
      const nextMeasurements = result.blueprint.visual_measurements.map((measurement) => {
        if (!measurement.targetBinding || bindingValue(measurement.targetBinding) !== target) return measurement;
        return { ...measurement, targetBinding: null, reviewStatus: "pending" as const, reviewPersisted: false };
      });
      return { ...result, blueprint: { ...result.blueprint, visual_measurements: nextMeasurements, needs_review: true } };
    });
  }

  function updateBlueprintSketch(key: SketchNumberKey, raw: string) {
    invalidateMeasurementBinding(`base_sketch.${key}`);
    const confirmationField: DefaultFieldKey | null =
      key === "thickness" ? "base_sketch.thickness"
      : key === "wall_thickness" ? "base_sketch.wall_thickness"
      : null;
    if (confirmationField) {
      setConfirmedDefaultFields((previous) => ({
        ...previous,
        [selectedIndex]: (previous[selectedIndex] ?? []).filter((field) => field !== confirmationField),
      }));
    }
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

  function updateVisualMeasurement(index: number, patch: Partial<Pick<VisualMeasurement, "reviewedValue" | "reviewedUnit" | "reviewedFeature" | "reviewNote" | "targetBinding">>) {
    setMeasurementReviewsDirty((previous) => ({ ...previous, [selectedIndex]: true }));
    updateCurrentResult((result) => {
      if (!result.blueprint?.visual_measurements) return result;
      return {
        ...result,
        blueprint: {
          ...result.blueprint,
          visual_measurements: result.blueprint.visual_measurements.map((measurement, itemIndex) => itemIndex === index
            ? { ...measurement, ...patch, reviewStatus: "pending", reviewPersisted: false }
            : measurement),
        },
      };
    });
  }

  function setVisualMeasurementDecision(index: number, decision: "confirmed" | "rejected") {
    setMeasurementReviewsDirty((previous) => ({ ...previous, [selectedIndex]: true }));
    updateCurrentResult((result) => {
      if (!result.blueprint?.visual_measurements) return result;
      const measurement = result.blueprint.visual_measurements[index];
      if (!measurement) return result;
      if (decision === "confirmed" && !canConfirmMeasurementReading(measurement)) return result;
      return {
        ...result,
        blueprint: {
          ...result.blueprint,
          visual_measurements: result.blueprint.visual_measurements.map((item, itemIndex) => itemIndex === index
            ? { ...item, reviewStatus: decision, reviewPersisted: false, ...(decision === "rejected" ? { targetBinding: null } : {}) }
            : item),
        },
      };
    });
  }

  async function saveMeasurementReviews() {
    if (!selected || !blueprint) return;
    const reviews = (blueprint.visual_measurements ?? []).flatMap((measurement, measurementIndex) => {
      if (measurement.reviewStatus !== "confirmed" && measurement.reviewStatus !== "rejected") return [];
      return [{
        measurementIndex,
        decision: measurement.reviewStatus === "confirmed" ? "confirmed_reading" as const : "rejected" as const,
        ...(measurement.reviewStatus === "confirmed" ? {
          value: measurement.reviewedValue,
          unit: measurement.reviewedUnit ?? measurement.unit,
          featureDescription: measurement.reviewedFeature ?? null,
          targetBinding: measurement.targetBinding ?? null,
        } : {}),
        note: measurement.reviewNote ?? null,
      }];
    });
    setSavingMeasurementReviews(true);
    setError("");
    setNotice("");
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/drawing-review`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fileIndex: selected.index, reviews }),
      });
      const payload = await response.json().catch(() => ({})) as { error?: string; ok?: boolean; confirmedCount?: number; rejectedCount?: number; associatedCount?: number };
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (response.status === 402) throw new Error("Saving measurement reviews requires an active Pro subscription or administrator access.");
      if (!response.ok || !payload.ok) throw new Error(payload.error ?? `Saving measurement reviews failed (HTTP ${response.status}).`);
      updateCurrentResult((result) => !result.blueprint ? result : ({
        ...result,
        blueprint: {
          ...result.blueprint,
          visual_measurements: (result.blueprint.visual_measurements ?? []).map((measurement) => ({
            ...measurement,
            reviewPersisted: measurement.reviewStatus === "confirmed" || measurement.reviewStatus === "rejected",
          })),
        },
      }));
      setMeasurementReviewsDirty((previous) => ({ ...previous, [selected.index]: false }));
      setNotice(`Saved ${payload.confirmedCount ?? 0} confirmed reading(s), ${payload.rejectedCount ?? 0} rejected candidate(s), and ${payload.associatedCount ?? 0} explicit CAD field association(s). Saved associations are applied only when generating reviewed CAD.`);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not save measurement reviews.");
    } finally {
      setSavingMeasurementReviews(false);
    }
  }

  function toggleDefaultConfirmation(field: DefaultFieldKey, checked: boolean) {
    setConfirmedDefaultFields((previous) => {
      const fields = new Set(previous[selectedIndex] ?? []);
      if (checked) fields.add(field);
      else fields.delete(field);
      return { ...previous, [selectedIndex]: Array.from(fields) };
    });
  }

  function updateBlueprintFeature(index: number, key: FeatureNumberKey, raw: string) {
    if (key !== "x" && key !== "y") invalidateMeasurementBinding(`features[${index}].${key}`);
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
    if ((blueprint?.visual_measurements ?? []).some((measurement) => measurement.targetBinding)) {
      setMeasurementReviewsDirty((previous) => ({ ...previous, [selectedIndex]: true }));
    }
    updateCurrentResult((result) => !result.blueprint ? result : ({
      ...result,
      blueprint: {
        ...result.blueprint,
        primary_body_type: allowed.includes(value as BlueprintBodyType) ? value as BlueprintBodyType : null,
        visual_measurements: (result.blueprint.visual_measurements ?? []).map((measurement) =>
          measurement.targetBinding
            ? { ...measurement, targetBinding: null, reviewStatus: "pending" as const, reviewPersisted: false }
            : measurement
        ),
        needs_review: true,
      },
    }));
  }

  function updateBlueprintProfile(value: string) {
    const allowed: BlueprintProfile[] = ["circle", "rectangle", "polygon", "complex_path"];
    if ((blueprint?.visual_measurements ?? []).some((measurement) => measurement.targetBinding?.scope === "base_sketch")) {
      setMeasurementReviewsDirty((previous) => ({ ...previous, [selectedIndex]: true }));
    }
    updateCurrentResult((result) => !result.blueprint ? result : ({
      ...result,
      blueprint: {
        ...result.blueprint,
        base_sketch: {
          ...result.blueprint.base_sketch,
          profile: allowed.includes(value as BlueprintProfile) ? value as BlueprintProfile : "circle",
        },
        visual_measurements: (result.blueprint.visual_measurements ?? []).map((measurement) =>
          measurement.targetBinding?.scope === "base_sketch"
            ? { ...measurement, targetBinding: null, reviewStatus: "pending" as const, reviewPersisted: false }
            : measurement
        ),
        needs_review: true,
      },
    }));
  }

  function addBlueprintFeature() {
    updateCurrentResult((result) => {
      if (!result.blueprint || result.blueprint.features.length >= 100) return result;
      const feature: BlueprintFeature = {
        type: "through_hole", count: 1, pitch_radius: null, start_angle: 0,
        angular_pitch: null, diameter: null, inner_diameter: null, root_radius: null,
        ring_mode: "cut", length: null, width: null, depth: null, radius: null,
        edge_scope: "all", x: 0, y: 0,
      };
      return {
        ...result,
        blueprint: { ...result.blueprint, features: [...result.blueprint.features, feature], needs_review: true },
      };
    });
  }

  function removeBlueprintFeature(index: number) {
    if ((blueprint?.visual_measurements ?? []).some(
      (measurement) => measurement.targetBinding?.scope === "feature" && measurement.targetBinding.featureIndex >= index,
    )) {
      setMeasurementReviewsDirty((previous) => ({ ...previous, [selectedIndex]: true }));
    }
    updateCurrentResult((result) => !result.blueprint ? result : ({
      ...result,
      blueprint: {
        ...result.blueprint,
        features: result.blueprint.features.filter((_feature, i) => i !== index),
        visual_measurements: (result.blueprint.visual_measurements ?? []).map((measurement) =>
          measurement.targetBinding?.scope === "feature" && measurement.targetBinding.featureIndex >= index
            ? { ...measurement, targetBinding: null, reviewStatus: "pending" as const, reviewPersisted: false }
            : measurement.targetBinding?.scope === "feature" && measurement.targetBinding.featureIndex < index
              ? { ...measurement, targetBinding: { ...measurement.targetBinding, featureIndex: measurement.targetBinding.featureIndex } }
              : measurement
        ),
        needs_review: true,
      },
    }));
  }

  function changeSource(value: string) {
    const index = Number(value);
    setSelectedIndex(index);
    setReviewedDescription((results[index]?.rawText ?? "").slice(0, 4000));
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
      setResults((previous) => ({ ...previous, [selected.index]: attachSavedMeasurementReviews(payload.spec!, []) }));
      setReviewedDescription((payload.spec.rawText ?? "").slice(0, 4000));
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
    if (measurementReviewsDirty[selectedIndex]) {
      setError("Save your latest measurement review changes before generating CAD. This persists removals or edits to previous CAD field associations.");
      return;
    }
    const unsavedBindings = (blueprint?.visual_measurements ?? []).some(
      (measurement) => measurement.reviewStatus === "confirmed" && measurement.targetBinding && measurement.reviewPersisted !== true,
    );
    if (unsavedBindings) {
      setError("Save each confirmed CAD field association before generating. This keeps the selected dimension-to-feature mapping in the project review ledger.");
      return;
    }
    if (blueprint?.unsupported_geometry.length) {
      setError("This drawing contains unsupported geometry. The generator will not substitute a simpler part; resolve those features before export.");
      return;
    }
    const missingDefaultConfirmations = getProvisionalDefaultFields(blueprint).filter(
      (item) => item.value === null || !(confirmedDefaultFields[selectedIndex] ?? []).includes(item.field),
    );
    if (missingDefaultConfirmations.length > 0) {
      setError("Review and confirm every highlighted provisional dimension before generating CAD.");
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
          confirmedDefaultFields: getProvisionalDefaultFields(blueprint)
            .filter((item) => item.value !== null && (confirmedDefaultFields[selectedIndex] ?? []).includes(item.field))
            .map((item) => ({ field: item.field, value: item.value })),
          ...(blueprint ? { reviewedBlueprint: getCanonicalBlueprintForGeneration(blueprint) } : {}),
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
                (blueprint
                  ? (!blueprint.primary_body_type || blueprint.unsupported_geometry.length > 0 || !defaultConfirmationsComplete)
                  : reviewedDescription.trim().length < 5)
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
            {blueprint?.visual_measurements && blueprint.visual_measurements.length > 0 && (
              <section className="space-y-3 rounded-xl border border-border p-4">
                <div>
                  <h3 className="font-semibold">Drawing measurement review ledger</h3>
                  <p className="mt-1 text-xs leading-5 text-muted-foreground">
                    Compare each candidate with the original drawing. A CAD association is optional and must be selected manually; no AI feature hint is applied automatically.
                  </p>
                </div>
                <div className="space-y-3">
                  {blueprint.visual_measurements.map((measurement, index) => {
                    const bindingOptions = getMeasurementBindingOptions(blueprint, measurement.kind);
                    const selectedBinding = measurement.targetBinding ? bindingValue(measurement.targetBinding) : "";
                    return (
                    <article key={index} className="space-y-3 rounded-lg border border-border p-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div>
                          <p className="font-medium">{measurement.dimension_name}</p>
                          <p className="mt-1 text-xs text-muted-foreground">{measurement.raw_callout || "No readable callout text"} · {measurement.kind}</p>
                        </div>
                        <div className="flex flex-wrap gap-1">
                          <span className="rounded-md border px-2 py-1 text-xs">
                            {measurement.verification_status === "ocr_value_match" ? "Value also found by OCR" : "Vision-only · verify"}
                          </span>
                          <span className={`rounded-md border px-2 py-1 text-xs ${measurement.reviewStatus === "confirmed" ? "border-emerald-600 text-emerald-700" : measurement.reviewStatus === "rejected" ? "border-destructive text-destructive" : "text-muted-foreground"}`}>
                            {measurement.reviewStatus === "confirmed" ? "Reading confirmed by you" : measurement.reviewStatus === "rejected" ? "Candidate rejected" : "Pending your review"}
                          </span>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
                        <span><strong>AI proposal:</strong> {measurement.value === null ? "Unreadable" : measurement.value} {measurement.unit === "unknown" ? "" : measurement.unit}</span>
                        <span><strong>View:</strong> {measurement.source_view}</span>
                        <span><strong>Page:</strong> {measurement.source_page}</span>
                        {measurement.feature && <span><strong>AI feature hint:</strong> {measurement.feature}</span>}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        Model confidence estimate: {Math.round(measurement.confidence * 100)}% · Uncalibrated and not an accuracy probability
                      </p>
                      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_160px]">
                        <label className="text-sm font-medium">Value you read from the drawing
                          <input
                            type="number"
                            step="any"
                            value={measurement.reviewedValue ?? ""}
                            onChange={(event) => updateVisualMeasurement(index, { reviewedValue: numericInputValue(event.target.value) })}
                            disabled={generating || savingMeasurementReviews}
                            className={blueprintInputClass(measurement.reviewStatus === "pending")}
                          />
                        </label>
                        <label className="text-sm font-medium">Unit
                          <select
                            value={measurement.reviewedUnit ?? measurement.unit}
                            onChange={(event) => updateVisualMeasurement(index, { reviewedUnit: event.target.value })}
                            disabled={generating || savingMeasurementReviews}
                            className={blueprintInputClass(measurement.reviewStatus === "pending")}
                          >
                            <option value="unknown">Unknown</option>
                            <option value="mm">mm</option>
                            <option value="cm">cm</option>
                            <option value="m">m</option>
                            <option value="in">in</option>
                            <option value="inch">inch</option>
                            <option value="deg">deg</option>
                            <option value="°">°</option>
                            <option value="count">count</option>
                          </select>
                        </label>
                      </div>
                      <label className="block text-sm font-medium">Feature this callout appears to describe (your note; not a CAD binding)
                        <input
                          value={measurement.reviewedFeature ?? ""}
                          onChange={(event) => updateVisualMeasurement(index, { reviewedFeature: event.target.value.slice(0, 120) })}
                          maxLength={120}
                          disabled={generating || savingMeasurementReviews}
                          className={blueprintInputClass(false)}
                          placeholder="e.g. outer circular edge, central bore, six mounting holes"
                        />
                      </label>
                      <label className="block text-sm font-medium">Review note (optional)
                        <textarea
                          value={measurement.reviewNote ?? ""}
                          onChange={(event) => updateVisualMeasurement(index, { reviewNote: event.target.value.slice(0, 500) })}
                          maxLength={500}
                          rows={2}
                          disabled={generating || savingMeasurementReviews}
                          className={blueprintInputClass(false)}
                          placeholder="Note any ambiguity, tolerance or reason for rejecting this reading."
                        />
                      </label>
                      <label className="block text-sm font-medium">Associate this confirmed reading with a CAD field (optional)
                        <select
                          value={selectedBinding}
                          onChange={(event) => {
                            const option = bindingOptions.find((item) => item.value === event.target.value);
                            updateVisualMeasurement(index, { targetBinding: option?.binding ?? null });
                          }}
                          disabled={generating || savingMeasurementReviews || measurement.reviewStatus === "rejected"}
                          className={blueprintInputClass(Boolean(measurement.targetBinding && !measurement.reviewPersisted))}
                        >
                          <option value="">Do not apply to CAD geometry</option>
                          {bindingOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                        </select>
                        <span className="mt-1 block text-xs leading-5 text-muted-foreground">
                          Only compatible Blueprint fields are listed. Selecting a field does not apply it yet: confirm the reading and save the review first. A saved association will replace that exact CAD field during generation.
                        </span>
                        {measurement.targetBinding && (
                          <span className="mt-1 block text-xs font-medium text-primary">
                            {measurement.reviewPersisted && measurement.reviewStatus === "confirmed" ? "Saved association: " : "Pending association: "}
                            {bindingOptions.find((option) => option.value === selectedBinding)?.label ?? "Target no longer exists; choose a valid field"}
                          </span>
                        )}
                      </label>
                      <div className="flex flex-wrap gap-2">
                        <Button type="button" size="sm" onClick={() => setVisualMeasurementDecision(index, "confirmed")} disabled={!canConfirmMeasurementReading(measurement) || generating || savingMeasurementReviews}>
                          Confirm reading
                        </Button>
                        <Button type="button" size="sm" variant="outline" onClick={() => setVisualMeasurementDecision(index, "rejected")} disabled={generating || savingMeasurementReviews}>
                          Reject candidate
                        </Button>
                      </div>
                    </article>
                    );
                  })}
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 border-t pt-3">
                  <p className="text-xs leading-5 text-muted-foreground">Edits reset the decision to pending. Only a saved, confirmed, manually selected association is applied to its exact CAD field; source OCR/vision evidence remains unchanged.</p>
                  <Button type="button" variant="outline" onClick={saveMeasurementReviews} disabled={savingMeasurementReviews || analyzing || generating}>
                    {savingMeasurementReviews ? <><LoaderCircle className="size-4 animate-spin" /> Saving review…</> : "Save measurement review"}
                  </Button>
                </div>
              </section>
            )}
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
                  {provisionalDefaultFields.length > 0 && (
                    <fieldset className="mt-4 space-y-2 rounded-lg border border-amber-400 bg-amber-50/60 p-3 text-sm">
                      <legend className="px-1 font-semibold text-amber-950">Confirm provisional dimensions before export</legend>
                      <p className="text-xs leading-5 text-amber-950">
                        These fields were initially filled by the CAD system because the drawing did not provide them. You may adjust a value, but it remains unverified until you confirm the exact current value below. It is not a drawing-derived measurement.
                      </p>
                      {provisionalDefaultFields.map((item) => (
                        <label key={item.field} className="flex items-start gap-2 text-amber-950">
                          <input
                            type="checkbox"
                            className="mt-1"
                            checked={confirmedDefaultsForSelected.includes(item.field)}
                            disabled={item.value === null || generating || analyzing}
                            onChange={(event) => toggleDefaultConfirmation(item.field, event.target.checked)}
                          />
                          <span>
                            I have reviewed and approve the current provisional / manually adjusted {item.label} value of{" "}
                            <strong>{item.value === null ? "missing / invalid" : item.value + " mm"}</strong>{" "}
                            for this model.
                          </span>
                        </label>
                      ))}
                    </fieldset>
                  )}
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
                              const allowed: BlueprintFeatureType[] = ["circular_pattern_cut", "hole_pattern", "radial_cutout_pattern", "ring_step", "through_hole", "pocket", "fillet"];
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
                            <option value="circular_pattern_cut">Circular cut pattern (legacy)</option>
                            <option value="hole_pattern">Bolt-circle hole pattern</option>
                            <option value="radial_cutout_pattern">Radial gullet / perimeter cutout pattern</option>
                            <option value="ring_step">Concentric ring step</option>
                            <option value="through_hole">Through hole</option>
                            <option value="pocket">Pocket</option>
                            <option value="fillet">Fillet</option>
                          </select>
                        </label>
                        <Button type="button" size="sm" variant="ghost" onClick={() => removeBlueprintFeature(index)} disabled={generating}>Remove</Button>
                      </div>
                      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        {blueprintFeatureFields.filter(({ key }) => {
                          if (feature.type === "circular_pattern_cut" || feature.type === "hole_pattern") return ["count", "diameter", "pitch_radius", "start_angle", "angular_pitch", "depth", "x", "y"].includes(key);
                          if (feature.type === "radial_cutout_pattern") return ["count", "radius", "root_radius", "pitch_radius", "start_angle", "x", "y"].includes(key);
                          if (feature.type === "ring_step") return ["diameter", "inner_diameter", "depth"].includes(key);
                          if (feature.type === "through_hole") return ["diameter", "depth", "x", "y"].includes(key);
                          if (feature.type === "pocket") return ["diameter", "length", "width", "depth", "x", "y"].includes(key);
                          return feature.type === "fillet" && key === "radius";
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
                      {feature.type === "ring_step" && (
                        <label className="block text-sm font-medium">Ring operation
                          <select
                            className={blueprintInputClass(false)}
                            value={feature.ring_mode}
                            onChange={(event) => updateCurrentResult((result) => !result.blueprint ? result : ({
                              ...result,
                              blueprint: {
                                ...result.blueprint,
                                features: result.blueprint.features.map((item, i) => i === index ? { ...item, ring_mode: event.target.value === "boss" ? "boss" : "cut" } : item),
                                needs_review: true,
                              },
                            }))}
                          >
                            <option value="cut">Annular recess / counterbore</option>
                            <option value="boss">Raised annular ring</option>
                          </select>
                        </label>
                      )}
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
