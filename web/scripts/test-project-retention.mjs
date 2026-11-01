import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
import { dirname, resolve, join } from "node:path";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const here = dirname(fileURLToPath(import.meta.url));
const sourcePath = resolve(here, "../src/lib/project-retention-core.ts");
const source = readFileSync(sourcePath, "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true },
});
const scratchDir = mkdtempSync(join(tmpdir(), "project-retention-test-"));

try {
  const compiledPath = join(scratchDir, "project-retention-core.cjs");
  writeFileSync(compiledPath, compiled.outputText, { encoding: "utf8", flag: "wx" });
  const core = require(compiledPath);
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

  assert.equal(core.FREE_PROJECT_LIMIT, 1, "the free plan includes one saved project");
  assert.equal(core.canCreateProject(0, false), true, "the first project is allowed on the free plan");
  assert.equal(core.canCreateProject(1, false), false, "a second project is blocked on the free plan");
  assert.equal(core.canCreateProject(25, true), true, "Pro accounts are not capped");

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
  console.log("PASS: retention compaction, stable array indexes, one-project free cap and protected-output policy");
} finally {
  rmSync(scratchDir, { recursive: true, force: true });
}
