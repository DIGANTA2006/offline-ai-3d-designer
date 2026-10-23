import { put } from "@vercel/blob";
import { NextResponse } from "next/server";
import type { Prisma } from "@prisma/client";
import { getCurrentUser } from "@/lib/auth/server";
import { isSameOriginRequest } from "@/lib/security/same-origin";
import { prisma } from "@/lib/prisma";
import { getCadServiceConfig } from "@/lib/cad-service-config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_BODY_BYTES = 16 * 1024;
const MAX_CAD_RESPONSE_BYTES = 15 * 1024 * 1024;
const MAX_BASE64_BYTES = 10 * 1024 * 1024;
// CAD generation requires an active PRO subscription; ADMIN accounts bypass billing.
const CAD_TIMEOUT_MS = 30_000;

type UnitSystem = "mm" | "cm" | "in" | "m";
type CadResponse = {
  success: boolean;
  partSpec?: Record<string, unknown>;
  stepBase64?: string;
  stlBase64?: string;
  validationErrors?: string[];
  error?: string;
};

class RouteError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function readLimitedText(response: Response, limit: number): Promise<string> {
  const statedLength = Number(response.headers.get("content-length") ?? 0);
  if (statedLength > limit) throw new RouteError("CAD service response exceeded the configured size limit.", 502);
  if (!response.body) return "";

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let size = 0;
  let text = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > limit) {
        await reader.cancel();
        throw new RouteError("CAD service response exceeded the configured size limit.", 502);
      }
      text += decoder.decode(value, { stream: true });
    }
    text += decoder.decode();
    return text;
  } finally {
    reader.releaseLock();
  }
}

function decodeBase64(value: unknown, label: string): Buffer {
  if (typeof value !== "string" || value.length === 0 || value.length > MAX_BASE64_BYTES) {
    throw new RouteError(`The CAD service did not return a valid ${label} export.`, 502);
  }
  if (!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) {
    throw new RouteError(`The CAD service returned an invalid ${label} export.`, 502);
  }
  const buffer = Buffer.from(value, "base64");
  if (buffer.length === 0) throw new RouteError(`The CAD service returned an empty ${label} export.`, 502);
  return buffer;
}

function cadServiceUrl(): URL {
  try {
    return new URL("/api/v1/text-to-cad", getCadServiceConfig().baseUrl);
  } catch (error) {
    throw new RouteError(error instanceof Error ? error.message : "CAD service configuration is invalid.", 503);
  }
}

function safeErrorMessage(error: unknown): string {
  if (error instanceof RouteError) return error.message;
  return "CAD generation failed. Check that the CAD service is online and review its runtime logs.";
}

export async function POST(request: Request) {
  if (!isSameOriginRequest(request)) {
    return NextResponse.json({ error: "Request origin could not be verified." }, { status: 403 });
  }

  let user;
  try {
    user = await getCurrentUser();
  } catch (error) {
    console.error("Project API could not resolve the current user.", error);
    return NextResponse.json({ error: "Authentication or database service is unavailable." }, { status: 503 });
  }
  if (!user) return NextResponse.json({ error: "Sign in before creating a CAD project." }, { status: 401 });

  const privateBlobToken = process.env.PRIVATE_BLOB_READ_WRITE_TOKEN?.trim();
  if (!privateBlobToken) {
    return NextResponse.json({ error: "Private project storage is not configured. Connect a private Vercel Blob store before generating files." }, { status: 503 });
  }
  let serviceToken: string | undefined;
  try {
    serviceToken = getCadServiceConfig().token;
  } catch (error) {
    const message = error instanceof Error ? error.message : "CAD service configuration is invalid.";
    return NextResponse.json({ error: message }, { status: 503 });
  }
  if (process.env.NODE_ENV === "production" && !serviceToken) {
    return NextResponse.json({ error: "CAD service token is not configured on the web service." }, { status: 503 });
  }

  const statedLength = Number(request.headers.get("content-length") ?? 0);
  if (statedLength > MAX_BODY_BYTES) return NextResponse.json({ error: "Project request is too large." }, { status: 413 });

  let body: unknown;
  try {
    const raw = await request.text();
    if (Buffer.byteLength(raw, "utf8") > MAX_BODY_BYTES) return NextResponse.json({ error: "Project request is too large." }, { status: 413 });
    body = JSON.parse(raw);
  } catch {
    return NextResponse.json({ error: "A valid JSON request body is required." }, { status: 400 });
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return NextResponse.json({ error: "A JSON object request body is required." }, { status: 400 });
  }

  const input = body as Record<string, unknown>;
  const text = typeof input.text === "string" ? input.text.trim() : "";
  const requestedName = typeof input.name === "string" ? input.name.trim() : "";
  const allowedUnits: UnitSystem[] = ["mm", "cm", "in", "m"];
  const unitSystem = input.unitSystem === undefined ? "mm" : input.unitSystem;
  if (text.length < 5 || text.length > 4000) {
    return NextResponse.json({ error: "Describe the part in 5–4000 characters." }, { status: 400 });
  }
  if (requestedName.length > 80) return NextResponse.json({ error: "Project names must be 80 characters or fewer." }, { status: 400 });
  if (typeof unitSystem !== "string" || !allowedUnits.includes(unitSystem as UnitSystem)) {
    return NextResponse.json({ error: "Choose a supported unit system: mm, cm, in, or m." }, { status: 400 });
  }

  let serviceUrl: URL;
  try {
    serviceUrl = cadServiceUrl();
  } catch (error) {
    return NextResponse.json({ error: safeErrorMessage(error) }, { status: error instanceof RouteError ? error.status : 503 });
  }

  let usageReserved = false;
  let projectId: string | null = null;
  let hasCadAccess = user.role === "ADMIN";
  try {
    const subscription = await prisma.subscription.findUnique({ where: { userId: user.id } });
    hasCadAccess = hasCadAccess || (subscription?.tier === "PRO" && subscription.status === "ACTIVE");
  } catch (error) {
    console.error("Project API could not load subscription status.", error);
    return NextResponse.json({ error: "Subscription service is unavailable. Please retry shortly." }, { status: 503 });
  }
  if (!hasCadAccess) {
    return NextResponse.json({
      error: "An active Pro subscription is required to generate CAD files. Pro costs ₹500 per month.",
      code: "SUBSCRIPTION_REQUIRED",
      upgradeUrl: "/dashboard/billing",
    }, { status: 402 });
  }
  const now = new Date();
  const periodStart = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
  const usageWhere: { userId_action_periodStart: { userId: string; action: string; periodStart: Date } } = {
    userId_action_periodStart: { userId: user.id, action: "generation", periodStart },
  };

  try {
    await prisma.usageRecord.upsert({
      where: usageWhere,
      update: {},
      create: { userId: user.id, action: "generation", periodStart, count: 0 },
    });
    const reservation = await prisma.usageRecord.updateMany({
      where: { userId: user.id, action: "generation", periodStart },
      data: { count: { increment: 1 } },
    });
    if (reservation.count !== 1) {
      return NextResponse.json({ error: "Your free-tier generation limit has been reached for this month." }, { status: 403 });
    }
    usageReserved = true;

    const name = requestedName || text.replace(/\s+/g, " ").slice(0, 72);
    const project = await prisma.project.create({
      data: { userId: user.id, name, description: text, status: "PROCESSING" },
      select: { id: true },
    });
    projectId = project.id;

    const abortController = new AbortController();
    const timeout = setTimeout(() => abortController.abort(), CAD_TIMEOUT_MS);
    let upstream: Response;
    try {
      upstream = await fetch(serviceUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(serviceToken ? { Authorization: `Bearer ${serviceToken}` } : {}),
        },
        body: JSON.stringify({ text, userId: user.id, unitSystem, exportFormats: ["step", "stl"] }),
        cache: "no-store",
        signal: abortController.signal,
      });
    } finally {
      clearTimeout(timeout);
    }

    const upstreamText = await readLimitedText(upstream, MAX_CAD_RESPONSE_BYTES);
    let cad: CadResponse;
    try {
      cad = JSON.parse(upstreamText) as CadResponse;
    } catch {
      throw new RouteError("The CAD service returned an invalid response. Check the CAD service deployment and logs.", 502);
    }
    if (!upstream.ok) {
      // Never forward an upstream 401 as an application 401: the browser would
      // mistake a CAD service-token mismatch for a missing user session.
      const safeDetail = typeof cad.error === "string" ? cad.error.slice(0, 240) : "CAD service request failed.";
      throw new RouteError(safeDetail, upstream.status === 503 ? 503 : 502);
    }
    if (!cad.success) {
      const safeDetail = typeof cad.error === "string" ? cad.error.slice(0, 240) : "The CAD parser could not create a valid part from this description.";
      throw new RouteError(safeDetail, 422);
    }

    const stepBytes = decodeBase64(cad.stepBase64, "STEP");
    const stlBytes = decodeBase64(cad.stlBase64, "STL");
    const blobBase = `projects/${user.id}/${project.id}/v1`;
    const [stepBlob, stlBlob] = await Promise.all([
      put(`${blobBase}/part.step`, stepBytes, { access: "private", token: privateBlobToken, contentType: "model/step", addRandomSuffix: true }),
      put(`${blobBase}/part.stl`, stlBytes, { access: "private", token: privateBlobToken, contentType: "model/stl", addRandomSuffix: true }),
    ]);

    const version = await prisma.projectVersion.create({
      data: {
        projectId: project.id,
        version: 1,
        inputText: text,
        spec: (cad.partSpec ?? {}) as Prisma.InputJsonValue,
        stepFilePath: stepBlob.pathname,
        stlFilePath: stlBlob.pathname,
      },
      select: { id: true, version: true },
    });
    await prisma.project.update({ where: { id: project.id }, data: { status: "SUCCEEDED" } });

    try {
      await prisma.auditLog.create({
        data: {
          userId: user.id,
          agent: "text-to-cad",
          provider: "python-backend",
          action: "project_generated",
          status: "success",
          details: { projectId: project.id, versionId: version.id, exportFormats: ["step", "stl"] },
        },
      });
    } catch (auditError) {
      console.error("CAD project succeeded but its audit log could not be saved.", auditError);
    }

    return NextResponse.json({ ok: true, projectId: project.id, versionId: version.id, version: version.version, status: "SUCCEEDED" }, { status: 201 });
  } catch (error) {
    console.error("Text-to-CAD project creation failed.", error);
    if (projectId) {
      try { await prisma.project.update({ where: { id: projectId }, data: { status: "FAILED" } }); }
      catch (updateError) { console.error("Could not mark failed CAD project.", updateError); }
    }
    if (usageReserved) {
      try {
        await prisma.usageRecord.updateMany({ where: { userId: user.id, action: "generation", periodStart, count: { gt: 0 } }, data: { count: { decrement: 1 } } });
      } catch (usageError) { console.error("Could not release failed-generation reservation.", usageError); }
    }
    const status = error instanceof RouteError ? error.status : error instanceof Error && error.name === "AbortError" ? 504 : 500;
    const message = error instanceof Error && error.name === "AbortError" ? "CAD service request timed out. Check the backend's health and logs." : safeErrorMessage(error);
    return NextResponse.json({ error: message }, { status });
  }
}
