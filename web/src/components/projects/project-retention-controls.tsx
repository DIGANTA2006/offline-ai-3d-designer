"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Bookmark, LoaderCircle, ShieldCheck, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

type ApiPayload = { ok?: boolean; error?: string; warning?: string };

export function ProjectImportanceToggle({ projectId, initialImportant }: { projectId: string; initialImportant: boolean }) {
  const router = useRouter();
  const [important, setImportant] = useState(initialImportant);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => setImportant(initialImportant), [initialImportant]);

  async function toggle() {
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/retention`, {
        method: "PATCH", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ isImportant: !important }),
      });
      const payload = await response.json().catch(() => ({})) as ApiPayload;
      if (!response.ok) throw new Error(payload.error ?? "Could not update project retention.");
      setImportant(!important); router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update project retention.");
    } finally { setBusy(false); }
  }

  return <div className="flex flex-col items-end gap-1">
    <Button type="button" size="sm" variant={important ? "default" : "outline"} onClick={toggle} disabled={busy}>
      {busy ? <LoaderCircle className="size-4 animate-spin" /> : <Bookmark className="size-4" />}
      {important ? "Important project" : "Mark important"}
    </Button>
    {error && <p role="alert" className="max-w-64 text-right text-xs text-destructive">{error}</p>}
    <p className="max-w-64 text-right text-xs text-muted-foreground">{important ? "Preserved by automatic project cleanup." : "Eligible for cleanup when the project limit is reached."}</p>
  </div>;
}

export function ProjectVersionActions({ projectId, versionId, versionNumber, initialProtected }: { projectId: string; versionId: string; versionNumber: number; initialProtected: boolean }) {
  const router = useRouter();
  const [protectedVersion, setProtectedVersion] = useState(initialProtected);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => setProtectedVersion(initialProtected), [initialProtected]);

  async function toggleProtection() {
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}`, {
        method: "PATCH", credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ isProtected: !protectedVersion }),
      });
      const payload = await response.json().catch(() => ({})) as ApiPayload;
      if (!response.ok) throw new Error(payload.error ?? "Could not update export protection.");
      setProtectedVersion(!protectedVersion);
      if (payload.warning) setError(payload.warning);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not update export protection.");
    } finally { setBusy(false); }
  }

  async function deleteVersion() {
    if (!window.confirm(`Delete CAD version ${versionNumber} and its stored STEP/STL exports? This cannot be undone.`)) return;
    setBusy(true); setError("");
    try {
      const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}`, { method: "DELETE", credentials: "same-origin" });
      const payload = await response.json().catch(() => ({})) as ApiPayload;
      if (!response.ok) throw new Error(payload.error ?? "Could not delete this export.");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not delete this export.");
    } finally { setBusy(false); }
  }

  return <div className="flex flex-wrap items-center gap-2">
    <Button type="button" size="sm" variant={protectedVersion ? "default" : "outline"} onClick={toggleProtection} disabled={busy}>
      {busy ? <LoaderCircle className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
      {protectedVersion ? "Protected" : "Protect"}
    </Button>
    <Button type="button" size="sm" variant="destructive" onClick={deleteVersion} disabled={busy}><Trash2 className="size-4" /> Delete</Button>
    {error && <p role="alert" className="basis-full text-xs text-destructive">{error}</p>}
  </div>;
}
