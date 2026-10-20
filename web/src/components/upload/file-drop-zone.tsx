"use client";

import { useCallback, useRef, useState, DragEvent, ChangeEvent } from "react";
import { Upload, FileText, Image, AlertTriangle, CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { validateFiles, formatFileSize, type ValidatedFile } from "@/lib/upload/validation";

interface FileItem {
  file: File;
  type: "pdf" | "image" | "dxf";
  size: number;
  status: "pending" | "uploading" | "success" | "error";
  error?: string;
}

interface FileDropZoneProps {
  onFilesSelected: (files: ValidatedFile[]) => void;
  maxFiles?: number;
  disabled?: boolean;
  acceptedTypes?: string;
}

export function FileDropZone({ onFilesSelected, maxFiles = 10, disabled = false, acceptedTypes }: FileDropZoneProps) {
  const [isDragActive, setIsDragActive] = useState(false);
  const [files, setFiles] = useState<FileItem[]>([]);
  const [rejected, setRejected] = useState<{ file: File; reason: string }[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const [totalSize, setTotalSize] = useState(0);

  const getFileIcon = (type: string) => {
    switch (type) {
      case "pdf": return <FileText className="size-5 text-red-500" />;
      case "image": return <Image className="size-5 text-blue-500" />;
      default: return <FileText className="size-5 text-gray-500" />;
    }
  };

  const handleFiles = useCallback(
    (newFiles: FileList | File[]) => {
      const fileArray = Array.from(newFiles);
      const { valid, rejected: rejectedFiles } = validateFiles(fileArray);

      setRejected(rejectedFiles);
      setFiles(
        valid.map((v) => ({
          file: v.file,
          type: v.type,
          size: v.size,
          status: "pending" as const,
        }))
      );
      setTotalSize(valid.reduce((sum, v) => sum + v.size, 0));
      onFilesSelected(valid);
    },
    [onFilesSelected]
  );

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      event.stopPropagation();
      setIsDragActive(false);
      if (disabled) return;
      if (event.dataTransfer.files.length) handleFiles(event.dataTransfer.files);
    },
    [disabled, handleFiles]
  );

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    if (!disabled) setIsDragActive(true);
  }, [disabled]);

  const onDragLeave = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragActive(false);
  }, []);

  const onClick = useCallback(() => {
    if (!disabled) inputRef.current?.click();
  }, [disabled]);

  const onChange = useCallback(
    (event: ChangeEvent<HTMLInputElement>) => {
      if (event.target.files && event.target.files.length) handleFiles(event.target.files);
      event.target.value = "";
    },
    [handleFiles]
  );

  const removeFile = useCallback((index: number) => {
    setFiles((prev) => {
      const next = [...prev];
      const removed = next.splice(index, 1)[0];
      setTotalSize((s) => s - removed.size);
      onFilesSelected(next.filter((f) => f.status !== "error").map((f) => ({ file: f.file, type: f.type, size: f.size })));
      return next;
    });
  }, [onFilesSelected]);

  const retryFile = useCallback((index: number) => {
    setFiles((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], status: "pending", error: undefined };
      return next;
    });
  }, []);

  return (
    <div className="space-y-4">
      <div
        ref={inputRef}
        className={cn(
          "relative rounded-2xl border-2 border-dashed transition-colors",
          isDragActive
            ? "border-primary bg-primary/5"
            : "border-border hover:border-primary/50",
          disabled && "opacity-50 cursor-not-allowed"
        )}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={onClick}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-label="Drop zone for file upload"
      >
        <input
          type="file"
          ref={inputRef}
          onChange={onChange}
          multiple
          accept={acceptedTypes ?? ".pdf,.png,.jpg,.jpeg,.webp,.dxf"}
          disabled={disabled || files.length >= maxFiles}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer"
          aria-hidden="true"
        />
        <div className="p-8 text-center">
          <Upload className="mx-auto size-12 text-muted-foreground" />
          <p className="mt-4 text-lg font-medium">
            {isDragActive ? "Drop files here" : "Drag & drop files here, or click to browse"}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            PDF, PNG, JPG, WEBP, DXF • Max {maxFiles} files • 25 MB each
          </p>
        </div>
      </div>

      {files.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">{files.length} file(s) selected</span>
            <span className="text-muted-foreground">Total: {formatFileSize(totalSize)}</span>
          </div>
          <div className="max-h-60 overflow-y-auto space-y-2">
            {files.map((item, index) => (
              <div
                key={index}
                className={cn(
                  "flex items-center gap-3 rounded-xl border p-3 transition-colors",
                  item.status === "success" && "border-emerald-500/30 bg-emerald-500/5",
                  item.status === "error" && "border-destructive/30 bg-destructive/5",
                  item.status === "uploading" && "border-primary/30 bg-primary/5",
                  item.status === "pending" && "border-border bg-card"
                )}
              >
                <div className="flex items-center justify-center size-10 rounded-lg bg-muted">{getFileIcon(item.type)}</div>
                <div className="flex-1 min-w-0">
                  <p className="truncate font-medium text-sm">{item.file.name}</p>
                  <p className="text-xs text-muted-foreground">{formatFileSize(item.size)} • {item.type.toUpperCase()}</p>
                  {item.error && <p className="text-xs text-destructive mt-1">{item.error}</p>}
                </div>
                <div className="flex items-center gap-2">
                  {item.status === "uploading" && <Loader2 className="size-4 animate-spin text-primary" />}
                  {item.status === "success" && <CheckCircle2 className="size-4 text-emerald-500" />}
                  {item.status === "error" && <AlertTriangle className="size-4 text-destructive" />}
                  {item.status !== "success" && (
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => retryFile(index)}
                      disabled={item.status === "uploading"}
                      aria-label="Retry upload"
                    >
                      <Loader2 className="size-4" />
                    </Button>
                  )}
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => removeFile(index)}
                    disabled={item.status === "uploading"}
                    aria-label="Remove file"
                  >
                    <XCircle className="size-4 text-muted-foreground" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {rejected.length > 0 && (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 p-3">
          <p className="font-medium text-destructive text-sm">Rejected files:</p>
          <ul className="mt-2 space-y-1 text-xs text-muted-foreground">
            {rejected.map((r, i) => (
              <li key={i} className="flex items-center gap-2">
                <XCircle className="size-3 shrink-0" />
                <span className="truncate">{r.file.name}</span>
                <span className="text-destructive/70">— {r.reason}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {disabled && files.length === 0 && rejected.length === 0 && (
        <p className="text-center text-sm text-muted-foreground">Upload disabled — processing in progress</p>
      )}
    </div>
  );
}
