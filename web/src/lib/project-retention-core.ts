/**
 * Pure retention policy helpers. Kept separate from Prisma/Blob so the policies
 * can be tested without a live database or storage credentials.
 */
/** Free plan: one saved project. Pro plan: unlimited. Nothing is ever deleted automatically. */
export const FREE_PROJECT_LIMIT = 1;

/** Pure rule: may this account save another project? */
export function canCreateProject(savedProjectCount: number, hasUnlimitedProjects: boolean): boolean {
  return hasUnlimitedProjects || savedProjectCount < FREE_PROJECT_LIMIT;
}
export const MAX_UNPROTECTED_OUTPUT_VERSIONS = 2;

const HEAVY_JSON_KEY =
  /base64|data[_-]?(?:url|uri)|(?:raw[_-]?)?mesh(?:data|bytes|payload|base64)?$|(?:image|file|binary)[_-]?(?:bytes|buffer|payload)|^(?:vertices|faces|triangles)$/i;

function isInlineBinaryString(value: string): boolean {
  if (value.startsWith("data:image/") || value.startsWith("data:application/") || value.startsWith("data:model/")) return true;
  if (value.length < 256_000) return false;
  const compact = value.replace(/\s/g, "");
  if (compact.length < 256_000 || compact.length % 4 !== 0) return false;
  return /^[A-Za-z0-9+/]+={0,2}$/.test(compact);
}

/**
 * Strip transient data URLs, Base64 exports, and raw vertex/face arrays before a
 * value reaches a JSON database column. Null placeholders preserve array positions.
 */
export function compactStoredJson<T>(value: T): T {
  const visit = (node: unknown, key = ""): unknown => {
    if (HEAVY_JSON_KEY.test(key)) return undefined;
    if (typeof node === "string") return isInlineBinaryString(node) ? undefined : node;
    if (Array.isArray(node)) {
      return node.map((item) => {
        const compacted = visit(item);
        // JSON.stringify turns undefined array values into null; explicitly preserve
        // slots so source/OCR indices cannot silently shift after compaction.
        return compacted === undefined ? null : compacted;
      });
    }
    if (node && typeof node === "object") {
      const result: Record<string, unknown> = {};
      for (const [childKey, childValue] of Object.entries(node)) {
        const compacted = visit(childValue, childKey);
        if (compacted !== undefined) result[childKey] = compacted;
      }
      return result;
    }
    return node;
  };
  return visit(value) as T;
}

// Projects are never pruned automatically. Deleting a project is always an explicit user action.

type OutputRetentionRecord = { id: string; isProtected: boolean };

/** Versions must be supplied newest-first; protected versions do not count toward the default two. */
export function selectUnprotectedVersionIdsToPrune(
  versionsNewestFirst: OutputRetentionRecord[],
  keepUnprotected = MAX_UNPROTECTED_OUTPUT_VERSIONS,
): string[] {
  return versionsNewestFirst
    .filter((version) => !version.isProtected)
    .slice(Math.max(0, keepUnprotected))
    .map((version) => version.id);
}
