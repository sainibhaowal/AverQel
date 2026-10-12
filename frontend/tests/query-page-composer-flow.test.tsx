import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
  pendingReleases: [] as Array<() => void>,
  streamBodies: [] as Array<Record<string, unknown>>,
  failNextStream: false,
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => mocks.fetchWithAuth(...args),
}));

vi.mock("@/app/context/AuthContext", () => ({
  useAuth: () => ({ user: { id: "user-1", tenant_id: "tenant-1" } }),
}));

vi.mock("@/lib/providers-api", () => ({
  listProviders: vi.fn(async () => []),
  listProviderModels: vi.fn(async () => []),
  listAssignments: vi.fn(async () => []),
  createAssignment: vi.fn(),
  updateAssignment: vi.fn(),
}));

vi.mock("../app/dashboard/query/_hooks/useQueryStream", () => ({
  useQueryStream: (options: {
    onEvent: (event: Record<string, unknown>) => void;
    onFinally?: () => void;
  }) => ({
    start: (args: { body: Record<string, unknown> }) => {
      mocks.streamBodies.push(args.body);
      const conversationId = mocks.streamBodies.length === 1 ? "conversation-1" : "conversation-1";
      options.onEvent({
        event: "start",
        data: {
          message_id: `message-${mocks.streamBodies.length}`,
          conversation_id: conversationId,
          started_at: new Date().toISOString(),
        },
      });
      if (mocks.failNextStream) {
        mocks.failNextStream = false;
        options.onEvent({
          event: "error",
          data: { code: "PROVIDER_ERROR", message: "The provider rejected this query." },
        });
      }
      return new Promise<void>((resolve) => {
        mocks.pendingReleases.push(() => {
          options.onFinally?.();
          resolve();
        });
      });
    },
    cancel: vi.fn(),
  }),
}));

vi.mock("../app/dashboard/query/_components/QueryComposer", () => ({
  MAX_QUERY_ATTACHMENTS: 10,
  MAX_QUERY_QUEUE_ITEMS: 20,
  default: (props: {
    query: string;
    onQueryChange: (value: string) => void;
    onSubmit: (
      attachments: Array<{ id: string; documentId?: string; name: string; status: string }>,
    ) => void;
    isStreaming: boolean;
    requestPending?: boolean;
    attachments?: Array<{ id: string; documentId?: string; name: string; status: string }>;
    onFilesSelected?: (files: FileList | null) => void;
    queueItems?: Array<{ id: string; query: string; status?: "queued" | "failed" }>;
    queuePaused?: boolean;
    onRetryQueueItem?: (id: string) => void;
  }) => (
    <div>
      <input
        aria-label="Query draft"
        value={props.query}
        onChange={(event) => props.onQueryChange(event.target.value)}
      />
      <input
        aria-label="Choose documents to attach"
        type="file"
        onChange={(event) => props.onFilesSelected?.(event.currentTarget.files)}
      />
      {(props.attachments ?? []).map((attachment) => (
        <span key={attachment.id}>
          {attachment.status === "ready" ? "Ready" : attachment.status}
        </span>
      ))}
      <button type="button" onClick={() => props.onSubmit(props.attachments ?? [])}>
        {props.isStreaming || props.requestPending ? "Queue query" : "Send query"}
      </button>
      {(props.queueItems ?? []).map((item) => (
        <p key={item.id}>
          {item.query}
          {item.status === "failed" ? (
            <button type="button" onClick={() => props.onRetryQueueItem?.(item.id)}>
              Retry failed query
            </button>
          ) : null}
        </p>
      ))}
      {props.queuePaused ? <span>Queue paused</span> : null}
    </div>
  ),
}));

vi.mock("../app/dashboard/query/_components/MessageThread", () => ({ default: () => null }));
vi.mock("@/app/components/dashboard/ChatSidebar", () => ({ default: () => null }));
vi.mock("@/app/components/query/PDFPreviewModal", () => ({ default: () => null }));
vi.mock("@/app/components/ui/ConfirmationModal", () => ({ default: () => null }));

import QueryPageClient from "../app/dashboard/query/_components/QueryPageClient";
import { clearQueryDraftFiles } from "../app/dashboard/query/_lib/query-uploads";

function response(payload: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

describe("Grounded Query composer flow", () => {
  afterEach(() => {
    act(() => clearQueryDraftFiles());
  });

  beforeEach(() => {
    mocks.fetchWithAuth.mockReset();
    mocks.streamBodies.length = 0;
    mocks.pendingReleases.length = 0;
    mocks.failNextStream = false;
    localStorage.setItem("averqel_user", JSON.stringify({ id: "user-1", tenant_id: "tenant-1" }));
    mocks.fetchWithAuth.mockImplementation(async (url: string) => {
      if (url === "/queries/capabilities/chat") return response({ supports_thinking: false });
      if (url === "/collections") return response([]);
      if (url === "/documents/upload") return response({ document_id: "document-attached-1" });
      if (url === "/documents/document-attached-1/status") {
        return response({
          status: "indexed",
          ingestion_status: "indexed",
          quarantined: false,
          total_chunk_count: 4,
        });
      }
      if (url === "/chats/conversation-1/messages") return response({ messages: [] });
      return response({});
    });
  });

  it("uploads through Documents Hub, waits for indexing, and queues prompts on the existing stream", async () => {
    render(<QueryPageClient />);

    const file = new File(["private source"], "source.txt", { type: "text/plain" });
    fireEvent.change(screen.getByLabelText("Choose documents to attach"), {
      target: { files: [file] },
    });
    await waitFor(() => expect(screen.getByText("Ready")).toBeInTheDocument());

    const uploadCall = mocks.fetchWithAuth.mock.calls.find(([url]) => url === "/documents/upload");
    expect(uploadCall?.[1]).toMatchObject({ method: "POST" });
    expect((uploadCall?.[1] as RequestInit).headers).toHaveProperty("Idempotency-Key");
    expect(
      mocks.fetchWithAuth.mock.calls.some(
        ([url]) => url === "/documents/document-attached-1/status",
      ),
    ).toBe(true);

    fireEvent.change(screen.getByRole("textbox", { name: "Query draft" }), {
      target: { value: "Summarize this uploaded file" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send query" }));

    await waitFor(() => expect(mocks.streamBodies).toHaveLength(1));
    expect(mocks.streamBodies[0]).toMatchObject({
      query: "Summarize this uploaded file",
      filters: { attached_document_ids: ["document-attached-1"] },
    });

    fireEvent.change(screen.getByRole("textbox", { name: "Query draft" }), {
      target: { value: "Compare it with the earlier guidance" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue query" }));
    expect(await screen.findByText("Compare it with the earlier guidance")).toBeInTheDocument();
    expect(mocks.streamBodies).toHaveLength(1);

    await act(async () => {
      mocks.pendingReleases.shift()?.();
    });
    await waitFor(() => expect(mocks.streamBodies).toHaveLength(2));
    expect(mocks.streamBodies[1]).toMatchObject({
      query: "Compare it with the earlier guidance",
      conversation_id: "conversation-1",
    });

    await act(async () => {
      mocks.pendingReleases.shift()?.();
    });
  });

  it("reuses an accessible Documents Hub table without uploading a duplicate", async () => {
    mocks.fetchWithAuth.mockImplementation(async (url: string) => {
      if (url === "/queries/capabilities/chat") return response({ supports_thinking: false });
      if (url === "/collections") return response([]);
      if (url === "/queries/attachments/resolve") {
        return response({
          found: true,
          document_id: "existing-sales-table",
          filename: "sales.csv",
          tabular: true,
        });
      }
      if (url === "/documents/existing-sales-table/status") {
        return response({
          status: "indexed",
          ingestion_status: "indexed",
          quarantined: false,
          total_chunk_count: 0,
        });
      }
      if (url === "/queries/datasets/existing-sales-table/prepare") {
        return response({ status: "ready", progress: 100, row_count: 100_000 });
      }
      if (url === "/chats/conversation-1/messages") return response({ messages: [] });
      return response({});
    });

    render(<QueryPageClient />);
    fireEvent.change(screen.getByLabelText("Choose documents to attach"), {
      target: { files: [new File(["id,total\n1,10\n"], "sales.csv", { type: "text/csv" })] },
    });
    await waitFor(() => expect(screen.getByText("Ready")).toBeInTheDocument());

    expect(mocks.fetchWithAuth.mock.calls.some(([url]) => url === "/documents/upload")).toBe(false);
    expect(
      mocks.fetchWithAuth.mock.calls.some(
        ([url]) => url === "/queries/datasets/existing-sales-table/prepare",
      ),
    ).toBe(true);

    fireEvent.change(screen.getByRole("textbox", { name: "Query draft" }), {
      target: { value: "Count the sales rows" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send query" }));
    await waitFor(() => expect(mocks.streamBodies).toHaveLength(1));
    expect(mocks.streamBodies[0]).toMatchObject({
      filters: { attached_document_ids: ["existing-sales-table"] },
    });
  });

  it("recognizes a table from its MIME type and waits for the table index", async () => {
    mocks.fetchWithAuth.mockImplementation(async (url: string) => {
      if (url === "/queries/capabilities/chat") return response({ supports_thinking: false });
      if (url === "/collections") return response([]);
      if (url === "/queries/attachments/resolve") return response({ found: false });
      if (url === "/documents/upload") return response({ document_id: "document-attached-1" });
      if (url === "/documents/document-attached-1/status") {
        return response({ status: "indexed", ingestion_status: "indexed", total_chunk_count: 4 });
      }
      if (url === "/queries/datasets/document-attached-1/prepare") {
        return response({ status: "ready", progress: 100, row_count: 3 });
      }
      if (url === "/chats/conversation-1/messages") return response({ messages: [] });
      return response({});
    });

    render(<QueryPageClient />);
    fireEvent.change(screen.getByLabelText("Choose documents to attach"), {
      target: { files: [new File(["id,total\n1,10\n"], "sales-data", { type: "text/csv" })] },
    });
    await waitFor(() => expect(screen.getByText("Ready")).toBeInTheDocument());
    expect(
      mocks.fetchWithAuth.mock.calls.some(
        ([url]) => url === "/queries/datasets/document-attached-1/prepare",
      ),
    ).toBe(true);
  });

  it("keeps an upload alive when the Query page unmounts during in-app navigation", async () => {
    let finishUpload: ((value: ReturnType<typeof response>) => void) | null = null;
    mocks.fetchWithAuth.mockImplementation(async (url: string) => {
      if (url === "/documents/upload") {
        return new Promise((resolve) => {
          finishUpload = resolve;
        });
      }
      if (url === "/documents/uploaded-after-navigation/status") {
        return response({
          status: "indexed",
          ingestion_status: "indexed",
          quarantined: false,
          total_chunk_count: 1,
        });
      }
      if (url === "/queries/capabilities/chat") return response({ supports_thinking: false });
      if (url === "/collections") return response([]);
      return response({});
    });

    const firstPage = render(<QueryPageClient />);
    fireEvent.change(screen.getByLabelText("Choose documents to attach"), {
      target: { files: [new File(["source"], "live-upload.txt", { type: "text/plain" })] },
    });
    await waitFor(() =>
      expect(mocks.fetchWithAuth).toHaveBeenCalledWith(
        "/documents/upload",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const uploadOptions = mocks.fetchWithAuth.mock.calls.find(
      ([url]) => url === "/documents/upload",
    )?.[1] as RequestInit;
    const signal = uploadOptions.signal as AbortSignal;
    expect(signal.aborted).toBe(false);

    firstPage.unmount();
    render(<QueryPageClient />);
    expect(screen.getByText("uploading")).toBeInTheDocument();
    expect(signal.aborted).toBe(false);

    await act(async () => {
      finishUpload?.(response({ document_id: "uploaded-after-navigation" }));
    });
    await waitFor(() => expect(screen.getByText("Ready")).toBeInTheDocument());
    act(() => clearQueryDraftFiles());
  });

  it("pauses after a stream failure and retries that prompt before later queued prompts", async () => {
    render(<QueryPageClient />);
    mocks.failNextStream = true;

    fireEvent.change(screen.getByRole("textbox", { name: "Query draft" }), {
      target: { value: "First prompt fails" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send query" }));
    await waitFor(() => expect(mocks.streamBodies).toHaveLength(1));

    fireEvent.change(screen.getByRole("textbox", { name: "Query draft" }), {
      target: { value: "Second prompt waits" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Queue query" }));
    expect(await screen.findByText("Second prompt waits")).toBeInTheDocument();

    await act(async () => {
      mocks.pendingReleases.shift()?.();
    });
    expect(await screen.findByText("Queue paused")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry failed query" }));

    await waitFor(() => expect(mocks.streamBodies).toHaveLength(2));
    expect(mocks.streamBodies[1]).toMatchObject({ query: "First prompt fails" });
    await act(async () => {
      mocks.pendingReleases.shift()?.();
    });

    await waitFor(() => expect(mocks.streamBodies).toHaveLength(3));
    expect(mocks.streamBodies[2]).toMatchObject({ query: "Second prompt waits" });
    await act(async () => {
      mocks.pendingReleases.shift()?.();
    });
  });
});
