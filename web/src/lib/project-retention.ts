import { del } from "@vercel/blob";
import { prisma } from "@/lib/prisma";
import {
  compactStoredJson,
  MAX_ACTIVE_PROJECTS,
  selectProjectIdsToPrune,
  selectUnprotectedVersionIdsToPrune,
} from "@/lib/project-retention-core";

export { compactStoredJson, MAX_ACTIVE_PROJECTS, MAX_UNPROTECTED_OUTPUT_VERSIONS } from "@/lib/project-retention-core";

export class ProjectCapacityError extends Error {
  constructor() {
    super("You have reached the 10-project storage limit. Mark an older project unimportant or delete it before creating another project.");
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

export async function assertProjectCapacity(userId: string): Promise<void> {
  const count = await prisma.project.count({ where: { userId } });
  if (count < MAX_ACTIVE_PROJECTS) return;
  // Make sure enough old projects can be removed to get back under the cap after
  // the new project is created, including when a legacy account is already over limit.
  const requiredDeletable = count - MAX_ACTIVE_PROJECTS + 1;
  const deletableCount = await prisma.project.count({
    where: {
      userId,
      isImportant: false,
      status: { notIn: ["PROCESSING", "QUEUED"] },
    },
  });
  if (deletableCount < requiredDeletable) throw new ProjectCapacityError();
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

export async function pruneUserProjects(
  userId: string,
  token: string,
  options: { excludeProjectId?: string } = {},
): Promise<string[]> {
  const projects = await prisma.project.findMany({
    where: { userId },
    orderBy: [{ createdAt: "asc" }, { updatedAt: "asc" }],
    select: { id: true, isImportant: true, status: true },
  });
  let excess = projects.length - MAX_ACTIVE_PROJECTS;
  if (excess <= 0) return [];
  const pruneIds = new Set(selectProjectIdsToPrune(projects, options));
  const deleted: string[] = [];
  for (const project of projects) {
    if (excess <= 0) break;
    if (!pruneIds.has(project.id)) continue;
    if (await deleteProjectAndBlobs(project.id, userId, token)) {
      deleted.push(project.id);
      excess -= 1;
    }
  }
  if (excess > 0) throw new ProjectCapacityError();
  return deleted;
}

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
