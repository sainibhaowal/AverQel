"use client";

import { fetchWithAuth } from "@/lib/api";
import { MAX_CONCURRENT_QUERY_UPLOADS, MAX_QUERY_ATTACHMENTS } from "./query-limits";

export const QUERY_DRAFT_ID = "grounded-query-current-draft";

export interface QueryUploadAttachment {
  id: string;
  draftId: string;
  ownerId: string;
  name: string;
  sizeBytes: number;
  status: "queued" | "uploading" | "processing" | "ready" | "failed";
  documentId?: string;
  progress?: number;
  stage?: string;
  rowCount?: number;
  tabular?: boolean;
  error?: string;
}

interface UploadRecord {
  ownerId: string;
  idempotencyKey: string;
  file: File | null;
  controller: AbortController | null;
  running: boolean;
}

interface UploadSlotPool {
  active: number;
  waiters: Array<() => void>;
}

const listeners = new Set<() => void>();
const records = new Map<string, UploadRecord>();
const uploadSlotPool: UploadSlotPool = { active: 0, waiters: [] };
let snapshot: QueryUploadAttachment[] = [];

function publish(next: QueryUploadAttachment[]): void {
  snapshot = next;
  listeners.forEach((listener) => listener());
}

function updateUpload(
  id: string,
  update: (current: QueryUploadAttachment) => QueryUploadAttachment,
): void {
  const index = snapshot.findIndex((item) => item.id === id);
  if (index < 0) return;
  const next = [...snapshot];
  const current = next[index];
  if (!current) return;
  next[index] = update(current);
  publish(next);
}

function acquireUploadSlot(pool: UploadSlotPool, signal: AbortSignal): Promise<boolean> {
  return new Promise((resolve) => {
    const grant = () => {
      if (signal.aborted) {
        resolve(false);
        return;
      }
      pool.active += 1;
      resolve(true);
    };

    if (signal.aborted) {
      resolve(false);
      return;
    }
    if (pool.active < MAX_CONCURRENT_QUERY_UPLOADS) {
      grant();
      return;
    }

    let waiter: (() => void) | null = null;
    const onAbort = () => {
      if (waiter) pool.waiters = pool.waiters.filter((candidate) => candidate !== waiter);
      resolve(false);
    };
    waiter = () => {
      signal.removeEventListener("abort", onAbort);
      grant();
    };
    pool.waiters.push(waiter);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

function releaseUploadSlot(pool: UploadSlotPool): void {
  pool.active = Math.max(0, pool.active - 1);
  pool.waiters.shift()?.();
}

function isCurrentOwner(ownerId: string): boolean {
  try {
    const storedUser = localStorage.getItem("averqel_user");
    if (!storedUser) return false;
    const parsed = JSON.parse(storedUser) as { id?: unknown; tenant_id?: unknown };
    return `${String(parsed.tenant_id ?? "")}:${String(parsed.id ?? "")}` === ownerId;
  } catch {
    return false;
  }
}

function waitForNextCheck(signal: AbortSignal, delayMs: number): Promise<boolean> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve(false);
      return;
    }
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve(true);
    }, delayMs);
    const onAbort = () => {
      window.clearTimeout(timer);
      resolve(false);
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

async function waitForIndexing(
  documentId: string,
  signal: AbortSignal,
  allowEmpty: boolean,
): Promise<void> {
  const deadline = Date.now() + 10 * 60 * 1000;
  let intervalMs = 1_500;
  let transientFailures = 0;

  while (!signal.aborted && Date.now() < deadline) {
    const attachment = snapshot.find((item) => item.documentId === documentId);
    if (!attachment || !isCurrentOwner(attachment.ownerId)) {
      throw new Error("The signed-in account changed, so this upload check was stopped.");
    }
    let response: Response;
    try {
      response = (await fetchWithAuth(`/documents/${documentId}/status`, {
        signal,
        timeoutMs: 20_000,
        silentTimeout: true,
      })) as Response;
    } catch {
      if (signal.aborted) return;
      transientFailures += 1;
      if (transientFailures > 3) {
        throw new Error("Could not reach Documents Hub to check this file's indexing status.");
      }
      if (!(await waitForNextCheck(signal, intervalMs + Math.floor(Math.random() * 300)))) return;
      intervalMs = Math.min(8_000, Math.round(intervalMs * 1.5));
      continue;
    }

    if (!response.ok) {
      if (response.status === 429 || response.status >= 500) {
        transientFailures += 1;
        if (transientFailures > 3) {
          throw new Error(
            `Documents Hub could not report indexing status (HTTP ${response.status}).`,
          );
        }
        if (!(await waitForNextCheck(signal, intervalMs + Math.floor(Math.random() * 300)))) return;
        intervalMs = Math.min(8_000, Math.round(intervalMs * 1.5));
        continue;
      }
      throw new Error(
        response.status === 403 || response.status === 404
          ? "This document is no longer available to your account."
          : `Could not check document indexing status (HTTP ${response.status}).`,
      );
    }

    transientFailures = 0;
    const status = (await response.json()) as {
      status?: string;
      ingestion_status?: string | null;
      quarantined?: boolean;
      total_chunk_count?: number;
    };
    if (status.quarantined) {
      throw new Error("Documents Hub quarantined this file, so it cannot be used in a query.");
    }

    const documentStatus = status.status?.toLowerCase();
    const ingestionStatus = status.ingestion_status?.toLowerCase();
    if (documentStatus === "indexed" && (ingestionStatus === "indexed" || !ingestionStatus)) {
      if (!allowEmpty && (status.total_chunk_count ?? 0) < 1) {
        throw new Error("No searchable text was extracted from this file.");
      }
      return;
    }
    if (
      ["failed", "dead_lettered", "error"].includes(documentStatus || "") ||
      ["failed", "dead_lettered", "error"].includes(ingestionStatus || "")
    ) {
      throw new Error(
        "Documents Hub could not index this file. Check its status in Documents Hub.",
      );
    }

    if (!(await waitForNextCheck(signal, intervalMs + Math.floor(Math.random() * 300)))) return;
    intervalMs = Math.min(8_000, Math.round(intervalMs * 1.5));
  }

  if (!signal.aborted) {
    throw new Error("Indexing is taking longer than expected. Check the file in Documents Hub.");
  }
}

const TABLE_FILE_PATTERN = /\.(csv|tsv)$/i;
const MAX_QUERY_DATASET_FILE_SIZE_BYTES = 25 * 1024 * 1024;

function isTabularFile(file: Pick<File, "name" | "type">): boolean {
  const contentType = file.type.toLowerCase().split(";", 1)[0];
  return (
    TABLE_FILE_PATTERN.test(file.name) ||
    contentType === "text/csv" ||
    contentType === "text/x-csv" ||
    contentType === "text/tab-separated-values" ||
    contentType === "text/tsv"
  );
}

function readApiError(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object") {
    const data = payload as { detail?: unknown; message?: unknown; error?: unknown };
    if (typeof data.message === "string") return data.message;
    if (data.error && typeof data.error === "object") {
      const apiError = data.error as { message?: unknown };
      if (typeof apiError.message === "string") return apiError.message;
    }
    if (typeof data.detail === "string") return data.detail;
    if (data.detail && typeof data.detail === "object") {
      const detail = data.detail as { message?: unknown };
      if (typeof detail.message === "string") return detail.message;
    }
  }
  return fallback;
}

async function readFileBytes(file: File): Promise<ArrayBuffer> {
  if (typeof file.arrayBuffer === "function") return file.arrayBuffer();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error || new Error("Could not read the selected file."));
    reader.onload = () => {
      if (reader.result instanceof ArrayBuffer) resolve(reader.result);
      else reject(new Error("The selected file could not be read as bytes."));
    };
    reader.readAsArrayBuffer(file);
  });
}

async function waitForDatasetIndex(
  id: string,
  documentId: string,
  controller: AbortController,
  retry: boolean,
): Promise<void> {
  const signal = controller.signal;
  const attachment = snapshot.find((item) => item.id === id);
  if (!attachment || !(attachment.tabular ?? TABLE_FILE_PATTERN.test(attachment.name))) return;
  if (attachment.sizeBytes > MAX_QUERY_DATASET_FILE_SIZE_BYTES) {
    throw new Error("Grounded Query table indexing supports CSV or TSV files up to 25 MiB.");
  }
  if (!isCurrentOwner(attachment.ownerId)) {
    throw new Error("The signed-in account changed, so this table check was stopped.");
  }

  const start = (await fetchWithAuth(`/queries/datasets/${documentId}/prepare`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ retry }),
    signal,
    timeoutMs: 20_000,
  })) as Response;
  const prepared = (await start.json().catch(() => ({}))) as Record<string, unknown>;
  if (!start.ok)
    throw new Error(readApiError(prepared, `Could not prepare this table (HTTP ${start.status}).`));

  const deadline = Date.now() + 10 * 60 * 1000;
  let intervalMs = 1_000;
  let transientFailures = 0;
  let current = prepared;
  while (!signal.aborted && Date.now() < deadline) {
    const status = String(current.status || "").toLowerCase();
    const progress = typeof current.progress === "number" ? current.progress : 0;
    updateUpload(id, (item) => ({
      ...item,
      status: status === "ready" ? "ready" : "processing",
      progress,
      stage: typeof current.stage === "string" ? current.stage : item.stage,
      rowCount: typeof current.row_count === "number" ? current.row_count : item.rowCount,
      error: undefined,
    }));
    if (status === "ready") return;
    if (status === "failed") {
      throw new Error(
        typeof current.error_message === "string"
          ? current.error_message
          : "Grounded Query could not index this table.",
      );
    }
    if (!isCurrentOwner(attachment.ownerId)) {
      throw new Error("The signed-in account changed, so this table check was stopped.");
    }
    if (!(await waitForNextCheck(signal, intervalMs + Math.floor(Math.random() * 300)))) return;
    let response: Response;
    try {
      response = (await fetchWithAuth(`/queries/datasets/${documentId}/status`, {
        signal,
        timeoutMs: 20_000,
        silentTimeout: true,
      })) as Response;
    } catch {
      if (signal.aborted) return;
      transientFailures += 1;
      if (transientFailures > 4)
        throw new Error("Could not reach Grounded Query to check table indexing status.");
      intervalMs = Math.min(8_000, Math.round(intervalMs * 1.5));
      continue;
    }
    if (!response.ok) {
      if (response.status === 429 || response.status >= 500) {
        transientFailures += 1;
        if (transientFailures > 4)
          throw new Error(
            `Grounded Query could not report table status (HTTP ${response.status}).`,
          );
        intervalMs = Math.min(8_000, Math.round(intervalMs * 1.5));
        continue;
      }
      throw new Error(`Could not check table indexing status (HTTP ${response.status}).`);
    }
    transientFailures = 0;
    current = (await response.json()) as Record<string, unknown>;
    intervalMs = Math.min(5_000, Math.round(intervalMs * 1.3));
  }
  if (!signal.aborted)
    throw new Error(
      "Table indexing is taking longer than expected. Check the attachment status and retry.",
    );
}

async function trackIndexing(
  id: string,
  documentId: string,
  controller: AbortController,
  retryDataset = false,
) {
  try {
    const attachment = snapshot.find((item) => item.id === id);
    const isTable = Boolean(
      attachment && (attachment.tabular ?? TABLE_FILE_PATTERN.test(attachment.name)),
    );
    await waitForIndexing(documentId, controller.signal, isTable);
    await waitForDatasetIndex(id, documentId, controller, retryDataset);
    if (!controller.signal.aborted) {
      updateUpload(id, (item) => ({ ...item, status: "ready", progress: 100, error: undefined }));
    }
  } catch (error) {
    if (!controller.signal.aborted) {
      updateUpload(id, (item) => ({
        ...item,
        status: "failed",
        error: error instanceof Error ? error.message : "Indexing failed.",
      }));
    }
  } finally {
    const record = records.get(id);
    if (record?.controller === controller) {
      record.controller = null;
      record.running = false;
    }
  }
}

async function uploadFile(id: string): Promise<void> {
  const record = records.get(id);
  if (!record || !record.file || record.running) return;

  const controller = new AbortController();
  record.controller = controller;
  record.running = true;
  const hasSlot = await acquireUploadSlot(uploadSlotPool, controller.signal);
  if (!hasSlot) {
    if (record.controller === controller) {
      record.controller = null;
      record.running = false;
    }
    return;
  }

  let documentId: string | undefined;
  try {
    if (controller.signal.aborted || !isCurrentOwner(record.ownerId)) return;
    updateUpload(id, (item) => ({ ...item, status: "uploading", error: undefined }));
    const file = record.file;
    if (!file) return;
    if (isTabularFile(file) && file.size > MAX_QUERY_DATASET_FILE_SIZE_BYTES) {
      throw new Error("Grounded Query table indexing supports CSV or TSV files up to 25 MiB.");
    }
    const digest = await crypto.subtle.digest("SHA-256", await readFileBytes(file));
    const sha256 = Array.from(new Uint8Array(digest), (byte) =>
      byte.toString(16).padStart(2, "0"),
    ).join("");
    const matchResponse = (await fetchWithAuth("/queries/attachments/resolve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sha256 }),
      signal: controller.signal,
      timeoutMs: 20_000,
    })) as Response;
    if (!matchResponse.ok)
      throw new Error(
        `Could not check Documents Hub for this file (HTTP ${matchResponse.status}).`,
      );
    const match = (await matchResponse.json()) as {
      found?: boolean;
      document_id?: string;
      filename?: string;
      tabular?: boolean;
    };
    if (match.found && match.document_id) {
      documentId = match.document_id;
      record.file = null;
      updateUpload(id, (item) => ({
        ...item,
        name: match.filename || item.name,
        tabular: Boolean(match.tabular),
        documentId,
        status: "processing",
        error: undefined,
      }));
    } else {
      const form = new FormData();
      form.append("file", file);
      const response = (await fetchWithAuth("/documents/upload", {
        method: "POST",
        headers: { "Idempotency-Key": record.idempotencyKey },
        body: form,
        signal: controller.signal,
        timeoutMs: 180_000,
      })) as Response;
      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({}));
        throw new Error(
          readApiError(errorPayload, `Upload failed for ${file.name} (HTTP ${response.status}).`),
        );
      }
      const result = (await response.json()) as { document_id?: string };
      if (!result.document_id) throw new Error(`Upload did not return an ID for ${file.name}.`);
      if (controller.signal.aborted) return;

      documentId = result.document_id;
      record.file = null;
      updateUpload(id, (item) => ({
        ...item,
        tabular: isTabularFile(file),
        documentId,
        status: "processing",
        error: undefined,
      }));
    }
  } catch (error) {
    if (!controller.signal.aborted) {
      updateUpload(id, (item) => ({
        ...item,
        status: "failed",
        error: error instanceof Error ? error.message : "Upload failed.",
      }));
    }
  } finally {
    releaseUploadSlot(uploadSlotPool);
    if (!documentId) {
      if (record.controller === controller) {
        record.controller = null;
        record.running = false;
      }
    }
  }

  if (documentId && !controller.signal.aborted) {
    await trackIndexing(id, documentId, controller);
  }
}

export function subscribeQueryUploads(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getQueryUploadsSnapshot(): QueryUploadAttachment[] {
  return snapshot;
}

export function addQueryFiles(files: readonly File[], ownerId: string | null): number {
  if (!ownerId) return 0;
  const staleIds = snapshot
    .filter((item) => item.draftId === QUERY_DRAFT_ID && item.ownerId !== ownerId)
    .map((item) => item.id);
  staleIds.forEach((id) => {
    records.get(id)?.controller?.abort();
    records.delete(id);
  });
  if (staleIds.length) {
    const staleIdSet = new Set(staleIds);
    publish(snapshot.filter((item) => !staleIdSet.has(item.id)));
  }
  const currentCount = snapshot.filter(
    (item) => item.draftId === QUERY_DRAFT_ID && item.ownerId === ownerId,
  ).length;
  const acceptedFiles = files.slice(0, Math.max(0, MAX_QUERY_ATTACHMENTS - currentCount));
  if (!acceptedFiles.length) return 0;

  const additions = acceptedFiles.map((file) => {
    const id = crypto.randomUUID();
    records.set(id, {
      ownerId,
      idempotencyKey: crypto.randomUUID(),
      file,
      controller: null,
      running: false,
    });
    return {
      id,
      draftId: QUERY_DRAFT_ID,
      ownerId,
      name: file.name,
      sizeBytes: file.size,
      tabular: isTabularFile(file),
      status: "queued" as const,
    };
  });
  publish([...snapshot, ...additions]);
  additions.forEach((item) => void uploadFile(item.id));
  return acceptedFiles.length;
}

export function addExistingQueryDocument(
  document: { document_id: string; filename: string; size_bytes?: number; tabular?: boolean },
  ownerId: string | null,
): boolean {
  if (!ownerId || !document.document_id || !document.filename) return false;
  if (
    snapshot.some(
      (item) =>
        item.draftId === QUERY_DRAFT_ID &&
        item.ownerId === ownerId &&
        item.documentId === document.document_id,
    )
  ) {
    return false;
  }
  const currentCount = snapshot.filter(
    (item) => item.draftId === QUERY_DRAFT_ID && item.ownerId === ownerId,
  ).length;
  if (currentCount >= MAX_QUERY_ATTACHMENTS) return false;
  const id = crypto.randomUUID();
  const controller = new AbortController();
  const record: UploadRecord = {
    ownerId,
    idempotencyKey: crypto.randomUUID(),
    file: null,
    controller,
    running: true,
  };
  records.set(id, record);
  publish([
    ...snapshot,
    {
      id,
      draftId: QUERY_DRAFT_ID,
      ownerId,
      name: document.filename,
      sizeBytes: document.size_bytes ?? 0,
      tabular: Boolean(document.tabular),
      status: "processing",
      documentId: document.document_id,
    },
  ]);
  void trackIndexing(id, document.document_id, controller);
  return true;
}

export function removeQueryFile(id: string): void {
  records.get(id)?.controller?.abort();
  records.delete(id);
  publish(snapshot.filter((item) => item.id !== id));
}

export function clearQueryDraftFiles(): void {
  const draftIds = snapshot
    .filter((item) => item.draftId === QUERY_DRAFT_ID)
    .map((item) => item.id);
  draftIds.forEach((id) => {
    records.get(id)?.controller?.abort();
    records.delete(id);
  });
  if (draftIds.length) {
    const removed = new Set(draftIds);
    publish(snapshot.filter((item) => !removed.has(item.id)));
  }
}

export function retryQueryFile(id: string): void {
  const item = snapshot.find((attachment) => attachment.id === id);
  const record = records.get(id);
  if (!item || !record || record.running) return;

  if (item.documentId) {
    const controller = new AbortController();
    record.controller = controller;
    record.running = true;
    updateUpload(id, (current) => ({ ...current, status: "processing", error: undefined }));
    void trackIndexing(id, item.documentId, controller, true);
    return;
  }

  if (record.file) {
    updateUpload(id, (current) => ({ ...current, status: "queued", error: undefined }));
    void uploadFile(id);
  }
}
