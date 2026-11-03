/**
 * File upload validation utilities.
 *
 * validateFiles is a lightweight client-side selection check. It is only a UX
 * aid. The server MUST call validateFilesWithContent before storing any file.
 */

export const ALLOWED_MIME_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/jpg",
  "image/webp",
  "application/dxf",
  "application/x-dxf",
  "image/vnd.dxf",
  "text/plain",
] as const;

export const ALLOWED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".dxf"] as const;

// Keep the upload limits below the Vercel Function request-body limit.
export const MAX_FILE_SIZE = 3 * 1024 * 1024; // 3 MiB per file
export const MAX_FILES_PER_UPLOAD = 10;
export const MAX_TOTAL_SIZE = 3 * 1024 * 1024; // 3 MiB per batch

export type UploadFileType = "pdf" | "image" | "dxf";
type ContentFormat = "pdf" | "png" | "jpeg" | "webp" | "dxf";

export interface ValidatedFile {
  file: File;
  type: UploadFileType;
  size: number;
}

export interface ValidationResult {
  valid: ValidatedFile[];
  rejected: { file: File; reason: string }[];
}

const EXTENSION_FORMATS: Record<string, ContentFormat> = {
  ".pdf": "pdf",
  ".png": "png",
  ".jpg": "jpeg",
  ".jpeg": "jpeg",
  ".webp": "webp",
  ".dxf": "dxf",
};

const FORMAT_MIME_TYPES: Record<ContentFormat, readonly string[]> = {
  pdf: ["application/pdf"],
  png: ["image/png"],
  jpeg: ["image/jpeg", "image/jpg"],
  webp: ["image/webp"],
  dxf: ["application/dxf", "application/x-dxf", "image/vnd.dxf", "text/plain"],
};

const GENERIC_MIME_TYPES = new Set(["", "application/octet-stream"]);
const DXF_SECTIONS = new Set([
  "HEADER",
  "CLASSES",
  "TABLES",
  "BLOCKS",
  "ENTITIES",
  "OBJECTS",
  "THUMBNAILIMAGE",
]);

function getExtension(fileName: string): string | null {
  const baseName = fileName.replace(/^.*[\\/]/, "");
  const dot = baseName.lastIndexOf(".");
  if (dot <= 0 || dot === baseName.length - 1) return null;
  return baseName.slice(dot).toLowerCase();
}

function toUploadFileType(format: ContentFormat): UploadFileType {
  if (format === "pdf") return "pdf";
  if (format === "dxf") return "dxf";
  return "image";
}

/**
 * Lightweight metadata-only classification for the browser UI.
 * This result is NOT a security check and must not authorize storage.
 */
export function getFileType(file: File): UploadFileType | null {
  const mime = file.type.toLowerCase();
  const extension = getExtension(file.name);
  const format = extension ? EXTENSION_FORMATS[extension] : undefined;

  if (format) return toUploadFileType(format);
  if (mime === "application/pdf") return "pdf";
  if (mime === "application/dxf" || mime === "application/x-dxf" || mime === "image/vnd.dxf") return "dxf";
  if (["image/png", "image/jpeg", "image/jpg", "image/webp"].includes(mime)) return "image";
  return null;
}

/**
 * Metadata-only validation for immediate browser feedback. Actual content
 * validation is performed asynchronously by validateFilesWithContent on the server.
 */
export function validateFile(file: File): { ok: boolean; reason?: string; type?: UploadFileType } {
  const type = getFileType(file);
  if (file.size === 0) return { ok: false, reason: "File is empty." };
  if (!type) {
    return { ok: false, reason: `Unsupported file type: ${file.type || "unknown"}. Allowed: PDF, PNG, JPG, WEBP, DXF` };
  }
  if (file.size > MAX_FILE_SIZE) {
    return { ok: false, reason: `File exceeds 3 MiB limit: ${(file.size / 1024 / 1024).toFixed(1)} MB` };
  }
  return { ok: true, type };
}

/**
 * Metadata-only batch validation for the browser UI. Never use this function
 * as the server-side authorization to store uploaded content.
 */
export function validateFiles(files: File[]): ValidationResult {
  const valid: ValidatedFile[] = [];
  const rejected: { file: File; reason: string }[] = [];

  if (files.length > MAX_FILES_PER_UPLOAD) {
    files.forEach((file) => rejected.push({ file, reason: `Batch exceeds ${MAX_FILES_PER_UPLOAD} files limit` }));
    return { valid, rejected };
  }

  let totalSize = 0;
  for (const file of files) {
    const validation = validateFile(file);
    if (!validation.ok || !validation.type) {
      rejected.push({ file, reason: validation.reason ?? "Unknown validation error" });
      continue;
    }
    if (totalSize + file.size > MAX_TOTAL_SIZE) {
      rejected.push({ file, reason: "Total batch size exceeds 3 MiB limit." });
      continue;
    }
    totalSize += file.size;
    valid.push({ file, type: validation.type, size: file.size });
  }
  return { valid, rejected };
}

function startsWith(bytes: Uint8Array, signature: readonly number[]): boolean {
  return signature.every((value, index) => bytes[index] === value);
}

function isAsciiDxf(bytes: Uint8Array): boolean {
  // ASCII DXF is a sequence of group-code/value line pairs ending in 0/EOF.
  // Decode Windows-1252 to support common CAD-generated ANSI text files.
  const text = new TextDecoder("windows-1252").decode(bytes).replace(/^\uFEFF/, "");
  const lines = text.split(/\r\n|\n|\r/).map((line) => line.trim());
  while (lines.length > 0 && lines[lines.length - 1] === "") lines.pop();
  if (lines.length < 8 || lines.length % 2 !== 0) return false;
  if (lines[lines.length - 2] !== "0" || lines[lines.length - 1].toUpperCase() !== "EOF") return false;

  let hasKnownSection = false;
  let hasEndSection = false;
  for (let index = 0; index + 1 < lines.length; index += 2) {
    const groupCode = lines[index];
    const value = lines[index + 1].toUpperCase();
    if (groupCode === "0" && value === "ENDSEC") hasEndSection = true;
    if (
      groupCode === "0" && value === "SECTION" &&
      lines[index + 2] === "2" && DXF_SECTIONS.has((lines[index + 3] ?? "").toUpperCase())
    ) {
      hasKnownSection = true;
    }
  }
  return hasKnownSection && hasEndSection;
}

function detectContentFormat(bytes: Uint8Array): ContentFormat | null {
  // PDF header.
  if (bytes.length >= 8 && startsWith(bytes, [0x25, 0x50, 0x44, 0x46, 0x2D])) return "pdf";

  // PNG signature plus the mandatory first 13-byte IHDR chunk header.
  if (
    bytes.length >= 33 &&
    startsWith(bytes, [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) &&
    bytes[8] === 0 && bytes[9] === 0 && bytes[10] === 0 && bytes[11] === 13 &&
    bytes[12] === 0x49 && bytes[13] === 0x48 && bytes[14] === 0x44 && bytes[15] === 0x52
  ) return "png";

  // JPEG start-of-image and end-of-image markers.
  if (
    bytes.length >= 4 && startsWith(bytes, [0xFF, 0xD8, 0xFF]) &&
    bytes[bytes.length - 2] === 0xFF && bytes[bytes.length - 1] === 0xD9
  ) return "jpeg";

  // WebP is a RIFF container with a WEBP form type and a recognized first chunk.
  if (
    bytes.length >= 20 &&
    bytes[0] === 0x52 && bytes[1] === 0x49 && bytes[2] === 0x46 && bytes[3] === 0x46 &&
    bytes[8] === 0x57 && bytes[9] === 0x45 && bytes[10] === 0x42 && bytes[11] === 0x50
  ) {
    const riffSize = bytes[4] + (bytes[5] << 8) + (bytes[6] << 16) + (bytes[7] << 24);
    const firstChunk = String.fromCharCode(...bytes.subarray(12, 16));
    if (
      riffSize >= 12 && riffSize + 8 <= bytes.length &&
      ["VP8 ", "VP8L", "VP8X"].includes(firstChunk)
    ) return "webp";
  }

  // Binary DXF has a fixed AutoCAD header. ASCII DXF needs structural markers.
  const binaryDxfHeader = [
    0x41, 0x75, 0x74, 0x6F, 0x43, 0x41, 0x44, 0x20, 0x42, 0x69, 0x6E,
    0x61, 0x72, 0x79, 0x20, 0x44, 0x58, 0x46, 0x0D, 0x0A, 0x1A, 0x00,
  ];
  if (bytes.length > binaryDxfHeader.length && startsWith(bytes, binaryDxfHeader)) return "dxf";
  if (bytes.length > 0 && !bytes.includes(0) && isAsciiDxf(bytes)) return "dxf";

  return null;
}

/**
 * Server-side content validation. Requires an allowed extension, matching file
 * signature/structure, and a non-conflicting MIME type before a file is stored.
 */
export async function validateFileWithContent(
  file: File,
): Promise<{ ok: boolean; reason?: string; type?: UploadFileType }> {
  const extension = getExtension(file.name);
  const extensionFormat = extension ? EXTENSION_FORMATS[extension] : undefined;
  if (!extensionFormat) {
    return { ok: false, reason: "Unsupported file extension. Allowed: PDF, PNG, JPG, WEBP, DXF." };
  }
  if (file.size === 0) return { ok: false, reason: "File is empty." };
  if (file.size > MAX_FILE_SIZE) {
    return { ok: false, reason: `File exceeds 3 MiB limit: ${(file.size / 1024 / 1024).toFixed(1)} MB` };
  }

  let bytes: Uint8Array;
  try {
    bytes = new Uint8Array(await file.arrayBuffer());
  } catch {
    return { ok: false, reason: "Could not read file contents." };
  }
  if (bytes.length !== file.size || bytes.length === 0) {
    return { ok: false, reason: "File contents are empty or could not be read completely." };
  }

  const detectedFormat = detectContentFormat(bytes);
  if (!detectedFormat) {
    return { ok: false, reason: "File contents do not match a supported PDF, PNG, JPEG, WebP, or DXF structure." };
  }
  if (detectedFormat !== extensionFormat) {
    return { ok: false, reason: `File extension ${extension} does not match its detected ${detectedFormat.toUpperCase()} content.` };
  }

  const mime = file.type.trim().toLowerCase();
  if (!GENERIC_MIME_TYPES.has(mime) && !FORMAT_MIME_TYPES[detectedFormat].includes(mime)) {
    return { ok: false, reason: `MIME type ${mime} conflicts with the detected ${detectedFormat.toUpperCase()} content.` };
  }

  return { ok: true, type: toUploadFileType(detectedFormat) };
}

/**
 * Authoritative server-side batch validation. Invalid files are returned in
 * rejected and are never included in valid for private Blob storage.
 */
export async function validateFilesWithContent(files: File[]): Promise<ValidationResult> {
  const valid: ValidatedFile[] = [];
  const rejected: { file: File; reason: string }[] = [];

  if (files.length > MAX_FILES_PER_UPLOAD) {
    files.forEach((file) => rejected.push({ file, reason: `Batch exceeds ${MAX_FILES_PER_UPLOAD} files limit` }));
    return { valid, rejected };
  }

  let totalSize = 0;
  for (const file of files) {
    const validation = await validateFileWithContent(file);
    if (!validation.ok || !validation.type) {
      rejected.push({ file, reason: validation.reason ?? "Unknown content validation error" });
      continue;
    }
    if (totalSize + file.size > MAX_TOTAL_SIZE) {
      rejected.push({ file, reason: "Total batch size exceeds 3 MiB limit." });
      continue;
    }
    totalSize += file.size;
    valid.push({ file, type: validation.type, size: file.size });
  }

  return { valid, rejected };
}

/** Format file size for display. */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}