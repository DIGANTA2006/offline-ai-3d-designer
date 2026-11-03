import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { File } from "node:buffer";
import { fileURLToPath } from "node:url";
import { dirname, resolve, join } from "node:path";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const here = dirname(fileURLToPath(import.meta.url));
const sourcePath = resolve(here, "../src/lib/upload/validation.ts");
const source = readFileSync(sourcePath, "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS, strict: true },
});
const scratchDir = mkdtempSync(join(tmpdir(), "upload-validation-test-"));

function createPng() {
  const bytes = Buffer.alloc(33);
  Buffer.from([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]).copy(bytes, 0);
  bytes.writeUInt32BE(13, 8);
  bytes.write("IHDR", 12, "ascii");
  return bytes;
}

function createWebp() {
  const bytes = Buffer.alloc(30);
  bytes.write("RIFF", 0, "ascii");
  bytes.writeUInt32LE(22, 4);
  bytes.write("WEBP", 8, "ascii");
  bytes.write("VP8X", 12, "ascii");
  bytes.writeUInt32LE(10, 16);
  return bytes;
}

const asciiDxf = Buffer.from([
  "0", "SECTION", "2", "HEADER", "9", "$ACADVER", "1", "AC1027",
  "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES", "0", "LINE",
  "8", "0", "10", "0.0", "20", "0.0", "11", "10.0", "21", "10.0",
  "0", "ENDSEC", "0", "EOF", "",
].join("\n"), "utf8");
const binaryDxf = Buffer.concat([
  Buffer.from("AutoCAD Binary DXF\r\n\x1a\x00", "binary"),
  Buffer.from([0x00, 0x01, 0x02, 0x03]),
]);

const fixtures = {
  pdf: Buffer.from("%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n", "ascii"),
  png: createPng(),
  jpeg: Buffer.from([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0xFF, 0xD9]),
  webp: createWebp(),
  dxf: asciiDxf,
};

const mimeByFormat = {
  pdf: "application/pdf",
  png: "image/png",
  jpeg: "image/jpeg",
  webp: "image/webp",
  dxf: "application/dxf",
};

const makeFile = (name, type, content) => new File([content], name, { type });

try {
  const compiledPath = join(scratchDir, "upload-validation.cjs");
  writeFileSync(compiledPath, compiled.outputText, { encoding: "utf8", flag: "wx" });
  const validation = require(compiledPath);

  for (const [format, content] of Object.entries(fixtures)) {
    const extension = format === "jpeg" ? "jpg" : format;
    const result = await validation.validateFileWithContent(
      makeFile(`drawing.${extension}`, mimeByFormat[format], content),
    );
    assert.equal(result.ok, true, `${format} fixture should pass: ${result.reason ?? ""}`);
    assert.equal(result.type, format === "pdf" ? "pdf" : format === "dxf" ? "dxf" : "image");
  }

  const binaryResult = await validation.validateFileWithContent(makeFile("binary.dxf", "application/dxf", binaryDxf));
  assert.equal(binaryResult.ok, true, `binary DXF should pass: ${binaryResult.reason ?? ""}`);

  const noMimeResult = await validation.validateFileWithContent(makeFile("drawing.pdf", "", fixtures.pdf));
  assert.equal(noMimeResult.ok, true, "empty browser MIME is allowed when extension and content agree");
  const genericMimeResult = await validation.validateFileWithContent(makeFile("drawing.pdf", "application/octet-stream", fixtures.pdf));
assert.equal(
  genericMimeResult.ok,
  true,
  "generic octet-stream MIME is allowed when content proves the format",
);
  const plainText = makeFile("notes.txt", "text/plain", asciiDxf);
  assert.equal(validation.getFileType(plainText),null,"ordinary text files must not be classified as DXF",);
  const plainTextValidation = await validation.validateFileWithContent(plainText);
  assert.equal(plainTextValidation.ok, false);

  const fakeExecutable = await validation.validateFileWithContent(
    makeFile("renamed.pdf", "application/pdf", Buffer.from("MZ\x00\x00not a PDF", "ascii")),
  );
  assert.equal(fakeExecutable.ok, false, "an allowed extension alone must not authorize arbitrary bytes");

  const extensionMismatch = await validation.validateFileWithContent(
    makeFile("renamed.png", "image/png", fixtures.jpeg),
  );
  assert.equal(extensionMismatch.ok, false, "JPEG bytes renamed as PNG must be rejected");
  assert.match(extensionMismatch.reason ?? "", /extension .* does not match/i);

  const mimeMismatch = await validation.validateFileWithContent(
    makeFile("drawing.png", "image/jpeg", fixtures.png),
  );
  assert.equal(mimeMismatch.ok, false, "a conflicting non-generic MIME must be rejected");
  assert.match(mimeMismatch.reason ?? "", /MIME type .* conflicts/i);

  const empty = await validation.validateFileWithContent(makeFile("empty.pdf", "application/pdf", Buffer.alloc(0)));
  assert.equal(empty.ok, false, "empty files must be rejected");

  const unsupported = await validation.validateFileWithContent(makeFile("payload.exe", "application/octet-stream", Buffer.from("MZ")));
  assert.equal(unsupported.ok, false, "unsupported extensions must be rejected");

  const invalidDxf = await validation.validateFileWithContent(
    makeFile("not-a-drawing.dxf", "application/dxf", Buffer.from("ordinary text, not DXF", "utf8")),
  );
  assert.equal(invalidDxf.ok, false, "plain text without DXF structure must be rejected");

  const batch = await validation.validateFilesWithContent([
    makeFile("valid.pdf", "application/pdf", fixtures.pdf),
    makeFile("fake.pdf", "application/pdf", Buffer.from("not a PDF", "ascii")),
  ]);
  assert.equal(batch.valid.length, 1);
  assert.equal(batch.rejected.length, 1);
  assert.equal(batch.valid[0].file.name, "valid.pdf");
  assert.equal(batch.rejected[0].file.name, "fake.pdf");

  const emptyBatch = await validation.validateFilesWithContent([
    makeFile("fake.pdf", "application/pdf", Buffer.from("not a PDF", "ascii")),
  ]);
  assert.equal(emptyBatch.valid.length, 0, "no invalid file may remain uploadable");
  assert.equal(emptyBatch.rejected.length, 1);

  const oversized = await validation.validateFileWithContent(
    makeFile("large.pdf", "application/pdf", Buffer.alloc(3 * 1024 * 1024 + 1, 0x41)),
  );
  assert.equal(oversized.ok, false, "the 3 MiB per-file limit must remain enforced");

  const routePath = resolve(here, "../src/app/api/upload/route.ts");
  const route = readFileSync(routePath, "utf8");
  assert.match(route, /import\s*\{\s*validateFilesWithContent\s*\}\s*from\s*["']@\/lib\/upload\/validation["']/);
  const validateIndex = route.indexOf("await validateFilesWithContent(files)");
  const emptyGuardIndex = route.indexOf("if (!valid.length)");
  const createProjectIndex = route.indexOf("const project = await createProjectWithCapacity");
  assert.ok(validateIndex >= 0 && emptyGuardIndex > validateIndex && createProjectIndex > emptyGuardIndex,
    "the API must finish content validation and reject an all-invalid batch before creating a project");

  const sourceFile = readFileSync(sourcePath, "utf8");
  assert.match(sourceFile, /Total batch size exceeds 3 MiB limit/);
  assert.doesNotMatch(sourceFile, /Total batch size exceeds 100 MB limit/);

  console.log("PASS: PDF, PNG, JPEG, WebP, ASCII/binary DXF signatures; extension/MIME mismatch; empty/unsupported files; 3 MiB limit; invalid batches rejected before project creation");
} finally {
  rmSync(scratchDir, { recursive: true, force: true });
}