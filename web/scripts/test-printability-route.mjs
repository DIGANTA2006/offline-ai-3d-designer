import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire, Module } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const ts = require(resolve(process.cwd(), "node_modules/typescript"));
const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, "..");
const routePath = resolve(webRoot, "src/app/api/projects/[projectId]/printability/route.ts");

function loadTypeScriptModule(filePath, overrides = {}) {
  const source = readFileSync(filePath, "utf8");
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
  assert.equal(errors.length, 0, `TypeScript transpilation failed for ${filePath}`);

  const loaded = new Module(filePath);
  loaded.filename = filePath;
  loaded.paths = Module._nodeModulePaths(dirname(filePath));
  const nativeRequire = createRequire(filePath);
  loaded.require = (id) => Object.hasOwn(overrides, id) ? overrides[id] : nativeRequire(id);
  loaded._compile(output.outputText, filePath);
  return loaded.exports;
}

const calls = { backend: [] };
let currentUser = { id: "user-1", role: "USER" };
let sameOrigin = true;
let projectExists = true;
let versionRecord = {
  id: "version-1",
  version: 3,
  stepFilePath: "private/part.step",
  stlFilePath: "private/part.stl",
  spec: {
    partSpec: {
      name: "Saved test box",
      features: [{ id: "base", type: "box", parameters: {} }],
    },
  },
};
let paidAccess = { allowed: true };
let backendStatus = 200;
let backendBody = {
  success: true,
  checks: [],
  summary: { total: 0, pass: 0, fail: 0, warning: 0, skipped: 0 },
};

const prisma = {
  project: {
    findFirst: async () => projectExists ? { id: "project-1" } : null,
  },
  projectVersion: {
    findFirst: async () => versionRecord,
  },
};

const stubs = {
  "next/server": {
    NextResponse: { json: (data, init) => Response.json(data, init) },
  },
  "@/lib/auth/server": {
    getCurrentUser: async () => currentUser,
  },
  "@/lib/security/same-origin": {
    isSameOriginRequest: () => sameOrigin,
  },
  "@/lib/prisma": { prisma },
  "@/lib/cad-service-config": {
    getCadServiceConfig: () => ({ baseUrl: "https://cad.example.test", token: "test-service-token" }),
  },
  "@/lib/billing/paid-access": {
    checkPaidFeatureAccess: async () => paidAccess,
  },
};

const originalFetch = globalThis.fetch;
const originalNodeEnv = process.env.NODE_ENV;
process.env.NODE_ENV = "test";
globalThis.fetch = async (input, init) => {
  calls.backend.push({
    url: String(input),
    method: init?.method,
    headers: init?.headers,
    body: typeof init?.body === "string" ? JSON.parse(init.body) : null,
  });
  return Response.json(backendBody, { status: backendStatus });
};

const route = loadTypeScriptModule(routePath, stubs);
const params = { params: Promise.resolve({ projectId: "project-1" }) };

function getRequest(path = "http://localhost/api/projects/project-1/printability") {
  return new Request(path, { method: "GET" });
}

function postRequest(body) {
  return new Request("http://localhost/api/projects/project-1/printability", {
    method: "POST",
    headers: { "content-type": "application/json", origin: "http://localhost" },
    body: JSON.stringify(body),
  });
}

try {
  // Unauthenticated calls must not reach the private CAD service.
  currentUser = null;
  let response = await route.GET(getRequest(), params);
  assert.equal(response.status, 401);
  assert.equal(calls.backend.length, 0);

  // A project ID owned by another account must not disclose a saved PartSpec.
  currentUser = { id: "user-1", role: "USER" };
  projectExists = false;
  response = await route.GET(getRequest(), params);
  assert.equal(response.status, 404);
  assert.equal(calls.backend.length, 0);
  projectExists = true;

  // A version without a real stored CAD spec must be rejected before proxying.
  versionRecord = { ...versionRecord, spec: { uploadedFiles: [] } };
  response = await route.GET(getRequest(), params);
  assert.equal(response.status, 422);
  assert.equal(calls.backend.length, 0);
  versionRecord = {
    ...versionRecord,
    spec: {
      partSpec: {
        name: "Saved test box",
        features: [{ id: "base", type: "box", parameters: {} }],
      },
    },
  };

  // A saved drawing-generated PartSpec is passed to the service, not browser-supplied geometry.
  backendStatus = 200;
  backendBody = {
    success: true,
    checks: [{ check_id: "min_wall_thickness", status: "pass", available_fixes: [] }],
    summary: { total: 1, pass: 1, fail: 0, warning: 0, skipped: 0 },
  };
  response = await route.GET(getRequest(), params);
  let body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.versionId, "version-1");
  assert.equal(body.versionNumber, 3);
  assert.equal(body.partSpecName, "Saved test box");
  assert.equal(calls.backend.at(-1).url, "https://cad.example.test/api/v1/printability/check");
  assert.equal(calls.backend.at(-1).body.partSpec.name, "Saved test box");
  assert.equal(calls.backend.at(-1).headers.Authorization, "Bearer test-service-token");

  // Drawing-generated versions store a Blueprint schema, not the legacy PartSpec.
  // Route them to the geometry-native checker without relabeling the payload.
  const savedBlueprint = {
    part_name: "Drawing flange",
    primary_body_type: "rotational_flange",
    base_sketch: {
      profile: "circle",
      outer_diameter: 40,
      thickness: 10,
      thickness_is_default: true,
      wall_thickness_is_default: false,
    },
    features: [],
    unsupported_geometry: [],
    needs_review: true,
  };
  const confirmedProvisionalDefaults = [{
    field: "base_sketch.thickness",
    value: 10,
    unit: "mm",
    source: "provisional_default",
    confirmedBy: "user-1",
    confirmedAt: "2026-11-07T15:00:00.000Z",
  }];
  versionRecord = {
    ...versionRecord,
    spec: {
      reviewedBlueprint: savedBlueprint,
      partSpec: savedBlueprint,
      confirmedProvisionalDefaults,
    },
  };
  backendBody = {
    success: true,
    checks: [{ check_id: "min_wall_thickness", status: "pass", available_fixes: [] }],
    summary: { total: 1, pass: 1, fail: 0, warning: 0, skipped: 0 },
    notices: ["Checks ran against the saved drawing blueprint."],
  };
  response = await route.GET(getRequest(), params);
  body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.partSpecName, "Drawing flange");
  assert.equal(body.sourceGeometryType, "blueprint");
  assert.equal(calls.backend.at(-1).url, "https://cad.example.test/api/v1/printability/check-blueprint");
  assert.deepEqual(calls.backend.at(-1).body.blueprint, savedBlueprint);
  assert.equal(calls.backend.at(-1).body.partSpec, undefined);
  assert.ok(body.notices.some((notice) => notice.includes("remains a provisional default") && notice.includes("explicit confirmation")));
  assert.ok(body.notices.some((notice) => notice.includes("flagged as needing review")));

  // Older saved versions may contain a provisional default without PR #20 confirmation provenance.
  // Geometry checks may still run, but the response must not imply that the dimension was approved.
  versionRecord.spec.confirmedProvisionalDefaults = [];
  response = await route.GET(getRequest(), params);
  body = await response.json();
  assert.equal(response.status, 200);
  assert.ok(body.notices.some((notice) => notice.includes("no matching user-confirmation record")));
  assert.ok(body.notices.some((notice) => notice.includes("does not approve this value")));

  // Drawing-blueprint fixes must remain disabled until they can safely rebuild the blueprint.
  const beforeBlueprintFix = calls.backend.length;
  response = await route.POST(postRequest({
    versionId: "version-1",
    action: "rotate",
    checkId: "bed_fit_posZ_upright",
  }), params);
  body = await response.json();
  assert.equal(response.status, 409);
  assert.match(body.error, /One-click fixes for drawing blueprints are not enabled/);
  assert.equal(calls.backend.length, beforeBlueprintFix);

  // Restore a canonical PartSpec version for legacy mutation tests.
  versionRecord = {
    ...versionRecord,
    spec: {
      partSpec: {
        name: "Saved test box",
        features: [{ id: "base", type: "box", parameters: {} }],
      },
    },
  };

  // Mutations require same-origin protection.
  sameOrigin = false;
  response = await route.POST(postRequest({
    versionId: "version-1",
    action: "rotate",
    checkId: "bed_fit_posZ_upright",
  }), params);
  assert.equal(response.status, 403);
  sameOrigin = true;

  // Subscription entitlement remains enforced by the shared policy helper.
  paidAccess = { allowed: false, status: 402, message: "Pro required." };
  response = await route.GET(getRequest(), params);
  assert.equal(response.status, 402);
  paidAccess = { allowed: true };

  // Fixes are previews only: the saved project row and version are never updated.
  backendBody = {
    success: true,
    result: {
      action: "rotate",
      check_id: "bed_fit_posZ_upright",
      modified_spec: { name: "Saved test box", features: [] },
      new_checks: [{ check_id: "bed_fit_posX_on_side", status: "pass", details: "Fits." }],
    },
    notices: [],
  };
  response = await route.POST(postRequest({
    versionId: "version-1",
    action: "rotate",
    checkId: "bed_fit_posZ_upright",
  }), params);
  body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.proposalOnly, true);
  assert.equal(body.result.action, "rotate");
  assert.ok(body.notices.some((item) => item.includes("has not changed")));
  assert.equal(calls.backend.at(-1).url, "https://cad.example.test/api/v1/printability/fix");

  // An old backend with no mounted printability router should be reported as not deployed.
  backendStatus = 404;
  backendBody = { detail: "Not Found" };
  response = await route.GET(getRequest(), params);
  body = await response.json();
  assert.equal(response.status, 503);
  assert.match(body.error, /does not yet expose printability endpoints/);

  console.log("PASS: printability route enforces authentication, project ownership, paid access, same-origin mutation checks, saved-spec sourcing, backend token proxying, and review-only fix semantics.");
} finally {
  globalThis.fetch = originalFetch;
  if (originalNodeEnv === undefined) delete process.env.NODE_ENV;
  else process.env.NODE_ENV = originalNodeEnv;
}
