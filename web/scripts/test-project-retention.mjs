import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const here = dirname(fileURLToPath(import.meta.url));
const sourcePath = resolve(here, "../src/lib/project-retention-core.ts");
const source = readFileSync(sourcePath, "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true },
});
const moduleObject = { exports: {} };
const sandbox = { module: moduleObject, exports: moduleObject.exports };
vm.runInNewContext(compiled.outputText, sandbox, { filename: "project-retention-core.cjs" });
const core = moduleObject.exports;
const localJson = (value) => JSON.parse(JSON.stringify(value));

const largeBase64 = Buffer.alloc(300_000, 0x61).toString("base64");
const compacted = localJson(core.compactStoredJson({
  inputText: "M8 plate, 134 mm diameter",
  stepBase64: largeBase64,
  source: { dataUrl: "data:image/png;base64,AAAA", label: "drawing.png" },
  vertices: [1, 2, 3],
  faces: [[0, 1, 2]],
  ocrResults: [
    { fileIndex: 0, rawText: "OD 134", imagePayload: largeBase64 },
    { fileIndex: 1, rawText: "Ø80", imagePayload: largeBase64 },
  ],
  candidatePayloads: ["keep-before", largeBase64, "keep-after"],
}));
assert.equal(compacted.inputText, "M8 plate, 134 mm diameter");
assert.equal("stepBase64" in compacted, false);
assert.equal("vertices" in compacted, false);
assert.equal("faces" in compacted, false);
assert.equal("dataUrl" in compacted.source, false);
assert.deepEqual(compacted.ocrResults.map((item) => item.fileIndex), [0, 1]);
assert.equal("imagePayload" in compacted.ocrResults[0], false);
assert.deepEqual(compacted.candidatePayloads, ["keep-before", null, "keep-after"]);

const projectsOldestFirst = [
  { id: "old-a", isImportant: false, status: "DRAFT" },
  { id: "old-important", isImportant: true, status: "SUCCEEDED" },
  { id: "processing", isImportant: false, status: "PROCESSING" },
  { id: "queued", isImportant: false, status: "QUEUED" },
  { id: "old-b", isImportant: false, status: "FAILED" },
  { id: "middle", isImportant: false, status: "SUCCEEDED" },
  { id: "pinned-mid", isImportant: true, status: "SUCCEEDED" },
  { id: "next", isImportant: false, status: "DRAFT" },
  { id: "recent-a", isImportant: false, status: "SUCCEEDED" },
  { id: "recent-b", isImportant: false, status: "SUCCEEDED" },
  { id: "recent-c", isImportant: false, status: "DRAFT" },
  { id: "current", isImportant: false, status: "SUCCEEDED" },
];
assert.deepEqual(
  localJson(core.selectProjectIdsToPrune(projectsOldestFirst, { excludeProjectId: "current" })),
  ["old-a", "old-b"],
  "pruning must remove the oldest eligible projects while preserving important, active and current ones",
);
assert.deepEqual(core.selectProjectIdsToPrune(projectsOldestFirst.slice(0, 10)), []);

const versionsNewestFirst = [
  { id: "v8", isProtected: true },
  { id: "v7", isProtected: false },
  { id: "v6", isProtected: false },
  { id: "v5", isProtected: false },
  { id: "v4", isProtected: true },
  { id: "v3", isProtected: false },
];
assert.deepEqual(
  localJson(core.selectUnprotectedVersionIdsToPrune(versionsNewestFirst)),
  ["v5", "v3"],
  "keep two newest unprotected outputs plus every protected output",
);

console.log("PASS: retention compaction, stable array indexes, ten-project cap and protected-output policy");
