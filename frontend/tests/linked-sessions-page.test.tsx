import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import SessionsPage from "../app/dashboard/settings/sessions/page";

const fetchWithAuthMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

function makeSession(index: number, current = false) {
  return {
    id: `session-${index}`,
    device_id: `browser-${index.toString().padStart(8, "0")}`,
    label: `Browser ${index}`,
    user_agent: "Chrome on Linux",
    created_at: "2026-10-01T10:00:00Z",
    last_seen_at: "2026-10-01T10:05:00Z",
    revoked_at: null,
    current,
  };
}

describe("linked sessions page", () => {
  beforeEach(() => fetchWithAuthMock.mockReset());

  it("lists sessions and revokes a non-current session", async () => {
    fetchWithAuthMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [makeSession(1)],
      })
      .mockResolvedValueOnce({ ok: true });

    render(<SessionsPage />);
    expect(screen.getByRole("link", { name: "Back" })).toHaveAttribute(
      "href",
      "/dashboard/settings",
    );
    expect(screen.getByRole("main")).not.toHaveClass("max-w-5xl");
    expect(await screen.findByText("Browser 1")).toBeInTheDocument();
    expect(screen.getByText(/Last token refresh/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenNthCalledWith(2, "/auth/sessions/session-1", {
        method: "DELETE",
      });
    });
    expect(await screen.findByText("Revoked")).toBeInTheDocument();
  });

  it("does not offer revoke for the current session", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [makeSession(1, true)],
    });

    render(<SessionsPage />);
    expect(await screen.findByText("This session")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revoke" })).not.toBeInTheDocument();
    expect(fetchWithAuthMock).toHaveBeenCalledTimes(1);
  });

  it("loads additional session pages without changing the list shape", async () => {
    fetchWithAuthMock
      .mockResolvedValueOnce({
        ok: true,
        json: async () => Array.from({ length: 26 }, (_, index) => makeSession(index)),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => [makeSession(25)] });

    render(<SessionsPage />);
    expect(await screen.findByText("Browser 0")).toBeInTheDocument();
    expect(screen.queryByText("Browser 25")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load more sessions" }));

    expect(await screen.findByText("Browser 25")).toBeInTheDocument();
    expect(fetchWithAuthMock).toHaveBeenNthCalledWith(1, "/auth/sessions?limit=26&offset=0");
    expect(fetchWithAuthMock).toHaveBeenNthCalledWith(2, "/auth/sessions?limit=26&offset=25");
  });
});
