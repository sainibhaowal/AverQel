"use client";

import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import {
  Upload,
  CheckCircle2,
  AlertCircle,
  Loader2,
  HardDrive,
  ShieldCheck,
  Database,
  ListChecks,
  type LucideIcon,
} from "lucide-react";
import { fetchWithAuth } from "@/lib/api";

interface DropzoneProps {
  onSuccess: () => void;
  onCancel?: () => void;
  allowedExtensions: string[];
}

export default function Dropzone({ onSuccess, onCancel, allowedExtensions }: DropzoneProps) {
  const [file, setFile] = useState<File | null>(null);
  const [status, setStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
  const [uploadPhase, setUploadPhase] = useState<"validate" | "scan" | "store" | "queue">(
    "validate",
  );
  const [errorMessage, setErrorMessage] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);

  // Storage Quota
  const [storageUsed, setStorageUsed] = useState(0);
  const [storageLimit, setStorageLimit] = useState(1073741824); // 1GB fallback
  const [maxUploadSize, setMaxUploadSize] = useState(52428800); // 50MB fallback

  useEffect(() => {
    // Fetch stats and limits
    Promise.all([
      fetchWithAuth("/dashboard/stats").then((res) => res.json()),
      fetchWithAuth("/capabilities").then((res) => res.json()),
    ])
      .then(([stats, caps]) => {
        setStorageUsed(stats.storage_used_bytes || 0);
        if (caps.limits) {
          setStorageLimit(caps.limits.max_tenant_storage_bytes);
          setMaxUploadSize(caps.limits.max_upload_size_bytes);
        }
      })
      .catch((fetchError) => console.warn("Failed to fetch storage limits", fetchError));
  }, []);

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
  };

  const validateFile = (selectedFile: File) => {
    // Check individual file size
    if (selectedFile.size > maxUploadSize) {
      setStatus("error");
      setErrorMessage(`File is too large. Maximum size is ${formatBytes(maxUploadSize)}.`);
      return false;
    }

    // Check total quota
    if (storageUsed + selectedFile.size > storageLimit) {
      setStatus("error");
      setErrorMessage(
        `Storage quota exceeded. You have ${formatBytes(storageLimit - storageUsed)} remaining.`,
      );
      return false;
    }

    // Check extension
    const ext = `.${selectedFile.name.split(".").pop()?.toLowerCase()}`;
    if (allowedExtensions.length > 0 && !allowedExtensions.includes(ext)) {
      setStatus("error");
      setErrorMessage(`Unsupported file format. Please upload accepted formats only.`);
      return false;
    }

    return true;
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      if (validateFile(selectedFile)) {
        setFile(selectedFile);
        setStatus("idle");
        setUploadPhase("validate");
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const selectedFile = e.dataTransfer.files[0];
      if (validateFile(selectedFile)) {
        setFile(selectedFile);
        setStatus("idle");
        setUploadPhase("validate");
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleUpload = async () => {
    if (!file) return;

    setStatus("uploading");
    setUploadPhase("scan");
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = (await fetchWithAuth("/documents/upload", {
        method: "POST",
        body: formData,
        headers: {
          "Idempotency-Key": crypto.randomUUID(),
        },
      })) as Response;

      if (response.ok) {
        setUploadPhase("store");
        await new Promise((resolve) => window.setTimeout(resolve, 250));
        setUploadPhase("queue");
        setStatus("success");
        setTimeout(() => {
          onSuccess();
          setFile(null);
          setStatus("idle");
          setUploadPhase("validate");
        }, 1500);
      } else {
        const errorData = await response.json();
        setStatus("error");
        setErrorMessage(errorData.message || "Upload failed. Please try again.");
      }
    } catch {
      setStatus("error");
      setErrorMessage("Network error. Please check your connection.");
    }
  };

  const usagePercent = Math.min(100, Math.max(0, (storageUsed / storageLimit) * 100));

  return (
    <div className="flex flex-col gap-6">
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => status === "idle" && fileInputRef.current?.click()}
        className={`relative cursor-pointer overflow-hidden rounded-3xl border-2 border-dashed p-12 text-center transition-all ${file ? "border-accent/40 bg-accent/5 shadow-inner" : isDragging ? "border-accent bg-accent/10 scale-[0.98] shadow-2xl" : "border-glass-border hover:border-accent/30 hover:bg-accent/[0.02]"} ${status === "uploading" ? "pointer-events-none opacity-50" : ""} `}
      >
        <div
          className={`bg-accent/5 absolute top-0 right-0 -mt-16 -mr-16 h-32 w-32 rounded-full blur-3xl transition-opacity duration-500 ${isDragging ? "opacity-100" : "opacity-0"}`}
        />

        <input
          type="file"
          ref={fileInputRef}
          onChange={handleFileChange}
          className="hidden"
          accept={allowedExtensions.length > 0 ? allowedExtensions.join(",") : undefined}
        />

        {status === "success" ? (
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="flex flex-col items-center"
          >
            <div className="bg-success/10 border-success/20 mb-4 flex h-16 w-16 items-center justify-center rounded-full border">
              <CheckCircle2 size={36} className="text-success" />
            </div>
            <p className="text-foreground text-xl font-black tracking-tight">
              Transmission Complete
            </p>
            <p className="text-success mt-1 text-[11px] font-bold tracking-widest uppercase">
              Handoff to ingestion pipeline successful
            </p>
          </motion.div>
        ) : status === "error" ? (
          <div className="flex flex-col items-center">
            <div className="bg-danger/10 border-danger/20 mb-4 flex h-16 w-16 items-center justify-center rounded-full border">
              <AlertCircle size={36} className="text-danger" />
            </div>
            <p className="text-foreground text-danger text-xl font-black tracking-tight">
              Transmission Failed
            </p>
            <p className="text-danger mt-1 text-[11px] font-bold tracking-widest uppercase">
              {errorMessage}
            </p>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setStatus("idle");
                setFile(null);
                setUploadPhase("validate");
              }}
              className="theme-pill !bg-danger/10 !text-danger mt-6 transition-transform hover:scale-105"
            >
              Reset Upload
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center">
            <div
              className={`mb-5 flex h-20 w-20 items-center justify-center rounded-[2rem] transition-all duration-500 ${file ? "bg-accent text-accent-foreground shadow-accent/30 rotate-[15deg] shadow-xl" : "bg-foreground/5 text-foreground/20"}`}
            >
              <Upload size={38} className="stroke-[2.5]" />
            </div>
            {file ? (
              <>
                <p className="text-foreground max-w-full truncate px-4 text-lg font-black tracking-tight">
                  {file.name}
                </p>
                <p className="text-foreground/30 mt-1.5 text-[11px] font-bold tracking-[0.2em] uppercase">
                  {formatBytes(file.size)}
                </p>
                <div className="text-accent mt-5 flex animate-pulse items-center gap-2 text-[10px] font-black tracking-[0.3em] uppercase">
                  <div className="bg-accent h-1.5 w-1.5 rounded-full" />
                  Ready to Transmit
                  <div className="bg-accent h-1.5 w-1.5 rounded-full" />
                </div>
              </>
            ) : (
              <>
                <p className="text-foreground text-xl font-black tracking-tight">
                  Drop Source Matrix
                </p>
                <p className="text-muted-foreground/40 mt-1.5 text-[11px] font-black tracking-widest uppercase">
                  or click to browse local storage
                </p>
              </>
            )}
          </div>
        )}
      </div>

      <div className="border-glass-border bg-surface-0 rounded-[1.45rem] border p-5 shadow-[0_14px_36px_-28px_rgba(99,102,241,0.22)]">
        <div className="text-muted-foreground/60 mb-3 flex items-center justify-between text-[10px] font-black tracking-[0.2em] uppercase">
          <span className="flex items-center gap-2 font-black">
            <HardDrive size={14} className="text-primary" /> Tenant Quota
          </span>
          <span className="text-foreground font-black tabular-nums">
            {formatBytes(storageUsed)} / {formatBytes(storageLimit)}
          </span>
        </div>
        <div className="bg-foreground/5 h-1.5 w-full overflow-hidden rounded-full">
          <div
            className={`h-full rounded-full transition-all duration-1000 ${usagePercent > 90 ? "bg-danger" : "from-primary to-accent bg-gradient-to-r shadow-[0_0_8px_rgba(var(--primary),0.4)]"}`}
            style={{ width: `${usagePercent}%` }}
          />
        </div>
        <div className="text-muted-foreground/20 mt-3 flex items-center justify-between text-[9px] font-black tracking-widest uppercase">
          <span>Payload limit: {formatBytes(maxUploadSize)}</span>
          <span>{Math.round(usagePercent)}% Utilized</span>
        </div>
      </div>

      <div className="flex gap-4">
        {onCancel && (
          <button
            onClick={onCancel}
            disabled={status === "uploading"}
            className="border-glass-border hover:bg-primary/5 hover:text-primary text-foreground/80 bg-surface-0 h-14 flex-1 rounded-2xl border text-sm font-black tracking-widest uppercase shadow-sm transition-all disabled:opacity-30"
          >
            Abort
          </button>
        )}
        <button
          onClick={handleUpload}
          disabled={!file || status !== "idle"}
          className={`flex h-14 flex-[2] items-center justify-center gap-3 rounded-2xl text-sm font-black tracking-widest uppercase shadow-xl transition-all ${!file || status !== "idle" ? "bg-muted text-muted-foreground cursor-not-allowed shadow-none" : "bg-primary shadow-primary/25 text-white hover:scale-[1.02] hover:brightness-110 active:scale-[0.98]"} `}
        >
          {status === "uploading" ? (
            <>
              <Loader2 size={18} className="animate-spin" />
              <span className="animate-pulse">Transmitting...</span>
            </>
          ) : (
            <>
              <HardDrive size={18} />
              <span>Ingest Document</span>
            </>
          )}
        </button>
      </div>

      {status === "uploading" || status === "success" ? (
        <div
          className="border-primary/15 bg-primary/[0.04] rounded-2xl border p-4"
          aria-live="polite"
          aria-label="Document security and ingestion progress"
        >
          <div className="mb-3 flex items-center justify-between">
            <p className="text-foreground text-xs font-black tracking-widest uppercase">
              Secure upload progress
            </p>
            <span className="text-primary text-[10px] font-bold uppercase">
              {status === "success" ? "Complete" : "Live"}
            </span>
          </div>
          <div className="grid grid-cols-4 gap-2">
            {(
              [
                ["validate", "Validate", CheckCircle2],
                ["scan", "Malware scan", ShieldCheck],
                ["store", "Private storage", Database],
                ["queue", "Index queue", ListChecks],
              ] as Array<[string, string, LucideIcon]>
            ).map(([phase, label, Icon]) => {
              const phases = ["validate", "scan", "store", "queue"];
              const current = status === "success" ? phases.length : phases.indexOf(uploadPhase);
              const index = phases.indexOf(String(phase));
              const complete = current > index;
              const active = status === "uploading" && current === index;
              const PhaseIcon = Icon as typeof CheckCircle2;
              return (
                <div
                  key={String(phase)}
                  className={`rounded-xl border px-2 py-2 text-center transition-colors ${
                    complete
                      ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                      : active
                        ? "border-primary/40 bg-primary/10 text-primary"
                        : "border-foreground/10 text-foreground/30"
                  }`}
                >
                  {active ? (
                    <Loader2 size={14} className="mx-auto mb-1 animate-spin" />
                  ) : (
                    <PhaseIcon size={14} className="mx-auto mb-1" />
                  )}
                  <span className="block text-[8px] font-black tracking-wider uppercase">
                    {label}
                  </span>
                </div>
              );
            })}
          </div>
          <p className="text-foreground/45 mt-3 text-[10px] leading-relaxed">
            The security scan completes before the file is stored. A successful response means the
            original file passed the scan and was queued for background indexing.
          </p>
        </div>
      ) : null}
    </div>
  );
}
