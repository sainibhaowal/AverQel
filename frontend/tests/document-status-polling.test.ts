import { describe, expect, it } from "vitest";

import {
  DOCUMENT_STATUS_ACTIVE_POLL_MS,
  DOCUMENT_STATUS_RECOVERY_POLL_MS,
  getRealtimeStatusRefreshDelay,
  getDocumentStatusPollingInterval,
  getDocumentStatusRetryDelay,
} from "../app/dashboard/documents/_lib/status-polling";

describe("document status polling", () => {
  it("uses slower polling when checkpoint recovery is available but ingestion is active", () => {
    expect(
      getDocumentStatusPollingInterval({
        status: "embedding",
        ingestion_status: "embedding",
        recovery_available: true,
      }),
    ).toBe(DOCUMENT_STATUS_RECOVERY_POLL_MS);
  });

  it("stops polling when a failed checkpoint is waiting for the user to resume it", () => {
    expect(
      getDocumentStatusPollingInterval({
        status: "failed",
        ingestion_status: "failed",
        recovery_available: true,
      }),
    ).toBeNull();
  });

  it("stops polling completed documents and polls active documents at the normal rate", () => {
    expect(
      getDocumentStatusPollingInterval({
        status: "indexed",
        ingestion_status: "completed",
        recovery_available: false,
      }),
    ).toBeNull();
    expect(
      getDocumentStatusPollingInterval({
        status: "embedding",
        ingestion_status: "embedding",
        recovery_available: false,
      }),
    ).toBe(DOCUMENT_STATUS_ACTIVE_POLL_MS);
  });

  it("honors server rate-limit reset time and backs off other failures", () => {
    const resetAt = Math.ceil((Date.now() + 120_000) / 1000);
    const rateLimited = new Response(null, {
      status: 429,
      headers: { "X-RateLimit-Reset": String(resetAt) },
    });
    const unavailable = new Response(null, { status: 503 });

    expect(
      getDocumentStatusRetryDelay(rateLimited, DOCUMENT_STATUS_ACTIVE_POLL_MS),
    ).toBeGreaterThan(110_000);
    expect(getDocumentStatusRetryDelay(unavailable, DOCUMENT_STATUS_ACTIVE_POLL_MS)).toBe(20_000);
  });

  it("debounces realtime refreshes and caps progress-event refresh frequency", () => {
    expect(getRealtimeStatusRefreshDelay(100_000, 0)).toBe(500);
    expect(getRealtimeStatusRefreshDelay(103_000, 100_000)).toBe(2_000);
    expect(getRealtimeStatusRefreshDelay(106_000, 100_000)).toBe(500);
  });
});
