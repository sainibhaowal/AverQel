/**
 * Typed Document API Helpers
 * Centralizes all /documents/* API calls for the Document Intelligence Hub.
 */
import { fetchWithAuth } from "@/lib/api";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
export interface DocumentListItem {
  document_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: string;
  processing_progress: number;
  quarantined: boolean;
  information_yield: number | null;
  created_at: string;
  extraction_method?: string | null;
  extraction_coverage_score?: number | null;
  extraction_ocr_used?: boolean;
  extraction_vision_used?: boolean;
  extraction_warnings?: string[];
}

export interface DocumentStatusResult {
  document_id: string;
  status: string;
  processing_progress: number;
  active_stage: string;
  stage_progress: number;
  quarantined: boolean;
  information_yield: number | null;
  ingestion_job_id: string | null;
  ingestion_status: string | null;
  attempt_count: number | null;
  max_attempts: number | null;
  last_error_code: string | null;
  last_error_message: string | null;
  dead_lettered_at: string | null;
  extraction_method: string | null;
  extraction_coverage_score: number | null;
  extraction_ocr_used: boolean;
  extraction_vision_used: boolean;
  extraction_warnings: string[];
  embedding_provider: string | null;
  embedding_model: string | null;
  embedded_chunk_count: number;
}

export interface DeleteBatchResult {
  deleted: number;
  failed: string[];
}

export async function readApiErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.clone().json();
    return payload?.error?.message || payload?.detail || fallback;
  } catch {
    return fallback;
  }
}

// ---------------------------------------------------------------------------
// API Calls
// ---------------------------------------------------------------------------

export async function listDocuments(): Promise<DocumentListItem[]> {
  const res = (await fetchWithAuth("/documents")) as Response;
  if (!res.ok) throw new Error(`Failed to fetch documents: ${res.status}`);
  const data = await res.json();
  return data.items;
}

export async function getDocumentStatus(id: string): Promise<DocumentStatusResult> {
  const res = (await fetchWithAuth(`/documents/${id}/status`)) as Response;
  if (!res.ok) throw new Error(`Failed to fetch document status: ${res.status}`);
  return res.json();
}

export async function deleteDocument(id: string): Promise<boolean> {
  const res = (await fetchWithAuth(`/documents/${id}`, { method: "DELETE" })) as Response;
  if (!res.ok) {
    throw new Error(await readApiErrorMessage(res, "Failed to delete document."));
  }
  return res.ok;
}

export async function batchDeleteDocuments(ids: string[]): Promise<DeleteBatchResult> {
  const res = (await fetchWithAuth("/documents/batch/delete", {
    method: "POST",
    body: JSON.stringify({ document_ids: ids }),
  })) as Response;
  if (!res.ok) throw new Error(`Batch delete failed: ${res.status}`);
  return res.json();
}
