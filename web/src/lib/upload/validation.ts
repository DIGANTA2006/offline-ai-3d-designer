/**
 * File upload validation utilities.
 * Centralized validation logic for accepted file types, sizes, and counts.
 */

export const ALLOWED_MIME_TYPES = [
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/jpg",
  "image/webp",
  "application/dxf",
] as const;

export const ALLOWED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".webp", ".dxf"] as const;

export const MAX_FILE_SIZE = 25 * 1024 * 1024; // 25 MB per file
export const MAX_FILES_PER_UPLOAD = 10;
export const MAX_TOTAL_SIZE = 100 * 1024 * 1024; // 100 MB total per batch

export type UploadFileType = "pdf" | "image" | "dxf";

export interface ValidatedFile {
  file: File;
  type: UploadFileType;
  size: number;
}

export interface ValidationResult {
  valid: ValidatedFile[];
  rejected: { file: File; reason: string }[];
}

/**
 * Determine the file type category from MIME type or extension.
 */
export function getFileType(file: File): UploadFileType | null {
  const mime = file.type.toLowerCase();
  const ext = file.name.toLowerCase().split(".").pop();

  if (mime === "application/pdf" || ext === "pdf") return "pdf";
  if (mime.startsWith("image/") || ["png", "jpg", "jpeg", "webp"].includes(ext ?? "")) return "image";
  if (mime === "application/dxf" || ext === "dxf") return "dxf";
  return null;
}

/**
 * Validate a single file.
 */
export function validateFile(file: File): { ok: boolean; reason?: string; type?: UploadFileType } {
  const type = getFileType(file);
  if (!type) {
    return { ok: false, reason: `Unsupported file type: ${file.type || "unknown"}. Allowed: PDF, PNG, JPG, WEBP, DXF` };
  }
  if (file.size > MAX_FILE_SIZE) {
    return { ok: false, reason: `File exceeds 25 MB limit: ${(file.size / 1024 / 1024).toFixed(1)} MB` };
  }
  return { ok: true, type };
}

/**
 * Validate an array of files for batch upload.
 */
export function validateFiles(files: File[]): ValidationResult {
  const valid: ValidatedFile[] = [];
  const rejected: { file: File; reason: string }[] = [];

  if (files.length > MAX_FILES_PER_UPLOAD) {
    // Reject all if too many files
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
    totalSize += file.size;
    if (totalSize > MAX_TOTAL_SIZE) {
      rejected.push({ file, reason: `Total batch size exceeds 100 MB limit` });
      continue;
    }
    valid.push({ file, type: validation.type, size: file.size });
  }

  return { valid, rejected };
}

/**
 * Format file size for display.
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
