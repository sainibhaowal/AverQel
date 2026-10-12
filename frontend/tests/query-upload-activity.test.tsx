import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchWithAuthMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

import QueryUploadActivity from "../app/dashboard/documents/_components/QueryUploadActivity";
import { addQueryFiles, clearQueryDraftFiles } from "../app/dashboard/query/_lib/query-uploads";

const uploadOwnerId = "tenant-1:user-1";

function response(payload: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => payload };
}

describe("Documents Hub Query upload activity", () => {
  afterEach(() => {
    act(() => clearQueryDraftFiles());
  });

  beforeEach(() => {
    act(() => clearQueryDraftFiles());
    Object.defineProperty(window, "scrollTo", { writable: true, value: vi.fn() });
    localStorage.setItem("averqel_user", JSON.stringify({ id: "user-1", tenant_id: "tenant-1" }));
    fetchWithAuthMock.mockReset();
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/documents/upload") return response({ document_id: "document-live" });
      if (url === "/documents/document-live/status") {
        return response({ status: "processing", ingestion_status: "embedding" });
      }
      return response({});
    });
  });

  it("shows an upload live, then removes its temporary row when the saved document appears", async () => {
    const view = render(
      <QueryUploadActivity
        ownerId={uploadOwnerId}
        documentIds={new Set()}
        formatBytes={() => "6 Bytes"}
      />,
    );

    act(() => {
      addQueryFiles(
        [new File(["source"], "live-source.txt", { type: "text/plain" })],
        uploadOwnerId,
      );
    });

    expect(await screen.findByText("live-source.txt")).toBeInTheDocument();
    expect(await screen.findByText(/Indexing in Documents Hub/)).toBeInTheDocument();
    expect(screen.getByText("6 Bytes", { exact: false })).toBeInTheDocument();

    view.rerender(
      <QueryUploadActivity
        ownerId={uploadOwnerId}
        documentIds={new Set(["document-live"])}
        formatBytes={() => "6 Bytes"}
      />,
    );
    await waitFor(() => expect(screen.queryByText("live-source.txt")).not.toBeInTheDocument());
  });

  it("shows upload failures only to the matching tenant and account", async () => {
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      if (url === "/documents/upload") return response({}, 413);
      return response({});
    });
    const view = render(
      <QueryUploadActivity
        ownerId={uploadOwnerId}
        documentIds={new Set()}
        formatBytes={() => "1 Byte"}
      />,
    );

    act(() => {
      addQueryFiles([new File(["x"], "rejected.txt", { type: "text/plain" })], uploadOwnerId);
    });
    expect(
      await screen.findByText("Upload failed for rejected.txt (HTTP 413)."),
    ).toBeInTheDocument();
    expect(screen.getByText(/Upload or indexing failed/)).toBeInTheDocument();

    view.rerender(
      <QueryUploadActivity
        ownerId="tenant-2:user-2"
        documentIds={new Set()}
        formatBytes={() => "1 Byte"}
      />,
    );
    await waitFor(() => expect(screen.queryByText("rejected.txt")).not.toBeInTheDocument());
  });
});
