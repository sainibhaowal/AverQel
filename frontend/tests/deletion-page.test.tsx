import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import DeletionPage from "../app/dashboard/admin/deletion/page";

const fetchWithAuthMock = vi.fn();
const toastSuccessMock = vi.fn();
const toastErrorMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.mock("../app/context/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: "user-1",
      tenant_id: "tenant-1",
      roles: ["admin"],
    },
  }),
}));

vi.mock("react-hot-toast", () => ({
  default: {
    success: (...args: unknown[]) => toastSuccessMock(...args),
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}));

describe("deletion admin page", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    toastSuccessMock.mockReset();
    toastErrorMock.mockReset();
  });

  it("loads deletion history through the shared authenticated API client", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            tenant_id: "tenant-1",
            name: "Workspace One",
            created_at: "2026-03-31T00:00:00Z",
            updated_at: "2026-03-31T00:00:00Z",
            stats: {
              users_count: 3,
              active_users_count: 2,
              documents_count: 2,
              queries_count: 4,
              collections_count: 1,
            },
          },
        ],
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            deletion_id: "del-1",
            tenant_id: "tenant-1",
            requested_by_user_id: "user-1",
            status: "completed",
            scope: "tenant_data",
            reason: "tenant cleanup",
            result_counts: { documents: 2 },
            error_code: null,
            error_message: null,
            requested_at: "2026-03-31T00:00:00Z",
            started_at: "2026-03-31T00:01:00Z",
            completed_at: "2026-03-31T00:02:00Z",
            failed_at: null,
          },
        ],
      }),
    });

    render(<DeletionPage />);

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/admin/tenants");
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        "/admin/data-deletions?limit=20&target_tenant_id=tenant-1",
      );
    });

    expect(await screen.findByText("del-1")).toBeInTheDocument();
    expect(screen.getByText(/status: completed/i)).toBeInTheDocument();
  });

  it("refreshes deletion history after creating a deletion request", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            tenant_id: "tenant-1",
            name: "Workspace One",
            created_at: "2026-03-31T00:00:00Z",
            updated_at: "2026-03-31T00:00:00Z",
            stats: {
              users_count: 3,
              active_users_count: 2,
              documents_count: 2,
              queries_count: 4,
              collections_count: 1,
            },
          },
        ],
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ items: [] }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        deletion_id: "del-2",
        status: "queued",
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            deletion_id: "del-2",
            tenant_id: "tenant-1",
            requested_by_user_id: "user-1",
            status: "queued",
            scope: "tenant_data",
            reason: "offboarding",
            result_counts: {},
            error_code: null,
            error_message: null,
            requested_at: "2026-03-31T00:00:00Z",
            started_at: null,
            completed_at: null,
            failed_at: null,
          },
        ],
      }),
    });

    render(<DeletionPage />);

    fireEvent.click(await screen.findByRole("button", { name: /execute workspace wipe/i }));
    fireEvent.change(screen.getByPlaceholderText(/legal request, tenant offboarding/i), {
      target: { value: "offboarding" },
    });
    fireEvent.click(screen.getByRole("button", { name: /wipe data/i }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/admin/data-deletions", {
        method: "POST",
        body: JSON.stringify({ reason: "offboarding", target_tenant_id: "tenant-1" }),
      });
    });

    await waitFor(() => {
      expect(screen.getByText("del-2")).toBeInTheDocument();
    });

    expect(toastSuccessMock).toHaveBeenCalled();
  });
});
