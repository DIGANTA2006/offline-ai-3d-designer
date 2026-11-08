import { NextResponse } from "next/server";
import type { Prisma } from "@prisma/client";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";
import { compactStoredJson } from "@/lib/project-retention";
import { checkPaidFeatureAccess } from "@/lib/billing/paid-access";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 20;

type Context = { params: Promise<{ projectId: string }> };
type Candidate = { kind?: unknown };
type MeasurementBinding =
  | { scope: "base_sketch"; field: "outer_diameter" | "inner_bore_diameter" | "width" | "length" | "thickness" | "wall_thickness" }
  | { scope: "feature"; featureIndex: number; field: "count" | "pitch_radius" | "start_angle" | "angular_pitch" | "diameter" | "inner_diameter" | "root_radius" | "length" | "width" | "depth" | "radius" };
type ReviewInput = {
  measurementIndex: number;
  decision: "confirmed_reading" | "rejected";
  value?: number | null;
  unit?: string | null;
  featureDescription?: string | null;
  targetBinding?: MeasurementBinding | null;
  note?: string | null;
};
type SavedReview = ReviewInput & { reviewedAt: string; reviewedBy: string };

class RouteError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

function json(body: unknown, init: ResponseInit = {}) {
  const headers = new Headers(init.headers);
  headers.set("Cache-Control", "no-store");
  return NextResponse.json(body, { ...init, headers });
}

const MAX_BODY_BYTES = 32 * 1024;
const MAX_REVIEWS = 200;
const MAX_MEASUREMENT_VALUE = 1_000_000;
const LENGTH_UNITS = new Set(["mm", "cm", "m", "in", "inch"]);
const ANGLE_UNITS = new Set(["deg", "°"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function optionalText(value: unknown, label: string, maxLength: number): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value !== "string") throw new RouteError(label + " must be text.", 400);
  const cleaned = value.trim();
  if (cleaned.length > maxLength) throw new RouteError(label + " is too long.", 400);
  return cleaned || null;
}

function validateTargetBinding(
  raw: unknown,
  candidateKind: unknown,
  blueprint: Record<string, unknown>,
): MeasurementBinding | null {
  if (raw === undefined || raw === null) return null;
  if (!isRecord(raw)) throw new RouteError("CAD field association must be an object.", 400);

  const baseFieldKinds: Record<string, string> = {
    outer_diameter: "diameter",
    inner_bore_diameter: "diameter",
    width: "linear",
    length: "linear",
    thickness: "linear",
    wall_thickness: "linear",
  };
  const bodyType = typeof blueprint.primary_body_type === "string" ? blueprint.primary_body_type : null;

  if (raw.scope === "base_sketch") {
    if (Object.keys(raw).some((key) => !["scope", "field"].includes(key))) {
      throw new RouteError("Base-sketch association contains unsupported properties.", 400);
    }
    const field = raw.field;
    if (typeof field !== "string" || !Object.hasOwn(baseFieldKinds, field)) {
      throw new RouteError("This base-sketch field cannot receive a reviewed measurement.", 422);
    }
    if (candidateKind !== baseFieldKinds[field]) {
      throw new RouteError("Measurement kind does not match the selected base-sketch field.", 422);
    }
    if ((field === "outer_diameter" || field === "inner_bore_diameter") && bodyType !== "rotational_flange") {
      throw new RouteError("Diameter bindings on the base sketch require a rotational flange.", 422);
    }
    if ((field === "width" || field === "length") && !["prismatic_box", "sheet_enclosure"].includes(bodyType ?? "")) {
      throw new RouteError("Base-sketch width and length bindings require a prismatic body.", 422);
    }
    if (field === "thickness" && (!bodyType || bodyType === "revolved_profile")) {
      throw new RouteError("Solid thickness cannot be bound for this body type.", 422);
    }
    if (field === "wall_thickness" && bodyType !== "sheet_enclosure") {
      throw new RouteError("Wall thickness can only be bound on a sheet enclosure.", 422);
    }
    return { scope: "base_sketch", field: field as MeasurementBinding & never } as MeasurementBinding;
  }

  if (raw.scope === "feature") {
    if (Object.keys(raw).some((key) => !["scope", "featureIndex", "field"].includes(key))) {
      throw new RouteError("Feature association contains unsupported properties.", 400);
    }
    const featureIndex = raw.featureIndex;
    const features = blueprint.features;
    if (typeof featureIndex !== "number" || !Number.isSafeInteger(featureIndex) ||
        !Array.isArray(features) || featureIndex < 0 || featureIndex >= features.length) {
      throw new RouteError("CAD field association refers to an unknown Blueprint feature.", 422);
    }
    const feature = features[featureIndex];
    if (!isRecord(feature) || typeof feature.type !== "string") {
      throw new RouteError("The selected Blueprint feature is invalid.", 422);
    }
    const featureFieldKinds: Record<string, Record<string, string>> = {
      circular_pattern_cut: { count: "count", pitch_radius: "radius", start_angle: "angle", angular_pitch: "angle", diameter: "diameter", depth: "linear" },
      hole_pattern: { count: "count", pitch_radius: "radius", start_angle: "angle", angular_pitch: "angle", diameter: "diameter", depth: "linear" },
      radial_cutout_pattern: { count: "count", pitch_radius: "radius", root_radius: "radius", radius: "radius", start_angle: "angle", angular_pitch: "angle" },
      ring_step: { diameter: "diameter", inner_diameter: "diameter", depth: "linear" },
      through_hole: { diameter: "diameter", depth: "linear" },
      pocket: { diameter: "diameter", length: "linear", width: "linear", depth: "linear" },
      fillet: { radius: "radius" },
    };
    const allowedFields = featureFieldKinds[feature.type];
    const field = raw.field;
    if (!allowedFields || typeof field !== "string" || !Object.hasOwn(allowedFields, field)) {
      throw new RouteError("This field is not supported for the selected Blueprint feature.", 422);
    }
    if (candidateKind !== allowedFields[field]) {
      throw new RouteError("Measurement kind does not match the selected feature field.", 422);
    }
    return {
      scope: "feature",
      featureIndex,
      field: field as Extract<MeasurementBinding, { scope: "feature" }>["field"],
    };
  }

  throw new RouteError("CAD field association scope must be base_sketch or feature.", 400);
}

function bindingKey(binding: MeasurementBinding): string {
  return binding.scope === "base_sketch"
    ? `base_sketch.${binding.field}`
    : `features[${binding.featureIndex}].${binding.field}`;
}

function validateReview(
  raw: unknown,
  candidates: Candidate[],
  blueprint: Record<string, unknown>,
  userId: string,
  reviewedAt: string,
  seen: Set<number>,
): SavedReview {
  if (!isRecord(raw)) throw new RouteError("Each measurement review must be an object.", 400);
  const index = raw.measurementIndex;
  if (!Number.isSafeInteger(index) || typeof index !== "number" || index < 0 || index >= candidates.length) {
    throw new RouteError("A measurement review refers to an unknown drawing candidate.", 422);
  }
  if (seen.has(index)) throw new RouteError("A drawing measurement may be reviewed only once per save.", 400);
  seen.add(index);

  const decision = raw.decision;
  if (decision !== "confirmed_reading" && decision !== "rejected") {
    throw new RouteError("Measurement decision must be confirmed_reading or rejected.", 400);
  }
  const featureDescription = optionalText(raw.featureDescription, "Feature description", 120);
  const note = optionalText(raw.note, "Review note", 500);
  const candidate = candidates[index];
  if (decision === "rejected" && raw.targetBinding !== undefined && raw.targetBinding !== null) {
    throw new RouteError("A rejected measurement cannot be associated with CAD geometry.", 422);
  }
  const targetBinding = decision === "confirmed_reading"
    ? validateTargetBinding(raw.targetBinding, candidate.kind, blueprint)
    : null;
  const saved: SavedReview = {
    measurementIndex: index,
    decision,
    featureDescription,
    note,
    ...(targetBinding ? { targetBinding } : {}),
    reviewedAt,
    reviewedBy: userId,
  };

  if (decision === "confirmed_reading") {
    const value = raw.value;
    const unit = raw.unit;
    if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > MAX_MEASUREMENT_VALUE) {
      throw new RouteError("A confirmed reading must have a finite value between 0 and 1,000,000.", 422);
    }
    if (typeof unit !== "string") throw new RouteError("A confirmed reading must include a unit.", 422);

    const kind = candidate.kind;
    if (kind === "linear" || kind === "diameter" || kind === "radius") {
      if (!LENGTH_UNITS.has(unit) || value <= 0) {
        throw new RouteError("Linear, diameter and radius readings require a positive value and a length unit.", 422);
      }
    } else if (kind === "angle") {
      if (!ANGLE_UNITS.has(unit)) throw new RouteError("Angle readings require degrees.", 422);
    } else if (kind === "count") {
      if (unit !== "count" || !Number.isInteger(value) || value < 1) {
        throw new RouteError("Count readings require a positive whole number and the count unit.", 422);
      }
    } else {
      throw new RouteError("This candidate has an unknown dimension kind and cannot be confirmed yet.", 422);
    }
    if (targetBinding) {
      if (candidate.kind === "linear" || candidate.kind === "diameter" || candidate.kind === "radius") {
        const multiplier = unit === "mm" ? 1 : unit === "cm" ? 10 : unit === "m" ? 1000 : 25.4;
        if (!Number.isFinite(value * multiplier) || value * multiplier > MAX_MEASUREMENT_VALUE) {
          throw new RouteError("Converted CAD dimensions must not exceed 1,000,000 mm.", 422);
        }
      }
      if (targetBinding.scope === "feature") {
        if (targetBinding.field === "count" && value > 360) {
          throw new RouteError("A feature count cannot exceed 360.", 422);
        }
        if (targetBinding.field === "start_angle" && value > 360) {
          throw new RouteError("A feature start angle must be between 0 and 360 degrees.", 422);
        }
        if (targetBinding.field === "angular_pitch" && (value <= 0 || value > 360)) {
          throw new RouteError("Angular pitch must be greater than 0 and no more than 360 degrees.", 422);
        }
      }
    }
    saved.value = value;
    saved.unit = unit;
  }

  return saved;
}

export async function POST(request: Request, { params }: Context) {
  if (!isSameOriginRequest(request)) {
    return json({ error: "Request origin could not be verified." }, { status: 403 });
  }

  let user;
  try {
    user = await getCurrentUser();
  } catch (error) {
    console.error("Drawing measurement review could not resolve the current user.", error);
    return json({ error: "Authentication or database service is unavailable." }, { status: 503 });
  }
  if (!user) return json({ error: "Sign in before reviewing drawing measurements." }, { status: 401 });

  try {
    const { projectId } = await params;
    const project = await prisma.project.findFirst({
      where: { id: projectId, userId: user.id },
      include: { versions: { orderBy: [{ version: "desc" }, { createdAt: "desc" }], take: 1 } },
    });
    const version = project?.versions[0];
    if (!project || !version || !isRecord(version.spec)) {
      throw new RouteError("Project or saved drawing analysis was not found.", 404);
    }

    const paidAccess = await checkPaidFeatureAccess(
      user,
      "An active Pro subscription is required to save drawing measurement reviews.",
    );
    if (!paidAccess.allowed) throw new RouteError(paidAccess.message, paidAccess.status);

    const rawBody = await request.text();
    if (Buffer.byteLength(rawBody, "utf8") > MAX_BODY_BYTES) {
      throw new RouteError("Measurement review request is too large.", 413);
    }
    let body: unknown;
    try { body = JSON.parse(rawBody); }
    catch { throw new RouteError("A valid JSON body is required.", 400); }
    if (!isRecord(body)) throw new RouteError("A JSON object is required.", 400);

    const fileIndex = body.fileIndex;
    if (typeof fileIndex !== "number" || !Number.isSafeInteger(fileIndex) || fileIndex < 0) {
      throw new RouteError("fileIndex must be a non-negative integer.", 400);
    }
    if (!Array.isArray(body.reviews) || body.reviews.length > MAX_REVIEWS) {
      throw new RouteError("reviews must be an array with no more than 200 entries.", 400);
    }

    const storedSpec = version.spec as Record<string, unknown>;
    const uploadedFiles = storedSpec.uploadedFiles;
    if (!Array.isArray(uploadedFiles) || fileIndex >= uploadedFiles.length) {
      throw new RouteError("Source drawing was not found in this project.", 404);
    }
    const ocrResults = Array.isArray(storedSpec.ocrResults) ? storedSpec.ocrResults : [];
    const resultIndex = ocrResults.findIndex((item) => isRecord(item) && item.fileIndex === fileIndex);
    if (resultIndex < 0) throw new RouteError("Analyze this drawing before saving its measurement review.", 409);

    const resultRecord = ocrResults[resultIndex];
    if (!isRecord(resultRecord) || !isRecord(resultRecord.spec) || !isRecord(resultRecord.spec.blueprint)) {
      throw new RouteError("The saved drawing analysis does not contain a structured Blueprint.", 409);
    }
    const blueprint = resultRecord.spec.blueprint;
    const candidates = blueprint.visual_measurements;
    if (!Array.isArray(candidates)) {
      throw new RouteError("This drawing analysis has no visual measurement candidates to review.", 409);
    }

    const reviewedAt = new Date().toISOString();
    const seen = new Set<number>();
    const savedReviews = body.reviews.map((item) =>
      validateReview(item, candidates as Candidate[], blueprint, user.id, reviewedAt, seen)
    );
    const usedBindings = new Set<string>();
    for (const review of savedReviews) {
      if (!review.targetBinding) continue;
      const key = bindingKey(review.targetBinding);
      if (usedBindings.has(key)) {
        throw new RouteError("Only one reviewed measurement may be assigned to each CAD field in a save.", 400);
      }
      usedBindings.add(key);
    }

    const nextResults = [...ocrResults];
    nextResults[resultIndex] = { ...resultRecord, visualMeasurementReviews: savedReviews };
    const nextSpec = compactStoredJson({ ...storedSpec, ocrResults: nextResults });

    await prisma.projectVersion.update({
      where: { id: version.id },
      data: { spec: nextSpec as Prisma.InputJsonValue },
    });

    try {
      await prisma.auditLog.create({
        data: {
          userId: user.id,
          agent: "drawing-measurement-review",
          provider: "user-review",
          action: "drawing_measurement_reviews_saved",
          status: "success",
          details: {
            projectId,
            versionId: version.id,
            fileIndex,
            confirmedCount: savedReviews.filter((item) => item.decision === "confirmed_reading").length,
            rejectedCount: savedReviews.filter((item) => item.decision === "rejected").length,
          },
        },
      });
    } catch (error) {
      console.error("Measurement review saved but audit logging failed.", error);
    }

    return json({
      ok: true,
      fileIndex,
      reviewCount: savedReviews.length,
      confirmedCount: savedReviews.filter((item) => item.decision === "confirmed_reading").length,
      rejectedCount: savedReviews.filter((item) => item.decision === "rejected").length,
      reviewedAt,
    });
  } catch (error) {
    console.error("Drawing measurement review failed.", error);
    if (error instanceof RouteError) return json({ error: error.message }, { status: error.status });
    return json({ error: "Could not save measurement reviews. Check the project database and service logs." }, { status: 500 });
  }
}
