import assert from "node:assert/strict";
import { createRequire, Module } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const ts = require(resolve(process.cwd(), "node_modules/typescript"));
const here = dirname(fileURLToPath(import.meta.url));
const routePath = resolve(here, "../src/app/api/projects/[projectId]/drawing-review/route.ts");

const calls = { updates: 0, audits: 0, originAllowed: true, currentUser: { id: "user-owner" } };
let updatedSpec = null;
const project = {
  id: "project-1",
  versions: [{
    id: "version-1",
    version: 2,
    spec: {
      uploadedFiles: [{ name: "drawing.png", pathname: "private/drawing.png" }],
      ocrResults: [{
        fileIndex: 0,
        name: "drawing.png",
        spec: {
          rawText: "OD 80 mm, angle 30 deg",
          blueprint: {
            visual_measurements: [
              { dimension_name: "outer diameter", raw_callout: "Ø80", value: 80, unit: "mm", kind: "diameter", source_page: 1 },
              { dimension_name: "included angle", raw_callout: "30°", value: 30, unit: "deg", kind: "angle", source_page: 1 },
              { dimension_name: "hole count", raw_callout: "6X", value: 6, unit: "unknown", kind: "count", source_page: 1 },
            ],
          },
        },
      }],
    },
  }],
};

const prisma = {
  project: {
    findFirst: async (args) => {
      assert.equal(args.where.userId, "user-owner", "project lookup must be scoped to the authenticated owner");
      return project;
    },
  },
  projectVersion: {
    update: async ({ data }) => {
      calls.updates += 1;
      updatedSpec = data.spec;
      project.versions[0].spec = data.spec;
      return { id: "version-1" };
    },
  },
  auditLog: {
    create: async () => { calls.audits += 1; return {}; },
  },
};

const overrides = {
  "next/server": { NextResponse: { json: (body, init) => Response.json(body, init) } },
  "@/lib/auth/server": { getCurrentUser: async () => calls.currentUser },
  "@/lib/security/same-origin": { isSameOriginRequest: () => calls.originAllowed },
  "@/lib/prisma": { prisma },
  "@/lib/project-retention": { compactStoredJson: (value) => value },
  "@/lib/billing/paid-access": {
    checkPaidFeatureAccess: async () => ({ allowed: true, status: 200, message: "" }),
  },
};

function loadRoute() {
  const source = require("node:fs").readFileSync(routePath, "utf8");
  const output = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
      moduleResolution: ts.ModuleResolutionKind.Node10,
      esModuleInterop: true,
      strict: true,
    },
    reportDiagnostics: true,
  });
  const errors = (output.diagnostics ?? []).filter((item) => item.category === ts.DiagnosticCategory.Error);
  assert.equal(errors.length, 0, "measurement review route must transpile");

  const loaded = new Module(routePath);
  loaded.filename = routePath;
  loaded.paths = Module._nodeModulePaths(dirname(routePath));
  const nativeRequire = createRequire(routePath);
  loaded.require = (id) => Object.hasOwn(overrides, id) ? overrides[id] : nativeRequire(id);
  loaded._compile(output.outputText, routePath);
  return loaded.exports;
}

async function send(body) {
  const { POST } = loadRoute();
  return POST(
    new Request("http://localhost/api/projects/project-1/drawing-review", {
      method: "POST",
      headers: { "Content-Type": "application/json", Origin: "http://localhost" },
      body: JSON.stringify(body),
    }),
    { params: Promise.resolve({ projectId: "project-1" }) },
  );
}

const { POST } = loadRoute();
const originalBlueprint = JSON.stringify(project.versions[0].spec.ocrResults[0].spec.blueprint);

try {
  calls.originAllowed = false;
  const originResponse = await POST(
    new Request("http://localhost/api/projects/project-1/drawing-review", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fileIndex: 0, reviews: [] }),
    }),
    { params: Promise.resolve({ projectId: "project-1" }) },
  );
  assert.equal(originResponse.status, 403);
  calls.originAllowed = true;

  const good = await send({
    fileIndex: 0,
    reviews: [
      { measurementIndex: 0, decision: "confirmed_reading", value: 80, unit: "mm", featureDescription: "outer circular edge" },
      { measurementIndex: 1, decision: "confirmed_reading", value: 30, unit: "deg", featureDescription: "included angle" },
      { measurementIndex: 2, decision: "confirmed_reading", value: 6, unit: "count", featureDescription: "repeated holes" },
    ],
  });
  const goodPayload = await good.json();
  assert.equal(good.status, 200);
  assert.equal(goodPayload.confirmedCount, 3);
  assert.equal(goodPayload.rejectedCount, 0);
  assert.equal(calls.updates, 1);
  assert.equal(calls.audits, 1);

  const record = updatedSpec.ocrResults[0];
  assert.equal(record.visualMeasurementReviews[0].reviewedBy, "user-owner");
  assert.ok(record.visualMeasurementReviews[0].reviewedAt);
  assert.equal(record.spec.blueprint.visual_measurements[0].value, 80, "OCR evidence must remain unchanged");
  assert.equal(JSON.stringify(record.spec.blueprint), originalBlueprint, "review decisions must not mutate the source Blueprint");

  const duplicate = await send({
    fileIndex: 0,
    reviews: [
      { measurementIndex: 0, decision: "rejected" },
      { measurementIndex: 0, decision: "rejected" },
    ],
  });
  assert.equal(duplicate.status, 400, "duplicate candidate reviews must be rejected");
  assert.equal(calls.updates, 1, "invalid requests must not write project data");

  const incompatibleUnit = await send({
    fileIndex: 0,
    reviews: [{ measurementIndex: 0, decision: "confirmed_reading", value: 80, unit: "deg" }],
  });
  assert.equal(incompatibleUnit.status, 422, "diameters cannot be confirmed in angular units");
  assert.equal(calls.updates, 1);

  const unknownIndex = await send({
    fileIndex: 0,
    reviews: [{ measurementIndex: 99, decision: "rejected" }],
  });
  assert.equal(unknownIndex.status, 422, "candidate indices must refer to stored source evidence");
  assert.equal(calls.updates, 1);

  console.log("PASS: measurement reviews are owner-scoped, same-origin protected, type/unit validated, audited, and stored separately from immutable OCR evidence");
} finally {
  // No external state or credentials are changed by this test.
}
