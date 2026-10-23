"use client";

import { useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Loader2, CheckCircle2, AlertCircle, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { FileDropZone } from "./file-drop-zone";
import { validateFiles, type ValidatedFile } from "@/lib/upload/validation";

export function UploadPanel() {
  const router = useRouter();
  const [selectedFiles, setSelectedFiles] = useState<ValidatedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [progress, setProgress] = useState(0);

  const handleFilesSelected = useCallback((files: ValidatedFile[]) => {
    setSelectedFiles(files);
    setError("");
    setSuccess("");
  }, []);

  const handleUpload = async () => {
    if (!selectedFiles.length) return;
    setUploading(true);
    setProgress(0);
    setError("");
    setSuccess("");
    try {
      const formData = new FormData();
      selectedFiles.forEach((item) => formData.append("files", item.file));
      const response = await fetch("/api/upload", {
        method: "POST",
        body: formData,
        credentials: "same-origin",
      });
      setProgress(50);
      const data = await response.json().catch(() => ({})) as {
        error?: string; projectId?: string; versionId?: string; uploadedFiles?: Array<{ name: string }>;
      };
      if (response.status === 401) {
        router.replace("/login");
        return;
      }
      if (!response.ok || !data.projectId || !data.versionId) {
        throw new Error(data.error ?? `Upload failed (HTTP ${response.status}).`);
      }
      setProgress(100);
      setSuccess(`Stored ${data.uploadedFiles?.length ?? 0} file(s) privately. Open this project to analyze supported drawings with OCR and review the extracted text before CAD generation.`);
      router.push(`/dashboard/projects/${data.projectId}`);
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const { valid, rejected } = validateFiles(selectedFiles.map((item) => item.file));
  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><FileText className="size-5" />Upload Engineering Drawings</CardTitle>
        <CardDescription>Files are stored privately for your account. This flow does not run OCR or generate CAD from drawings yet; use New Project for text-to-CAD.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <FileDropZone onFilesSelected={handleFilesSelected} disabled={uploading} />
        {error && <div role="alert" className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"><AlertCircle className="mt-0.5 size-4 shrink-0" />{error}</div>}
        {success && <div role="status" className="flex items-start gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-700 dark:text-emerald-300"><CheckCircle2 className="mt-0.5 size-4 shrink-0" />{success}</div>}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
          <div className="text-sm text-muted-foreground">{selectedFiles.length} file(s) selected · {valid.length} valid · {rejected.length} rejected · 3 MiB batch limit</div>
          <Button onClick={handleUpload} disabled={uploading || !valid.length} className="gap-2">
            {uploading ? <><Loader2 className="size-4 animate-spin" /> Uploading… {progress}%</> : <><ArrowRight className="size-4" /> Store privately</>}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
