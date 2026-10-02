import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import SessionsPage from "../app/dashboard/settings/sessions/page";

const fetchWithAuthMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

describe("linked sessions page", () => {
  beforeEach(() => fetchWithAuthMock.mockReset());

  it("lists sessions and revokes a non-current session", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [{
        id: "session-1",
        device_id: "browser-12345678",
        label: "Laptop",
        user_agent: "Browser",
        created_at: "2026-10-01T10:00:00Z",
        last_seen_at: "2026-10-01T10:05:00Z",
        revoked_at: null,
        current: false,
      }],
    });

    render(<SessionsPage />);
    expect(await screen.findByText("Laptop")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /revoke/i }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/auth/sessions/session-1", { method: "DELETE" });
    });
  });
});
