import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, vi } from "vitest";

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
  afterEach(() => {
    vi.unstubAllGlobals();
  });

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
            seats_used: 3,
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
            status: "completed",
            scope: "tenant_data",
            reason: "workspace_offboarding",
            can_approve: false,
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
    expect(screen.getByRole("link", { name: "support" })).toHaveAttribute(
      "href",
      "/dashboard/support",
    );
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
            seats_used: 3,
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
        status: "awaiting_approval",
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            deletion_id: "del-2",
            tenant_id: "tenant-1",
            status: "awaiting_approval",
            scope: "tenant_data",
            reason: "workspace_offboarding",
            can_approve: false,
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
    fireEvent.change(screen.getByLabelText(/type delete tenant-1/i), {
      target: { value: "DELETE tenant-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: /wipe data/i }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/admin/data-deletions", {
        method: "POST",
        body: JSON.stringify({
          reason: "workspace_offboarding",
          target_confirmation: "DELETE tenant-1",
          target_tenant_id: "tenant-1",
        }),
      });
    });

    await waitFor(() => {
      expect(screen.getByText("del-2")).toBeInTheDocument();
    });

    expect(toastSuccessMock).toHaveBeenCalledWith(
      "Deletion request is waiting for a second administrator: del-2",
    );
  });

  it("lets a different administrator approve a pending workspace purge", async () => {
    vi.stubGlobal(
      "confirm",
      vi.fn(() => true),
    );
    fetchWithAuthMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              tenant_id: "tenant-1",
              name: "Workspace One",
              created_at: "2026-03-31T00:00:00Z",
              updated_at: "2026-03-31T00:00:00Z",
              seats_used: 3,
            },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            {
              deletion_id: "del-3",
              tenant_id: "tenant-1",
              status: "awaiting_approval",
              scope: "tenant_data",
              reason: "workspace_offboarding",
              can_approve: true,
              error_code: null,
              error_message: null,
              requested_at: "2026-03-31T00:00:00Z",
              started_at: null,
              completed_at: null,
              failed_at: null,
            },
          ],
        }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: "queued" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) });

    render(<DeletionPage />);
    const approveButton = await screen.findByRole("button", { name: /approve purge/i });
    fireEvent.click(approveButton);

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        "/admin/data-deletions/del-3/approve?target_tenant_id=tenant-1",
        { method: "POST" },
      );
    });
    expect(toastSuccessMock).toHaveBeenCalledWith("Deletion approved and queued.");
  });
});
