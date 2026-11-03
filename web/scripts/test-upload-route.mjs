import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire, Module } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const ts = require(resolve(process.cwd(), "node_modules/typescript"));
const here = dirname(fileURLToPath(import.meta.url));
const projectRoot = resolve(here, "..", "..");
const webRoot = resolve(projectRoot, "web");
const routePath = resolve(webRoot, "src/app/api/upload/route.ts");
const validationPath = resolve(webRoot, "src/lib/upload/validation.ts");

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
  const errors = (output.diagnostics ?? []).filter((diagnostic) => diagnostic.category === ts.DiagnosticCategory.Error);
  assert.equal(errors.length, 0, `TypeScript transpilation failed for ${filePath}`);

  const loaded = new Module(filePath);
  loaded.filename = filePath;
  loaded.paths = Module._nodeModulePaths(dirname(filePath));
  const nativeRequire = createRequire(filePath);
  loaded.require = (id) => Object.hasOwn(overrides, id) ? overrides[id] : nativeRequire(id);
  loaded._compile(output.outputText, filePath);
  return loaded.exports;
}

const validation = loadTypeScriptModule(validationPath);
const calls = {
  capacityChecks: 0,
  projectCreates: 0,
  blobPuts: [],
  versionCreates: 0,
  audits: 0,
};

class ProjectCapacityError extends Error {}
const prisma = {
  projectVersion: {
    create: async () => {
      calls.versionCreates += 1;
      return { id: "version-test", version: 1 };
    },
  },
  auditLog: {
    create: async () => {
      calls.audits += 1;
      return {};
    },
  },
  project: {
    delete: async () => ({}),
    update: async () => ({}),
  },
};

const stubs = {
  "@vercel/blob": {
    put: async (pathname) => {
      calls.blobPuts.push(pathname);
      return { pathname };
    },
    del: async () => ({}),
  },
  "next/server": {
    NextResponse: { json: (data, init) => Response.json(data, init) },
  },
  "@/lib/auth/server": {
    getCurrentUser: async () => ({ id: "user-test" }),
  },
  "@/lib/security/same-origin": {
    isSameOriginRequest: () => true,
  },
  "@/lib/upload/validation": validation,
  "@/lib/prisma": { prisma },
  "@/lib/project-retention": {
    assertProjectCapacity: async () => {
      calls.capacityChecks += 1;
    },
    createProjectWithCapacity: async () => {
      calls.projectCreates += 1;
      return { id: `project-${calls.projectCreates}` };
    },
    ProjectCapacityError,
  },
};

const originalToken = process.env.PRIVATE_BLOB_READ_WRITE_TOKEN;
process.env.PRIVATE_BLOB_READ_WRITE_TOKEN = "test-private-blob-token";

function validPdfFile(name = "valid.pdf") {
  const bytes = Buffer.from("%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n", "ascii");
  return new File([bytes], name, { type: "application/pdf" });
}

function invalidPdfFile(name = "fake.pdf") {
  const bytes = Buffer.from("MZ\x00\x00not a PDF", "ascii");
  return new File([bytes], name, { type: "application/pdf" });
}

async function postFiles(files) {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  const request = new Request("http://localhost/api/upload", {
    method: "POST",
    body: form,
  });
  const { POST } = loadTypeScriptModule(routePath, stubs);
  return POST(request);
}

try {
  // All-invalid files must be rejected before project creation or private storage.
  const invalidResponse = await postFiles([invalidPdfFile()]);
  const invalidBody = await invalidResponse.json();
  assert.equal(invalidResponse.status, 400);
  assert.equal(invalidBody.error, "No supported files were found.");
  assert.equal(calls.projectCreates, 0, "an all-invalid batch must not create a project");
  assert.equal(calls.blobPuts.length, 0, "an all-invalid batch must never reach Blob storage");
  assert.equal(calls.versionCreates, 0, "an all-invalid batch must not create a project version");

  // A mixed batch must store only valid files and report rejected files to the caller.
  const mixedResponse = await postFiles([
    validPdfFile(),
    invalidPdfFile("renamed-invalid.pdf"),
  ]);
  const mixedBody = await mixedResponse.json();
  assert.equal(mixedResponse.status, 201);
  assert.equal(calls.projectCreates, 1);
  assert.equal(calls.blobPuts.length, 1, "only the valid file may be uploaded");
  assert.match(calls.blobPuts[0], /valid\.pdf$/);
  assert.equal(mixedBody.uploadedFiles.length, 1);
  assert.equal(mixedBody.rejected.length, 1);
  assert.equal(mixedBody.rejected[0].name, "renamed-invalid.pdf");
  assert.equal(calls.versionCreates, 1);
  assert.equal(calls.audits, 1);

  console.log("PASS: actual upload POST route rejects all-invalid batches before project creation/Blob storage and stores only valid files from mixed batches");
} finally {
  if (originalToken === undefined) delete process.env.PRIVATE_BLOB_READ_WRITE_TOKEN;
  else process.env.PRIVATE_BLOB_READ_WRITE_TOKEN = originalToken;
}
