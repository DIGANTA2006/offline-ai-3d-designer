/**
 * Decide whether an uploaded source file is supported by the drawing OCR endpoint.
 *
 * Server-validated MIME metadata is authoritative for new uploads. Filename
 * extensions are only a compatibility fallback for older project versions.
 * DXF is accepted for storage but is not a PDF/raster OCR input in this flow.
 */
export type OcrSourceMetadata = {
  name: string;
  contentType?: string | null;
  type?: "pdf" | "image" | "dxf" | string | null;
};

const OCR_MIME_TYPES = new Set([
  "application/pdf",
  "image/png",
  "image/jpeg",
  "image/jpg",
  "image/webp",
]);

const OCR_EXTENSIONS = /\.(pdf|png|jpe?g|webp)$/i;

export function isOcrSourceFile(file: OcrSourceMetadata): boolean {
  const mime = (file.contentType ?? "").split(";", 1)[0].trim().toLowerCase();

  // A specific, validated MIME mismatch must not be overridden by a filename.
  if (mime && mime !== "application/octet-stream") {
    return OCR_MIME_TYPES.has(mime);
  }

  // New uploads retain the server-validated format even when the filename is random.
  if (file.type === "dxf") return false;
  if (file.type === "pdf" || file.type === "image") return true;

  // Compatibility fallback for old versions without MIME/type metadata.
  return OCR_EXTENSIONS.test(file.name);
}
