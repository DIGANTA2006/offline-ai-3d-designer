import assert from "node:assert/strict";
import { createRequire, Module } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync } from "node:fs";

const require = createRequire(import.meta.url);
const ts = require(resolve(process.cwd(), "node_modules/typescript"));
const here = dirname(fileURLToPath(import.meta.url));
const sourcePath = resolve(here, "../src/lib/upload/ocr-source-support.ts");
const source = readFileSync(sourcePath, "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  reportDiagnostics: true,
});
const errors = (output.diagnostics ?? []).filter((item) => item.category === ts.DiagnosticCategory.Error);
assert.equal(errors.length, 0, "OCR source support helper must transpile");

const loaded = new Module(sourcePath);
loaded.filename = sourcePath;
loaded.paths = Module._nodeModulePaths(dirname(sourcePath));
loaded._compile(output.outputText, sourcePath);
const { isOcrSourceFile } = loaded.exports;

// Server-validated MIME metadata must work even when storage names are opaque.
assert.equal(isOcrSourceFile({ name: "random-upload-id", contentType: "image/jpeg", type: "image" }), true);
assert.equal(isOcrSourceFile({ name: "untitled", contentType: "application/pdf; charset=binary", type: "pdf" }), true);
assert.equal(isOcrSourceFile({ name: "scan", contentType: "image/webp", type: "image" }), true);

// MIME metadata wins over misleading filenames and generic image categories.
assert.equal(isOcrSourceFile({ name: "misleading.jpg", contentType: "text/plain", type: "image" }), false);
assert.equal(isOcrSourceFile({ name: "scan.tiff", contentType: "image/tiff", type: "image" }), false);
assert.equal(isOcrSourceFile({ name: "photo.bmp", contentType: "image/bmp", type: "image" }), false);

// Legacy stored versions fall back to supported extension metadata only.
assert.equal(isOcrSourceFile({ name: "legacy.jpg" }), true);
assert.equal(isOcrSourceFile({ name: "legacy.PDF" }), true);
assert.equal(isOcrSourceFile({ name: "legacy.webp" }), true);
assert.equal(isOcrSourceFile({ name: "drawing.dxf", contentType: "application/octet-stream", type: "dxf" }), false);
assert.equal(isOcrSourceFile({ name: "mystery", contentType: "application/octet-stream" }), false);

console.log("PASS: OCR source filtering uses validated PDF/PNG/JPEG/WebP metadata, preserves legacy fallback, and excludes unsupported/DXF uploads.");
