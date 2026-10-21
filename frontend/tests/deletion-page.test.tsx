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
    user: { id: "admin-1", tenant_id: "tenant-admin", roles: ["admin"] },
  }),
}));

vi.mock("react-hot-toast", () => ({
  default: {
    success: (...args: unknown[]) => toastSuccessMock(...args),
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}));

describe("admin account deletion page", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    toastSuccessMock.mockReset();
    toastErrorMock.mockReset();
  });

  it("loads accounts and permanently deletes only the confirmed account", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ allowed: true, reason: null }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            user_id: "target-1",
            tenant_id: "tenant-1",
            tenant_name: "Workspace One",
            email: "member@example.org",
            is_active: true,
            created_at: "2026-05-01T10:00:00Z",
            last_login_at: "2026-10-17T08:30:00Z",
          },
        ],
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) });
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ pending_storage_cleanup_count: 3 }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) });

    render(<DeletionPage />);

    expect(await screen.findAllByText("member@example.org")).toHaveLength(3);
    expect(screen.getByText(/last successful sign-in/i)).toBeInTheDocument();
    expect(fetchWithAuthMock).toHaveBeenCalledWith("/admin/users");
    expect(fetchWithAuthMock).toHaveBeenCalledWith("/admin/storage-cleanup?limit=200");

    fireEvent.change(screen.getByLabelText(/type delete member@example.org/i), {
      target: { value: "DELETE member@example.org" },
    });
    fireEvent.click(screen.getByRole("button", { name: /erase account and owned data/i }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenNthCalledWith(5, "/admin/users/target-1", {
        method: "DELETE",
        body: JSON.stringify({ confirmation: "DELETE member@example.org" }),
      });
    });
    expect(toastSuccessMock).toHaveBeenCalledWith(
      "Account erased. 3 stored files are queued for background cleanup.",
    );
    expect(fetchWithAuthMock).toHaveBeenNthCalledWith(6, "/admin/storage-cleanup?limit=200");
    expect(screen.queryByText("member@example.org")).not.toBeInTheDocument();
  });

  it("requires the exact account confirmation before sending a deletion request", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ allowed: true, reason: null }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            user_id: "target-2",
            tenant_id: "tenant-1",
            tenant_name: "Workspace One",
            email: "another@example.org",
            is_active: true,
            created_at: "2026-05-01T10:00:00Z",
            last_login_at: null,
          },
        ],
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) });
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: async () => ({ items: [] }) });

    render(<DeletionPage />);
    expect(await screen.findAllByText("another@example.org")).toHaveLength(3);
    const deleteButton = screen.getByRole("button", { name: /erase account and owned data/i });
    expect(deleteButton).toBeDisabled();
    expect(fetchWithAuthMock).toHaveBeenCalledTimes(4);
  });

  it("does not request cross-tenant deletion data when platform MFA setup is required", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ allowed: false, reason: "ADMIN_MFA_SETUP_REQUIRED" }),
    });

    render(<DeletionPage />);

    expect(
      await screen.findByText("Set up authenticator MFA before using platform administration."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open account security settings/i })).toHaveAttribute(
      "href",
      "/dashboard/settings/profile",
    );
    expect(fetchWithAuthMock).toHaveBeenCalledTimes(1);
    expect(fetchWithAuthMock).toHaveBeenCalledWith("/admin/access");
  });

  it("explains platform allowlist requirements without loading global accounts", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ allowed: false, reason: "PLATFORM_ADMIN_ALLOWLIST_REQUIRED" }),
    });

    render(<DeletionPage />);

    expect(
      await screen.findByText(/not configured in the deployment’s platform-admin allowlist/i),
    ).toBeInTheDocument();
    expect(fetchWithAuthMock).toHaveBeenCalledTimes(1);
    expect(fetchWithAuthMock).toHaveBeenCalledWith("/admin/access");
  });
});
