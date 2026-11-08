import assert from "node:assert/strict";
import { createRequire, Module } from "node:module";
import { dirname, resolve } from "node:path";

const require = createRequire(import.meta.url);
const ts = require(resolve(process.cwd(), "node_modules/typescript"));
const utilityPath = resolve(process.cwd(), "src/lib/drawing-measurement-bindings.ts");
const source = require("node:fs").readFileSync(utilityPath, "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: {
    target: ts.ScriptTarget.ES2022,
    module: ts.ModuleKind.CommonJS,
    strict: true,
  },
  reportDiagnostics: true,
});
const errors = (output.diagnostics ?? []).filter((item) => item.category === ts.DiagnosticCategory.Error);
assert.equal(errors.length, 0, "measurement binding utility must transpile");

const loaded = new Module(utilityPath);
loaded.filename = utilityPath;
loaded.paths = Module._nodeModulePaths(dirname(utilityPath));
loaded._compile(output.outputText, utilityPath);
const { applySavedMeasurementBindings, bindingValue, measurementValueInBlueprintUnits } = loaded.exports;

assert.equal(bindingValue({ scope: "base_sketch", field: "outer_diameter" }), "base_sketch.outer_diameter");
assert.equal(bindingValue({ scope: "feature", featureIndex: 2, field: "diameter" }), "features[2].diameter");

assert.equal(measurementValueInBlueprintUnits({ kind: "linear", unit: "cm", reviewedValue: 2.5 }), 25);
assert.equal(measurementValueInBlueprintUnits({ kind: "diameter", unit: "in", reviewedValue: 1 }), 25.4);
assert.equal(measurementValueInBlueprintUnits({ kind: "radius", unit: "m", reviewedValue: 0.01 }), 10);
assert.equal(measurementValueInBlueprintUnits({ kind: "angle", unit: "deg", reviewedValue: 45 }), 45);
assert.equal(measurementValueInBlueprintUnits({ kind: "count", unit: "count", reviewedValue: 6 }), 6);
assert.equal(measurementValueInBlueprintUnits({ kind: "linear", unit: "ft", reviewedValue: 2 }), null);
assert.equal(measurementValueInBlueprintUnits({ kind: "count", unit: "count", reviewedValue: 1.5 }), null);
assert.equal(measurementValueInBlueprintUnits({ kind: "angle", unit: "deg", reviewedValue: 361 }), null);

const sourceBlueprint = {
  part_name: "reviewed flange",
  primary_body_type: "rotational_flange",
  base_sketch: {
    profile: "circle",
    outer_diameter: 90,
    inner_bore_diameter: null,
    width: null,
    length: null,
    thickness: 10,
    thickness_is_default: true,
    wall_thickness: 2.5,
    wall_thickness_is_default: true,
    points: null,
  },
  features: [{
    type: "hole_pattern",
    count: 4,
    pitch_radius: 20,
    start_angle: 0,
    angular_pitch: null,
    diameter: 5,
    inner_diameter: null,
    root_radius: null,
    ring_mode: "cut",
    length: null,
    width: null,
    depth: null,
    radius: null,
    edge_scope: "all",
    x: 0,
    y: 0,
  }],
  visual_measurements: [
    {
      kind: "diameter",
      unit: "cm",
      reviewedValue: 8,
      reviewedUnit: "cm",
      reviewStatus: "confirmed",
      reviewPersisted: true,
      targetBinding: { scope: "base_sketch", field: "outer_diameter" },
    },
    {
      kind: "count",
      unit: "count",
      reviewedValue: 6,
      reviewedUnit: "count",
      reviewStatus: "confirmed",
      reviewPersisted: true,
      targetBinding: { scope: "feature", featureIndex: 0, field: "count" },
    },
    {
      kind: "angle",
      unit: "deg",
      reviewedValue: 45,
      reviewedUnit: "deg",
      reviewStatus: "confirmed",
      reviewPersisted: true,
      targetBinding: { scope: "feature", featureIndex: 0, field: "start_angle" },
    },
    {
      kind: "diameter",
      unit: "inch",
      reviewedValue: 2,
      reviewedUnit: "inch",
      reviewStatus: "confirmed",
      reviewPersisted: false,
      targetBinding: { scope: "feature", featureIndex: 0, field: "diameter" },
    },
    {
      kind: "linear",
      unit: "mm",
      reviewedValue: 4,
      reviewedUnit: "mm",
      reviewStatus: "pending",
      reviewPersisted: true,
      targetBinding: { scope: "base_sketch", field: "thickness" },
    },
    {
      kind: "linear",
      unit: "ft",
      reviewedValue: 1,
      reviewedUnit: "ft",
      reviewStatus: "confirmed",
      reviewPersisted: true,
      targetBinding: { scope: "base_sketch", field: "wall_thickness" },
    },
  ],
  warnings: [],
  unsupported_geometry: [],
  source_pages: [1],
  needs_review: false,
};

const applied = applySavedMeasurementBindings(sourceBlueprint);
assert.notEqual(applied, sourceBlueprint, "generation must receive a copied Blueprint");
assert.notEqual(applied.base_sketch, sourceBlueprint.base_sketch, "base sketch must be copied");
assert.notEqual(applied.features, sourceBlueprint.features, "feature list must be copied");
assert.equal(applied.base_sketch.outer_diameter, 80, "8 cm must be normalized to 80 mm");
assert.equal(applied.features[0].count, 6, "saved count must update its selected feature");
assert.equal(applied.features[0].start_angle, 45, "saved angle must update its selected feature");
assert.equal(applied.features[0].diameter, 5, "unsaved mappings must never reach geometry");
assert.equal(applied.base_sketch.thickness, 10, "pending mappings must never reach geometry");
assert.equal(applied.base_sketch.wall_thickness, 2.5, "unsupported units must never reach geometry");
assert.equal(applied.needs_review, true, "applied measurements must keep the Blueprint in review state");

// Source drawing evidence and stored Blueprint geometry must remain byte-for-byte unchanged.
assert.equal(sourceBlueprint.base_sketch.outer_diameter, 90);
assert.equal(sourceBlueprint.features[0].count, 4);
assert.equal(sourceBlueprint.features[0].start_angle, 0);
assert.equal(sourceBlueprint.visual_measurements[0].reviewedValue, 8);
assert.equal(sourceBlueprint.base_sketch.thickness_is_default, true);
assert.equal(sourceBlueprint.base_sketch.wall_thickness_is_default, true);

console.log("PASS: confirmed/saved CAD bindings apply to a copy, normalize units, preserve source Blueprint evidence, and ignore pending, unsaved or invalid candidates");
