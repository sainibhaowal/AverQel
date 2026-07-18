import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import AuditLogsPage from "../app/dashboard/admin/audit-logs/page";

const fetchWithAuthMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

describe("audit logs page", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it("renders lowercase success status as a success badge", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            id: "log-1",
            action: "documents.upload",
            actor_user_id: "user-1",
            resource_type: "document",
            resource_id: "doc-1",
            status: "success",
            trace_id: "trace-1",
            created_at: "2026-03-31T00:00:00Z",
            details: {},
          },
        ],
        page: {
          next_cursor: null,
          has_more: false,
        },
      }),
    });

    render(<AuditLogsPage />);

    const badge = await screen.findByText("success");
    expect(badge.className).toContain("text-green-500");
  });

  it("loads the next page through the existing cursor API", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            id: "log-1",
            action: "documents.upload",
            actor_user_id: "user-1",
            resource_type: "document",
            resource_id: "doc-1",
            status: "SUCCESS",
            trace_id: "trace-1",
            created_at: "2026-03-31T00:00:00Z",
            details: {},
          },
        ],
        page: {
          next_cursor: "cursor-2",
          has_more: true,
        },
      }),
    });

    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            id: "log-2",
            action: "admin.audit_logs.read",
            actor_user_id: "user-2",
            resource_type: "admin",
            resource_id: null,
            status: "failed",
            trace_id: "trace-2",
            created_at: "2026-03-31T00:01:00Z",
            details: {},
          },
        ],
        page: {
          next_cursor: null,
          has_more: false,
        },
      }),
    });

    render(<AuditLogsPage />);

    await screen.findByText("documents.upload");
    fireEvent.click(screen.getByRole("button", { name: /load more records/i }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenNthCalledWith(
        2,
        "/admin/audit-logs?limit=50&cursor=cursor-2",
      );
    });

    expect(await screen.findByText("admin.audit_logs.read")).toBeInTheDocument();
  });
});
