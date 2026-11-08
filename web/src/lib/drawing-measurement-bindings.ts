export type MeasurementBinding =
  | {
      scope: "base_sketch";
      field: "outer_diameter" | "inner_bore_diameter" | "width" | "length" | "thickness" | "wall_thickness";
    }
  | {
      scope: "feature";
      featureIndex: number;
      field: "count" | "pitch_radius" | "start_angle" | "angular_pitch" | "diameter" | "inner_diameter" | "root_radius" | "length" | "width" | "depth" | "radius";
    };

type MeasurementReviewCandidate = {
  kind: string;
  unit: string;
  reviewedValue?: number | null;
  reviewedUnit?: string;
  reviewStatus?: "pending" | "confirmed" | "rejected";
  reviewPersisted?: boolean;
  targetBinding?: MeasurementBinding | null;
};

type BindingBlueprint = {
  base_sketch: object;
  features: object[];
  visual_measurements?: MeasurementReviewCandidate[];
  needs_review: boolean;
};

export function bindingValue(binding: MeasurementBinding): string {
  return binding.scope === "base_sketch"
    ? `base_sketch.${binding.field}`
    : `features[${binding.featureIndex}].${binding.field}`;
}

export function measurementValueInBlueprintUnits(measurement: MeasurementReviewCandidate): number | null {
  const value = measurement.reviewedValue;
  if (typeof value !== "number" || !Number.isFinite(value)) return null;

  if (measurement.kind === "linear" || measurement.kind === "diameter" || measurement.kind === "radius") {
    const unit = measurement.reviewedUnit ?? measurement.unit;
    const multiplier = unit === "mm" ? 1
      : unit === "cm" ? 10
      : unit === "m" ? 1000
      : unit === "in" || unit === "inch" ? 25.4
      : NaN;
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

/**
 * Apply only saved, user-confirmed measurement bindings to a defensive copy.
 * This deliberately does not infer geometry from OCR text or mutate source evidence.
 */
export function applySavedMeasurementBindings<T extends BindingBlueprint>(source: T): T {
  const blueprint = {
    ...source,
    base_sketch: { ...source.base_sketch },
    features: source.features.map((feature) => ({ ...feature })),
    visual_measurements: [...(source.visual_measurements ?? [])],
  } as T;

  const baseSketch = blueprint.base_sketch as Record<string, unknown>;
  const features = blueprint.features as Array<Record<string, unknown>>;
  const usedTargets = new Set<string>();

  for (const measurement of blueprint.visual_measurements ?? []) {
    const binding = measurement.targetBinding;
    if (measurement.reviewStatus !== "confirmed" || measurement.reviewPersisted !== true || !binding) continue;

    const target = bindingValue(binding);
    const value = measurementValueInBlueprintUnits(measurement);
    if (usedTargets.has(target) || value === null) continue;
    usedTargets.add(target);

    if (binding.scope === "base_sketch") {
      baseSketch[binding.field] = value;
      if (binding.field === "thickness") baseSketch.thickness_is_default = false;
      if (binding.field === "wall_thickness") baseSketch.wall_thickness_is_default = false;
    } else if (features[binding.featureIndex]) {
      features[binding.featureIndex] = {
        ...features[binding.featureIndex],
        [binding.field]: value,
      };
    }
  }

  if (usedTargets.size > 0) blueprint.needs_review = true;
  return blueprint;
}
