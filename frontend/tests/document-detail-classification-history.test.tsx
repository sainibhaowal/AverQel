import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
  actionFailure: false,
  rateLimitedComments: false,
  roles: ["user"] as string[],
  processing: false,
  fullTextFailures: 0,
  realtimeEventHandler: vi.fn(),
}));
const toastMocks = vi.hoisted(() => ({ error: vi.fn() }));

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => mocks.fetchWithAuth(...args),
}));

vi.mock("react-hot-toast", () => ({
  default: {
    error: toastMocks.error,
    success: vi.fn(),
  },
}));

vi.mock("@/app/context/AuthContext", () => ({
  useAuth: () => ({ user: { roles: mocks.roles } }),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "document-1" }),
}));

vi.mock("@/lib/realtime", () => ({
  useRealtimeEvents: (handler: (event: { data?: Record<string, unknown> }) => void) => {
    mocks.realtimeEventHandler.mockImplementation(handler);
  },
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

import DocumentDetailPage from "../app/dashboard/documents/[id]/DocumentDetailClient";

const historyPath = "/documents/organization/classification-rules/documents/document-1/history";

function jsonResponse(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => payload,
  } as Response;
}

function responseFor(endpoint: string): Response {
  if (endpoint === "/documents/document-1") {
    return jsonResponse({
      document_id: "document-1",
      filename: "brief.txt",
      content_type: "text/plain",
      size_bytes: 42,
      sha256_hash: "hash",
      storage_bucket: "private",
      storage_object_key: "document-1",
      status: mocks.processing ? "embedding" : "indexed",
      processing_progress: mocks.processing ? 68 : 100,
      extraction_method: "text",
      extraction_coverage_score: 1,
      extraction_ocr_used: false,
      extraction_vision_used: false,
      extraction_warnings: [],
      version: 1,
      parent_document_id: null,
      created_at: "2026-10-24T10:00:00Z",
      updated_at: "2026-10-24T10:00:00Z",
    });
  }

  if (endpoint === "/documents/document-1/status") {
    return jsonResponse({
      document_id: "document-1",
      status: mocks.processing ? "embedding" : "indexed",
      processing_progress: mocks.processing ? 68 : 100,
      active_stage: mocks.processing ? "embedding" : "indexed",
      stage_progress: mocks.processing ? 68 : 100,
      ingestion_job_id: null,
      ingestion_status: mocks.processing ? "embedding" : "completed",
      attempt_count: 1,
      max_attempts: 3,
      last_error_code: null,
      last_error_message: null,
      dead_lettered_at: null,
      extraction_method: "text",
      extraction_coverage_score: 1,
      extraction_ocr_used: false,
      extraction_vision_used: false,
      extraction_warnings: [],
      embedding_provider: null,
      embedding_model: null,
      security_scan_result: "passed",
      security_scan_reason: null,
      security_scanned_at: "2026-10-24T10:00:00Z",
      security_scan_required: true,
      total_chunk_count: 0,
      embedded_chunk_count: 0,
      recovery_available: false,
      recovery_stage: null,
      recovery_reason: null,
      last_checkpoint_at: null,
      remaining_chunk_count: 0,
      resume_count: 0,
    });
  }

  if (endpoint.startsWith("/documents/document-1/chunks")) {
    return jsonResponse({
      document_id: "document-1",
      total_chunks: 0,
      offset: 0,
      limit: 25,
      has_more: false,
      chunks: [],
    });
  }

  if (endpoint === "/documents/document-1/quality") {
    return jsonResponse({
      extraction_method: "text",
      extraction_coverage_score: 1,
      ocr_used: false,
      vision_used: false,
      warnings: [],
      total_chunks: 0,
      low_quality_chunks: 0,
      page_numbers: [],
      missing_page_numbers: [],
    });
  }

  if (endpoint === "/documents/document-1/comments") return jsonResponse([]);
  if (endpoint === historyPath) {
    return jsonResponse({
      document_id: "document-1",
      items: [
        {
          id: "history-1",
          rule_name: "Filename classification",
          source: "upload",
          status: "applied",
          actions: { tag: true },
          error_message: null,
          created_at: "2026-10-24T10:00:00Z",
        },
      ],
    });
  }
  if (endpoint === "/documents/document-1/versions") {
    return jsonResponse({ root_document_id: "document-1", versions: [] });
  }
  if (endpoint === "/documents/document-1/full-text") {
    if (mocks.fullTextFailures > 0) {
      mocks.fullTextFailures -= 1;
      return {
        ok: false,
        status: 500,
        json: async () => ({ detail: "Temporary failure" }),
      } as Response;
    }
    return jsonResponse({ content: "Document body" });
  }

  return jsonResponse({});
}

describe("document classification history permissions", () => {
  beforeEach(() => {
    mocks.roles = ["user"];
    mocks.processing = false;
    mocks.fullTextFailures = 0;
    mocks.actionFailure = false;
    mocks.rateLimitedComments = false;
    toastMocks.error.mockReset();
    mocks.fetchWithAuth.mockReset();
    mocks.realtimeEventHandler.mockReset();
    mocks.fetchWithAuth.mockImplementation(async (endpoint: string) => {
      if (mocks.rateLimitedComments && endpoint === "/documents/document-1/comments") {
        return new Response(JSON.stringify({ detail: "Too many requests" }), {
          status: 429,
          headers: { "Content-Type": "application/json", "Retry-After": "3" },
        });
      }
      if (mocks.actionFailure && endpoint === "/documents/document-1/actions") {
        return new Response(JSON.stringify({ error: { message: "Internal server error" } }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        });
      }
      return responseFor(endpoint);
    });
  });

  afterEach(() => cleanup());

  it("does not request or display classification history for a basic user", async () => {
    render(<DocumentDetailPage />);

    expect(await screen.findByText("Document body")).toBeInTheDocument();
    expect(mocks.fetchWithAuth).not.toHaveBeenCalledWith(historyPath, expect.anything());
    expect(screen.queryByRole("heading", { name: "Classification history" })).toBeNull();
  });

  it("loads and displays history for an editor while retaining the API route", async () => {
    mocks.roles = ["editor"];

    render(<DocumentDetailPage />);

    expect(await screen.findByText("Filename classification")).toBeInTheDocument();
    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(historyPath, expect.anything()),
    );
    expect(screen.getByRole("heading", { name: "Classification history" })).toBeInTheDocument();
  });

  it("refreshes only document status for realtime progress events", async () => {
    mocks.processing = true;

    render(<DocumentDetailPage />);

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/documents/document-1/status",
        expect.anything(),
      ),
    );
    expect(mocks.fetchWithAuth).not.toHaveBeenCalledWith(
      "/documents/document-1/full-text",
      expect.anything(),
    );
    mocks.fetchWithAuth.mockClear();

    mocks.realtimeEventHandler({ data: { document_id: "document-1" } });

    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/documents/document-1/status",
        expect.anything(),
      ),
    );
    expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(1);
  });

  it("shows one inline error and retries full text after a temporary failure", async () => {
    mocks.fullTextFailures = 1;

    render(<DocumentDetailPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Extracted text could not be loaded.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry text loading" }));

    expect(await screen.findByText("Document body")).toBeInTheDocument();
    expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
      "/documents/document-1/full-text",
      expect.objectContaining({ suppressErrorToast: true }),
    );
  });

  it("shows the API action error once without replacing it with a generic message", async () => {
    mocks.actionFailure = true;

    render(<DocumentDetailPage />);

    expect(await screen.findByText("Document body")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Run grounded action" }));

    await waitFor(() => expect(toastMocks.error).toHaveBeenCalledTimes(1));
    expect(toastMocks.error).toHaveBeenCalledWith("Internal server error");
    expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
      "/documents/document-1/actions",
      expect.objectContaining({ suppressErrorToast: true }),
    );
  });

  it("honors the server retry window instead of refetching rate-limited document details", async () => {
    mocks.rateLimitedComments = true;

    render(<DocumentDetailPage />);

    const detailNotice = await screen.findByRole("status");
    const retryButton = detailNotice.querySelector("button");
    expect(retryButton).toBeDisabled();
    fireEvent.click(retryButton as HTMLButtonElement);

    expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(6);
    expect(retryButton).toHaveTextContent(/Retry in \d+s/);
  });
});
