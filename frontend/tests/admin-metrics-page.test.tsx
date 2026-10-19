import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchWithAuth } from "@/lib/api";
import MetricsPage from "../app/dashboard/admin/metrics/page";

vi.mock("@/lib/api", () => ({ fetchWithAuth: vi.fn() }));

const mockedFetchWithAuth = vi.mocked(fetchWithAuth);

function makeSummary(apiRequests: number): Record<string, unknown> {
  return {
    api_requests_total: apiRequests,
    api_errors_total: 2,
    db_query_count: 228,
    worker_retries_total: 3,
    worker_dead_letters_total: 4,
    deepspace_cache_reads_total: 5,
    deepspace_cache_writes_total: 6,
    deepspace_context_compactions_total: 7,
    deepspace_overflow_prevented_total: 8,
    deepspace_mcp_result_references_total: 9,
    deepspace_budget_allocations_total: 10,
    deepspace_result_reference_events_total: 11,
    deepspace_execution_batches_total: 12,
    deepspace_canary_mismatches_total: 13,
    metrics_scope: "service-wide",
    metrics_complete: true,
    metrics_started_at: "2026-10-18T00:00:00+00:00",
    snapshot_at: "2026-10-18T00:00:01+00:00",
  };
}

describe("admin metrics dashboard live stream", () => {
  beforeEach(() => {
    mockedFetchWithAuth.mockReset();
  });

  it("renders an incoming service-wide SSE snapshot update", async () => {
    const encoder = new TextEncoder();
    let streamController: ReadableStreamDefaultController<Uint8Array> | null = null;
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        streamController = controller;
        controller.enqueue(
          encoder.encode(`event: metrics\ndata: ${JSON.stringify(makeSummary(845))}\n\n`),
        );
      },
    });

    mockedFetchWithAuth.mockImplementation(((path: string) => {
      if (path === "/capabilities") {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              supported_formats: [],
              ocr_enabled: false,
              vision_enabled: false,
              limits: { max_pdf_pages: 10, max_text_chars: 1_000 },
            }),
            { status: 200 },
          ),
        );
      }
      if (path === "/metrics/summary/stream") {
        return Promise.resolve(new Response(body, { status: 200 }));
      }
      throw new Error(`Unexpected metrics request: ${path}`);
    }) as typeof fetchWithAuth);

    const { unmount } = render(<MetricsPage />);
    expect(await screen.findByText("845")).toBeInTheDocument();

    await act(async () => {
      streamController?.enqueue(
        encoder.encode(`event: metrics\ndata: ${JSON.stringify(makeSummary(846))}\n\n`),
      );
    });

    expect(await screen.findByText("846")).toBeInTheDocument();
    unmount();
    await act(async () => {
      streamController?.close();
    });
  });
});
