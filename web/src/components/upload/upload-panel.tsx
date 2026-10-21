"use client";

import { useState, useCallback } from "react";
import { ArrowRight, Loader2, CheckCircle2, AlertCircle, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { FileDropZone } from "./file-drop-zone";
import { validateFiles, type ValidatedFile } from "@/lib/upload/validation";

interface UploadPanelProps {
  onUploadComplete: (projectId: string, versionId: string) => void;
}

export function UploadPanel({ onUploadComplete }: UploadPanelProps) {
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

    try {
      const formData = new FormData();
      selectedFiles.forEach((f) => formData.append("files", f.file));

      const response = await fetch("/api/upload", {
        method: "POST",
        body: formData,
        credentials: "same-origin",
      });

      setProgress(50);

      const data = await response.json();
      if (!response.ok) throw new Error(data.error ?? "Upload failed");

      setProgress(100);
      setSuccess(`Uploaded ${data.uploadedFiles.length} file(s). Starting processing...`);
      onUploadComplete(data.projectId, data.versionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed. Please try again.");
    } finally {
      setUploading(false);
    }
  };

  const { valid, rejected } = validateFiles(selectedFiles.map((f) => f.file));

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><FileText className="size-5" />Upload Engineering Drawings</CardTitle>
        <CardDescription>
          Drop PDF drawings, component photos, or DXF files. The AI will extract dimensions, tolerances, and generate a 3D model.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <FileDropZone onFilesSelected={handleFilesSelected} disabled={uploading} />

        {error && (
          <div className="flex items-start gap-2 rounded-xl border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />{error}
          </div>
        )}

        {success && (
          <div className="flex items-start gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3 text-sm text-emerald-700 dark:text-emerald-300">
            <CheckCircle2 className="mt-0.5 size-4 shrink-0" />{success}
          </div>
        )}

        <div className="flex items-center justify-between pt-2 border-t">
          <div className="text-sm text-muted-foreground">
            {selectedFiles.length} file(s) ready • {valid.length} valid • {rejected.length} rejected
          </div>
          <Button
            onClick={handleUpload}
            disabled={uploading || !valid.length}
            className="gap-2"
          >
            {uploading ? (
              <>
                <Loader2 className="size-4 animate-spin" />
                Uploading... {progress}%
              </>
            ) : (
              <>
                <ArrowRight className="size-4" />
                Upload & Process
              </>
            )}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
