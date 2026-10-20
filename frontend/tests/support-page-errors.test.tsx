import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import UserSupportPage from "../app/dashboard/support/page";
import AdminSupportPage from "../app/dashboard/admin/support/page";

const fetchWithAuthMock = vi.hoisted(() => vi.fn());
const authState = vi.hoisted(() => ({
  user: { id: "admin-id", email: "admin@example.test", roles: ["admin"] },
}));

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.mock("@/app/dashboard/support/SupportEncryptionGate", () => ({
  useSupportEncryption: () => ({
    ready: true,
    context: {
      privateKey: {} as CryptoKey,
      keyId: "test-support-key",
      ownPublicKey: { key_id: "test-support-key", public_key: "test-public-key" },
      adminPublicKey: { key_id: "test-admin-key", public_key: "test-admin-public-key" },
    },
    panel: null,
  }),
}));

vi.mock("@/app/dashboard/admin/SupportEncryptionMigration", () => ({
  default: () => null,
}));

vi.mock("@/app/context/AuthContext", () => ({
  useAuth: () => ({ user: authState.user, userDisabled: false }),
}));

vi.mock("next/navigation", () => ({
  useSearchParams: () => ({ get: () => null }),
}));

vi.mock("@/app/components/ui/DashboardSectionHeader", () => ({
  default: ({ title }: { title: string }) => <h1>{title}</h1>,
}));

describe("support queue load failures", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it("does not show an empty user history when the support API fails", async () => {
    fetchWithAuthMock.mockResolvedValue({ ok: false, status: 503 });

    render(<UserSupportPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your ticket history could not be loaded.",
    );
    expect(screen.queryByText("No tickets submitted yet.")).toBeNull();
  });

  it("shows a retryable access error instead of an empty admin queue on 403", async () => {
    fetchWithAuthMock.mockResolvedValue({ ok: false, status: 403 });

    render(<AdminSupportPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "allowlisted platform-administrator account",
    );
    expect(screen.queryByText("No users found.")).toBeNull();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });
});

describe("admin support selected user", () => {
  it("shows the user identity once in the selector and uses a neutral history heading", async () => {
    const userEmail = "rav.singh@example.test";
    fetchWithAuthMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        open_count: 1,
        overdue_count: 0,
        total: 1,
        items: [
          {
            id: "ticket-1",
            user_id: "user-1",
            user_email: userEmail,
            subject: "Test support ticket",
            description: "A test description.",
            category: "question",
            status: "open",
            priority: "normal",
            created_at: "2026-10-20T09:00:00Z",
            updated_at: "2026-10-20T09:00:00Z",
          },
        ],
      }),
    });

    render(<AdminSupportPage />);

    expect(await screen.findByRole("heading", { name: "Support history" })).toBeInTheDocument();
    expect(screen.getAllByText(userEmail)).toHaveLength(1);
    expect(screen.queryByText(/User ID:/)).toBeNull();
  });
});
