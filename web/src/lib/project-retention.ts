import { del } from "@vercel/blob";
import { prisma } from "@/lib/prisma";
import {
  canCreateProject,
  selectUnprotectedVersionIdsToPrune,
} from "@/lib/project-retention-core";
import { hasPaidFeatureAccess } from "@/lib/billing/subscription-policy";

export { compactStoredJson, FREE_PROJECT_LIMIT, MAX_UNPROTECTED_OUTPUT_VERSIONS } from "@/lib/project-retention-core";

export class ProjectCapacityError extends Error {
  constructor() {
    super("The free plan includes one saved project. Delete it to create another, or upgrade to Pro for unlimited projects.");
    this.name = "ProjectCapacityError";
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function projectPathPrefix(userId: string, projectId: string): string {
  return `projects/${userId}/${projectId}/`;
}

function safeProjectPath(pathname: unknown, prefix: string): string | null {
  if (typeof pathname !== "string" || !pathname.startsWith(prefix) || pathname.includes("..")) return null;
  return pathname;
}

function outputPathnames(version: {
  stepFilePath: string | null;
  stlFilePath: string | null;
  glbFilePath: string | null;
}, prefix: string): string[] {
  return [version.stepFilePath, version.stlFilePath, version.glbFilePath]
    .map((path) => safeProjectPath(path, prefix))
    .filter((path): path is string => path !== null);
}

async function deleteBlobs(pathnames: string[], token: string): Promise<void> {
  const unique = [...new Set(pathnames)];
  if (!unique.length) return;
  await del(unique, { token });
}

/** Pro (active subscription) and admin accounts have no project cap. */
async function hasUnlimitedProjects(userId: string, db: Pick<typeof prisma, "user" | "subscription">): Promise<boolean> {
  const [user, subscription] = await Promise.all([
    db.user.findUnique({ where: { id: userId }, select: { role: true } }),
    db.subscription.findUnique({ where: { userId } }),
  ]);
  return hasPaidFeatureAccess(user?.role ?? "USER", subscription);
}

export async function assertProjectCapacity(
  userId: string,
  db: Pick<typeof prisma, "project" | "user" | "subscription"> = prisma,
): Promise<void> {
  const count = await db.project.count({ where: { userId } });
  if (!canCreateProject(count, await hasUnlimitedProjects(userId, db))) throw new ProjectCapacityError();
}

/**
 * Creates a project only when the plan allows it. The capacity check and the insert run in one
 * database transaction under a per-user lock, so two simultaneous requests cannot both pass.
 */
export async function createProjectWithCapacity(
  userId: string,
  data: { name: string; description: string; status: "DRAFT" | "PROCESSING" },
): Promise<{ id: string }> {
  return prisma.$transaction(async (tx) => {
    await tx.$executeRaw`SELECT pg_advisory_xact_lock(hashtext(${userId}))`;
    await assertProjectCapacity(userId, tx);
    return tx.project.create({ data: { userId, ...data }, select: { id: true } });
  });
}

export async function deleteProjectAndBlobs(projectId: string, userId: string, token: string): Promise<boolean> {
  const project = await prisma.project.findFirst({
    where: { id: projectId, userId },
    select: {
      id: true,
      versions: {
        select: {
          stepFilePath: true,
          stlFilePath: true,
          glbFilePath: true,
          spec: true,
        },
      },
    },
  });
  if (!project) return false;
  const prefix = projectPathPrefix(userId, project.id);
  const pathnames: string[] = [];
  for (const version of project.versions) {
    pathnames.push(...outputPathnames(version, prefix));
    const spec = asRecord(version.spec);
    const uploadedFiles = spec?.uploadedFiles;
    if (Array.isArray(uploadedFiles)) {
      for (const file of uploadedFiles) {
        const record = asRecord(file);
        const pathname = safeProjectPath(record?.pathname, prefix);
        if (pathname) pathnames.push(pathname);
      }
    }
  }

  await deleteBlobs(pathnames, token);
  await prisma.project.delete({ where: { id: project.id } });
  return true;
}

// Projects are never deleted automatically. Deleting is always an explicit user action.

export async function pruneProjectVersions(projectId: string, userId: string, token: string): Promise<number[]> {
  const project = await prisma.project.findFirst({
    where: { id: projectId, userId },
    select: { id: true },
  });
  if (!project) return [];

  const versions = await prisma.projectVersion.findMany({
    where: {
      projectId,
      OR: [
        { stepFilePath: { not: null } },
        { stlFilePath: { not: null } },
        { glbFilePath: { not: null } },
      ],
    },
    orderBy: [{ version: "desc" }, { createdAt: "desc" }],
    select: {
      id: true,
      version: true,
      isProtected: true,
      stepFilePath: true,
      stlFilePath: true,
      glbFilePath: true,
    },
  });
  const pruneIds = new Set(selectUnprotectedVersionIdsToPrune(versions));
  const excess = versions.filter((version) => pruneIds.has(version.id));
  const prefix = projectPathPrefix(userId, projectId);
  const deleted: number[] = [];
  for (const version of excess) {
    await deleteBlobs(outputPathnames(version, prefix), token);
    await prisma.projectVersion.delete({ where: { id: version.id } });
    deleted.push(version.version);
  }
  return deleted;
}
