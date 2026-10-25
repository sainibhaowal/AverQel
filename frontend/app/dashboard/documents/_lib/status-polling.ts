export interface DocumentStatusPollingState {
  status: string;
  ingestion_status?: string | null;
  recovery_available?: boolean;
}

export const DOCUMENT_STATUS_ACTIVE_POLL_MS = 10_000;
export const DOCUMENT_STATUS_RECOVERY_POLL_MS = 30_000;
export const DOCUMENT_REALTIME_STATUS_MIN_INTERVAL_MS = 5_000;
const DOCUMENT_REALTIME_STATUS_DEBOUNCE_MS = 500;
const DOCUMENT_STATUS_MAX_RETRY_MS = 60_000;
const SERVER_RETRY_MAX_MS = 5 * 60_000;
const TERMINAL_STATUSES = new Set(["indexed", "completed", "failed", "dead_lettered"]);
const STOPPED_INGESTION_STATUSES = new Set(["failed", "dead_lettered", "completed", "indexed"]);

export function isTerminalDocumentStatus(status: string | null | undefined): boolean {
  return TERMINAL_STATUSES.has(status ?? "");
}

export function getRealtimeStatusRefreshDelay(nowMs: number, lastRefreshAtMs: number): number {
  return Math.max(
    DOCUMENT_REALTIME_STATUS_DEBOUNCE_MS,
    DOCUMENT_REALTIME_STATUS_MIN_INTERVAL_MS - (nowMs - lastRefreshAtMs),
  );
}

export function getDocumentStatusPollingInterval(
  status: DocumentStatusPollingState | null | undefined,
): number | null {
  if (!status) return DOCUMENT_STATUS_ACTIVE_POLL_MS;

  if (status.recovery_available && STOPPED_INGESTION_STATUSES.has(status.ingestion_status ?? "")) {
    return null;
  }

  if (isTerminalDocumentStatus(status.status) && !status.recovery_available) return null;
  if (status.recovery_available) return DOCUMENT_STATUS_RECOVERY_POLL_MS;
  return DOCUMENT_STATUS_ACTIVE_POLL_MS;
}

function parseRetryAfterMs(response: Response): number | null {
  const resetAt = Number(response.headers.get("X-RateLimit-Reset"));
  if (Number.isFinite(resetAt) && resetAt > 0) {
    const remaining = resetAt * 1000 - Date.now();
    if (remaining > 0) return Math.min(remaining, SERVER_RETRY_MAX_MS);
  }

  const retryAfter = response.headers.get("Retry-After");
  if (!retryAfter) return null;

  const retrySeconds = Number(retryAfter);
  if (Number.isFinite(retrySeconds) && retrySeconds > 0) {
    return Math.min(retrySeconds * 1000, SERVER_RETRY_MAX_MS);
  }

  const retryAt = Date.parse(retryAfter);
  if (Number.isFinite(retryAt) && retryAt > Date.now()) {
    return Math.min(retryAt - Date.now(), SERVER_RETRY_MAX_MS);
  }

  return null;
}

export function getDocumentStatusRetryDelay(
  response: Response | null,
  previousDelayMs: number,
): number {
  const serverDelay = response ? parseRetryAfterMs(response) : null;
  if (serverDelay !== null) return serverDelay;

  return Math.min(
    Math.max(previousDelayMs * 2, DOCUMENT_STATUS_ACTIVE_POLL_MS),
    DOCUMENT_STATUS_MAX_RETRY_MS,
  );
}
