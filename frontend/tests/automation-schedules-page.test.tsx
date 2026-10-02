import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AutomationSchedulesPanel from "../app/dashboard/documents/organization/AutomationSchedulesPanel";

const fetchWithAuthMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.mock("@/app/components/ui/AverQelDialogHost", () => ({
  averqelConfirm: vi.fn().mockResolvedValue(true),
}));

describe("automation schedules page", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    fetchWithAuthMock.mockImplementation((path: string) => {
      if (path === "/documents/organization/automation-schedules") {
        return Promise.resolve({ ok: true, json: async () => ({ items: [] }) });
      }
      if (path === "/documents/organization/classification-rules") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            items: [{ id: "rule-1", name: "Finance PDFs", enabled: true, priority: 10 }],
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
  });

  it("creates a daily schedule for all enabled rules", async () => {
    render(<AutomationSchedulesPanel />);
    const name = await screen.findByPlaceholderText("Schedule name");
    fireEvent.change(name, { target: { value: "Daily classification" } });

    fetchWithAuthMock.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/documents/organization/automation-schedules" && init?.method === "POST") {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: "schedule-1",
            name: "Daily classification",
            cadence: "daily",
            interval_seconds: 3600,
            timezone: "UTC",
            run_time: "09:00",
            weekday: null,
            enabled: true,
            rule_ids: [],
            rule_names: [],
            runs_all_enabled_rules: true,
            next_run_at: "2026-10-01T09:00:00Z",
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ items: [] }) });
    });

    fireEvent.click(screen.getByRole("button", { name: /create schedule/i }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        "/documents/organization/automation-schedules",
        expect.objectContaining({ method: "POST" }),
      );
    });
    expect(await screen.findByText("Daily classification")).toBeInTheDocument();
    expect(screen.getAllByText("All enabled rules")).toHaveLength(2);
  });
});
