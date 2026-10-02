"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, HardDrive, Loader2, Upload, X } from "lucide-react";
import { fetchWithAuth } from "@/lib/api";

interface DropzoneProps { onSuccess: () => void; onCancel?: () => void; allowedExtensions: string[]; }
type StagedFile = { id: string; file: File; state: "ready" | "uploading" | "complete" | "error"; error?: string; };
const formatBytes = (bytes: number) => {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  return `${(bytes / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
};

export default function Dropzone({ onSuccess, onCancel, allowedExtensions }: DropzoneProps) {
  const [items, setItems] = useState<StagedFile[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [storageUsed, setStorageUsed] = useState(0);
  const [storageLimit, setStorageLimit] = useState(1_073_741_824);
  const [maxUploadSize, setMaxUploadSize] = useState(52_428_800);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    void Promise.all([fetchWithAuth("/dashboard/stats"), fetchWithAuth("/capabilities")]).then(async ([statsResponse, capsResponse]) => {
      const stats = statsResponse.ok ? await statsResponse.json() : {};
      const caps = capsResponse.ok ? await capsResponse.json() : {};
      setStorageUsed(Number(stats.storage_used_bytes) || 0);
      if (caps.limits) {
        setStorageLimit(Number(caps.limits.max_tenant_storage_bytes) || 1_073_741_824);
        setMaxUploadSize(Number(caps.limits.max_upload_size_bytes) || 52_428_800);
      }
    }).catch(() => setMessage("Storage limits could not be refreshed. Server checks remain active."));
  }, []);

  const addFiles = (input: FileList | File[]) => {
    const accepted: StagedFile[] = [];
    const errors: string[] = [];
    let nextBytes = items.reduce((total, item) => total + item.file.size, 0);
    for (const file of Array.from(input)) {
      const extension = `.${file.name.split(".").pop()?.toLowerCase() || ""}`;
      const duplicate = [...items, ...accepted].some((item) => item.file.name === file.name && item.file.size === file.size);
      if (!file.size || file.size > maxUploadSize) errors.push(`${file.name}: maximum size is ${formatBytes(maxUploadSize)}.`);
      else if (allowedExtensions.length && !allowedExtensions.includes(extension)) errors.push(`${file.name}: unsupported format.`);
      else if (storageUsed + nextBytes + file.size > storageLimit) errors.push(`${file.name}: exceeds remaining storage quota.`);
      else if (!duplicate) { accepted.push({ id: crypto.randomUUID(), file, state: "ready" }); nextBytes += file.size; }
    }
    if (accepted.length) setItems((current) => [...current, ...accepted]);
    setMessage(errors.length ? errors.slice(0, 3).join(" ") : null);
  };

  const uploadAll = async () => {
    const pending = items.filter((item) => item.state === "ready" || item.state === "error");
    if (!pending.length) return;
    setIsUploading(true); setMessage(null); abortRef.current = new AbortController();
    let completed = 0;
    for (const item of pending) {
      if (abortRef.current.signal.aborted) break;
      setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, state: "uploading", error: undefined } : entry));
      const body = new FormData(); body.append("file", item.file);
      try {
        const response = await fetchWithAuth("/documents/upload", { method: "POST", body, signal: abortRef.current.signal, headers: { "Idempotency-Key": crypto.randomUUID() } }) as Response;
        if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.message || "The server rejected this file."); }
        completed += 1;
        setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, state: "complete" } : entry));
      } catch (error) {
        const detail = abortRef.current.signal.aborted ? "Upload cancelled." : error instanceof Error ? error.message : "Upload failed.";
        setItems((current) => current.map((entry) => entry.id === item.id ? { ...entry, state: "error", error: detail } : entry));
      }
    }
    setIsUploading(false); abortRef.current = null;
    if (completed) { onSuccess(); setMessage(`${completed} file${completed === 1 ? "" : "s"} securely queued for ingestion.`); }
  };

  const pendingCount = items.filter((item) => item.state === "ready" || item.state === "error").length;
  const totalBytes = items.reduce((total, item) => total + item.file.size, 0);
  return <div className="flex min-h-0 flex-col gap-4">
    <div onClick={() => !isUploading && inputRef.current?.click()} onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }} onDragLeave={(event) => { event.preventDefault(); setIsDragging(false); }} onDrop={(event) => { event.preventDefault(); setIsDragging(false); addFiles(event.dataTransfer.files); }} className={`cursor-pointer rounded-2xl border-2 border-dashed p-7 text-center transition ${isDragging ? "border-emerald-500 bg-emerald-50/80 scale-[0.99] dark:bg-emerald-950/30" : "border-emerald-500/30 bg-emerald-50/35 hover:border-emerald-500/60 hover:bg-emerald-50/70 dark:bg-emerald-950/15"} ${isUploading ? "pointer-events-none opacity-60" : ""}`}>
      <input ref={inputRef} type="file" multiple className="sr-only" accept={allowedExtensions.join(",")} onChange={(event) => { if (event.target.files) addFiles(event.target.files); event.target.value = ""; }} />
      <div className="mx-auto mb-3 grid h-12 w-12 place-items-center rounded-xl bg-emerald-500/12 text-emerald-700 dark:text-emerald-300"><Upload size={24} /></div><p className="text-foreground font-bold">Drop Source Matrix</p><p className="mt-1 text-xs text-muted-foreground">Drag one or many files here, or click to browse local storage.</p>
    </div>
    <div className="rounded-xl border border-emerald-500/20 bg-emerald-50/40 px-3 py-2 text-xs dark:bg-emerald-950/15"><div className="flex items-center justify-between gap-3"><span className="flex items-center gap-2 font-semibold"><HardDrive size={14} className="text-emerald-600" />Tenant quota</span><span className="tabular-nums">{formatBytes(storageUsed)} / {formatBytes(storageLimit)}</span></div><p className="mt-1 text-[11px] text-muted-foreground">{items.length} staged · {formatBytes(totalBytes)} · {formatBytes(maxUploadSize)} per file</p></div>
    {items.length ? <div className="custom-scrollbar max-h-48 space-y-1 overflow-y-auto rounded-xl border border-emerald-500/15 p-2" aria-label="Files staged for ingestion"><p className="px-2 pb-1 text-[10px] font-bold tracking-[0.14em] text-emerald-800 uppercase dark:text-emerald-200">{items.length} file{items.length === 1 ? "" : "s"} staged for upload</p>{items.map((item) => <div key={item.id} className="flex min-w-0 items-center gap-2 rounded-lg px-2 py-2 text-xs"><span className={item.state === "complete" ? "text-emerald-600" : item.state === "error" ? "text-rose-600" : "text-emerald-700"}>{item.state === "uploading" ? <Loader2 size={14} className="animate-spin" /> : item.state === "complete" ? <CheckCircle2 size={14} /> : item.state === "error" ? <AlertCircle size={14} /> : <HardDrive size={14} />}</span><span className="min-w-0 flex-1 truncate font-medium">{item.file.name}</span><span className="shrink-0 text-muted-foreground">{item.state === "error" ? item.error : item.state}</span>{!isUploading && item.state !== "uploading" ? <button type="button" onClick={(event) => { event.stopPropagation(); setItems((current) => current.filter((entry) => entry.id !== item.id)); }} className="text-muted-foreground hover:text-rose-600" aria-label={`Remove ${item.file.name}`}><X size={14} /></button> : null}</div>)}</div> : null}
    {message ? <p className="rounded-lg border border-emerald-500/20 bg-emerald-50 px-3 py-2 text-xs text-emerald-900 dark:bg-emerald-950/25 dark:text-emerald-100">{message}</p> : null}
    <div className="flex gap-3"><button type="button" onClick={() => isUploading ? abortRef.current?.abort() : onCancel?.()} className="documents-cancel-action flex-1 rounded-xl border border-emerald-500/25 px-3 py-3 text-xs font-bold text-emerald-800 hover:bg-emerald-50 dark:text-emerald-200">{isUploading ? "Cancel batch" : "Cancel"}</button><button type="button" onClick={() => void uploadAll()} disabled={!pendingCount || isUploading} className="documents-ingest-action flex flex-[2] items-center justify-center gap-2 rounded-xl bg-emerald-600 px-3 py-3 text-xs font-bold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-45">{isUploading ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}{isUploading ? "Ingesting batch…" : `Ingest ${pendingCount} file${pendingCount === 1 ? "" : "s"}`}</button></div>
  </div>;
}
