import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import CollectionModerationPage from "../app/dashboard/admin/collections/moderation/page";

const fetchWithAuthMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

describe("collection moderation page", () => {
  beforeEach(() => fetchWithAuthMock.mockReset());

  it("loads reports and updates their status", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [{
        id: "report-1",
        collection_id: "collection-1",
        reporter_user_id: "user-1",
        reported_user_id: "user-2",
        message_id: "message-1",
        reason: "spam",
        details: "Repeated links",
        status: "open",
        created_at: "2026-10-01T10:00:00Z",
        resolved_at: null,
      }],
    });

    render(<CollectionModerationPage />);

    expect(await screen.findByText("Repeated links")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resolve" }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/collections/admin/security/reports/report-1", {
        method: "POST",
        body: JSON.stringify({ status: "resolved" }),
      });
    });
  });
});
