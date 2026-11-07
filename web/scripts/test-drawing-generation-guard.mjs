import assert from "node:assert/strict";
import { createRequire, Module } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const ts = require(resolve(process.cwd(), "node_modules/typescript"));
const here = dirname(fileURLToPath(import.meta.url));
const routePath = resolve(here, "../src/app/api/projects/[projectId]/generate-from-drawing/route.ts");

const calls = { usageReservations: 0, cadFetches: 0 };
const project = {
  id: "project-test",
  versions: [{
    id: "source-version",
    version: 1,
    spec: {
      uploadedFiles: [{ name: "test-drawing.jpg", pathname: "private/source.jpg", contentType: "image/jpeg" }],
      ocrResults: [{
        fileIndex: 0,
        name: "test-drawing.jpg",
        spec: { rawText: "low-confidence drawing text", confidence: 0.28 },
      }],
    },
  }],
};

const prisma = {
  project: {
    findFirst: async () => project,
    update: async () => ({ id: project.id }),
  },
  usageRecord: {
    upsert: async () => { calls.usageReservations += 1; return {}; },
    updateMany: async () => { calls.usageReservations += 1; return { count: 1 }; },
  },
};

const overrides = {
  "@vercel/blob": {
    put: async () => { throw new Error("Blob storage must not be reached for a drawing with no blueprint."); },
    del: async () => ({}),
  },
  "next/server": {
    NextResponse: { json: (body, init) => Response.json(body, init) },
  },
  "@/lib/auth/server": {
    getCurrentUser: async () => ({ id: "user-test", role: "USER" }),
  },
  "@/lib/security/same-origin": {
    isSameOriginRequest: () => true,
  },
  "@/lib/prisma": { prisma },
  "@/lib/cad-service-config": {
    getCadServiceConfig: () => ({ baseUrl: "https://cad.example.test", token: "test-service-token" }),
  },
  "@/lib/project-retention": {
    compactStoredJson: (value) => value,
    pruneProjectVersions: async () => [],
  },
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
  assert.equal(errors.length, 0, "drawing generation route must transpile");

  const loaded = new Module(routePath);
  loaded.filename = routePath;
  loaded.paths = Module._nodeModulePaths(dirname(routePath));
  const nativeRequire = createRequire(routePath);
  loaded.require = (id) => Object.hasOwn(overrides, id) ? overrides[id] : nativeRequire(id);
  loaded._compile(output.outputText, routePath);
  return loaded.exports;
}

const previousBlobToken = process.env.PRIVATE_BLOB_READ_WRITE_TOKEN;
process.env.PRIVATE_BLOB_READ_WRITE_TOKEN = "test-private-blob-token";
const originalFetch = globalThis.fetch;
globalThis.fetch = async () => {
  calls.cadFetches += 1;
  throw new Error("CAD service must not be called for a drawing with no saved blueprint.");
};

try {
  const { POST } = loadRoute();
  const request = new Request("http://localhost/api/projects/project-test/generate-from-drawing", {
    method: "POST",
    headers: { "Content-Type": "application/json", Origin: "http://localhost" },
    body: JSON.stringify({
      fileIndex: 0,
      reviewed: true,
      reviewedDescription: "A user-entered description that must not silently replace the source drawing",
    }),
  });
  const response = await POST(request, { params: Promise.resolve({ projectId: "project-test" }) });
  const payload = await response.json();

  assert.equal(response.status, 409, "drawing generation without a saved blueprint must be rejected");
  assert.match(payload.error, /no saved structured blueprint/i);
  assert.equal(calls.usageReservations, 0, "rejection must happen before generation usage is reserved");
  assert.equal(calls.cadFetches, 0, "rejection must happen before the CAD service is called");

  console.log("PASS: drawing generation rejects missing saved blueprints before usage reservation, storage, or CAD service calls");
} finally {
  globalThis.fetch = originalFetch;
  if (previousBlobToken === undefined) delete process.env.PRIVATE_BLOB_READ_WRITE_TOKEN;
  else process.env.PRIVATE_BLOB_READ_WRITE_TOKEN = previousBlobToken;
}
