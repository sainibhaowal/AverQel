import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import CollectionModerationPage from "../app/dashboard/admin/collections/moderation/page";

const fetchWithAuthMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

const report = {
  id: "report-1",
  collection_id: "collection-1",
  collection_name: "Team workspace",
  status: "open",
  created_at: "2026-10-01T10:00:00Z",
  resolved_at: null,
};

function listResponse(items: unknown[] = [report], total = items.length, hasMore = false) {
  return {
    ok: true,
    headers: {
      get: (name: string) =>
        name === "X-Total-Count" ? String(total) : name === "X-Has-More" ? String(hasMore) : null,
    },
    json: async () => items,
  };
}

describe("collection moderation page", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    window.history.replaceState({}, "", "/dashboard/admin/collections/moderation");
  });

  it("loads contextual reports, updates status, and refreshes the current page", async () => {
    fetchWithAuthMock.mockImplementation(async (url: string, init?: RequestInit) => {
      if (init?.method === "POST")
        return { ok: true, json: async () => ({ ...report, status: "resolved" }) };
      if (init?.method !== "POST" && url === "/collections/admin/security/reports/report-1") {
        return {
          ok: true,
          json: async () => ({ ...report, reason: "spam", details: "Repeated links" }),
        };
      }
      return listResponse();
    });

    render(<CollectionModerationPage />);

    expect(screen.getByRole("link", { name: "Back To Dashboard" })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    expect(await screen.findByText("Moderation report")).toBeInTheDocument();
    expect(screen.getByText("Team workspace")).toBeInTheDocument();
    expect(screen.queryByText("user-1")).not.toBeInTheDocument();
    expect(screen.queryByText("Repeated links")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /view report details/i }));
    expect(await screen.findByText("Repeated links")).toBeInTheDocument();
    expect(screen.getByText("spam")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Resolve" }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        "/collections/admin/security/reports/report-1",
        {
          method: "POST",
          body: JSON.stringify({ status: "resolved", moderator_note: null }),
        },
      );
    });
    await waitFor(() => expect(fetchWithAuthMock).toHaveBeenCalledTimes(4));
  });

  it("paginates without hiding older reports", async () => {
    fetchWithAuthMock.mockImplementation(async (url?: string) => {
      if (String(url ?? "").includes("offset=25"))
        return listResponse([{ ...report, id: "report-26" }], 26, false);
      return listResponse(
        Array.from({ length: 25 }, (_, index) => ({ ...report, id: `report-${index + 1}` })),
        26,
        true,
      );
    });

    render(<CollectionModerationPage />);
    expect(await screen.findByText("Showing 1–25 of 26")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    expect(await screen.findByText("Showing 26–26 of 26")).toBeInTheDocument();
    expect(fetchWithAuthMock).toHaveBeenLastCalledWith(
      "/collections/admin/security/reports?status=open&limit=25&offset=25",
    );
  });

  it("opens a notification deep link to its tenant-scoped report", async () => {
    window.history.replaceState({}, "", "/dashboard/admin/collections/moderation?report=report-1");
    fetchWithAuthMock.mockImplementation(async (url?: string) => {
      if (String(url ?? "").includes("report_id=report-1"))
        return listResponse([{ ...report, status: "resolved" }]);
      return listResponse();
    });

    render(<CollectionModerationPage />);

    expect(await screen.findByText("Moderation report")).toBeInTheDocument();
    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        expect.stringContaining("status=all&limit=25&offset=0&report_id=report-1"),
      );
    });
    expect(await screen.findByRole("button", { name: "Reopen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Resolve" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dismiss" })).not.toBeInTheDocument();
  });

  it("saves internal notes separately and shows append-only activity history", async () => {
    const action = {
      id: "action-1",
      report_id: "report-1",
      actor_role: "admin",
      action_type: "note_added",
      previous_status: null,
      new_status: "open",
      note: "Confirmed with the workspace owner.",
      created_at: "2026-10-01T11:00:00Z",
    };
    fetchWithAuthMock.mockImplementation(async (url?: string, init?: RequestInit) => {
      if (String(url ?? "").includes("/history")) {
        return {
          ...listResponse([action], 1, false),
        };
      }
      if (init?.method !== "POST" && url === "/collections/admin/security/reports/report-1") {
        return {
          ok: true,
          json: async () => ({ ...report, reason: "spam", details: "Repeated links" }),
        };
      }
      if (init?.method === "POST") return { ok: true, json: async () => report };
      return listResponse();
    });

    render(<CollectionModerationPage />);
    expect(await screen.findByText("Moderation report")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /view report details/i }));
    expect(await screen.findByText("Repeated links")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Internal moderator note"), {
      target: { value: "Confirmed with the workspace owner." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        "/collections/admin/security/reports/report-1",
        {
          method: "POST",
          body: JSON.stringify({
            status: "open",
            moderator_note: "Confirmed with the workspace owner.",
          }),
        },
      );
    });

    fireEvent.click(screen.getByRole("button", { name: /Activity history/ }));
    expect(await screen.findByText("Confirmed with the workspace owner.")).toBeInTheDocument();
    expect(screen.getByText("Actor role: admin")).toBeInTheDocument();
  });
});
