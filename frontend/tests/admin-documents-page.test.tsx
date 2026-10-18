import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import AdminDocumentsPage from "../app/dashboard/admin/documents/page";

const fetchWithAuthMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

describe("admin document processing health page", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [{ tenant_id: "tenant-1", quarantined_count: 2, error_count: 1 }],
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) });
  });

  it("shows processing issues without document volume or storage totals", async () => {
    render(<AdminDocumentsPage />);

    expect(await screen.findByText("Workspace Processing Health")).toBeInTheDocument();
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
    expect(
      screen.getByText(/does not expose filenames, document IDs, storage paths/i),
    ).toBeInTheDocument();
    expect(screen.queryByText("Storage")).not.toBeInTheDocument();
    expect(screen.queryByText("Documents")).not.toBeInTheDocument();
  });

  it("does not render raw document identifiers or provider error text", async () => {
    fetchWithAuthMock.mockReset();
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [{ tenant_id: "tenant-1", quarantined_count: 0, error_count: 1 }],
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            job_id: "job-1",
            status: "failed",
            checkpoint_stage: "embedding",
            resume_count: 2,
            last_error_code: "PROVIDER_TIMEOUT",
            document_id: "private-document-id",
            checkpoint_cursor: 55,
            last_error_message: "private provider response details",
          },
        ],
      }),
    });

    render(<AdminDocumentsPage />);

    expect(await screen.findByText("PROVIDER_TIMEOUT")).toBeInTheDocument();
    expect(screen.queryByText("private-document-id")).not.toBeInTheDocument();
    expect(screen.queryByText("private provider response details")).not.toBeInTheDocument();
    expect(screen.queryByText(/55/)).not.toBeInTheDocument();
  });
});
