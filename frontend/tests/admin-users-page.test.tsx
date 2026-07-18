import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import AdminUsersPage from "../app/dashboard/admin/users/page";

const fetchWithAuthMock = vi.fn();
const confirmMock = vi.fn(() => true);

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.stubGlobal("confirm", confirmMock);

describe("admin users page", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it("loads users and selected user details", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            user_id: "user-1",
            tenant_id: "tenant-1",
            tenant_name: "Workspace One",
            email: "user@example.org",
            is_active: true,
            totp_enabled: false,
            roles: ["editor"],
            created_at: "2026-04-01T00:00:00Z",
            updated_at: "2026-04-01T00:00:00Z",
            last_login_at: null,
            stats: {
              documents_count: 2,
              queries_count: 3,
              conversations_count: 1,
              comments_count: 0,
              pinned_findings_count: 0,
            },
          },
        ],
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        user: {
          user_id: "user-1",
          tenant_id: "tenant-1",
          tenant_name: "Workspace One",
          email: "user@example.org",
          is_active: true,
          totp_enabled: false,
          roles: ["editor"],
          created_at: "2026-04-01T00:00:00Z",
          updated_at: "2026-04-01T00:00:00Z",
          last_login_at: null,
          stats: {
            documents_count: 2,
            queries_count: 3,
            conversations_count: 1,
            comments_count: 0,
            pinned_findings_count: 0,
          },
        },
        recent_activity: [],
      }),
    });

    render(<AdminUsersPage />);

    expect(await screen.findAllByText("user@example.org")).toHaveLength(2);
    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/admin/users/user-1");
    });
    expect(screen.getByText(/platform lifecycle oversight/i)).toBeInTheDocument();
  });

  it("shows selected user account detail", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            user_id: "user-2",
            tenant_id: "tenant-1",
            tenant_name: "Workspace One",
            email: "member@example.org",
            is_active: true,
            totp_enabled: true,
            roles: ["editor"],
            created_at: "2026-04-01T00:00:00Z",
            updated_at: "2026-04-01T00:00:00Z",
            last_login_at: "2026-04-02T00:00:00Z",
            stats: {
              documents_count: 1,
              queries_count: 1,
              conversations_count: 1,
              comments_count: 0,
              pinned_findings_count: 0,
            },
          },
        ],
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        user: {
          user_id: "user-2",
          tenant_id: "tenant-1",
          tenant_name: "Workspace One",
          email: "member@example.org",
          is_active: true,
          totp_enabled: true,
          roles: ["editor"],
          created_at: "2026-04-01T00:00:00Z",
          updated_at: "2026-04-01T00:00:00Z",
          last_login_at: "2026-04-02T00:00:00Z",
          stats: {
            documents_count: 1,
            queries_count: 1,
            conversations_count: 1,
            comments_count: 0,
            pinned_findings_count: 0,
          },
        },
        recent_activity: [],
      }),
    });
    render(<AdminUsersPage />);

    expect(await screen.findAllByText("member@example.org")).toHaveLength(2);
    expect(screen.getByText(/2fa on/i)).toBeInTheDocument();
    expect(screen.getByText(/platform lifecycle oversight/i)).toBeInTheDocument();
  });
});
