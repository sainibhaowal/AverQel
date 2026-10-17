import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import AnalyticsDashboard from "../app/dashboard/admin/analytics/page";

const fetchWithAuthMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

describe("analytics dashboard page", () => {
  it("loads analytics through the shared authenticated API client", async () => {
    fetchWithAuthMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        suppressed: false,
        total_queries: 42,
        avg_confidence: 0.87,
        volume_over_time: [{ date: "2026-03-19", count: 4 }],
        confidence_distribution: { high: 3, medium: 1, low: 0 },
      }),
    });

    render(<AnalyticsDashboard />);

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/analytics/dashboard");
    });

    expect(await screen.findByText(/analytics & telemetry/i)).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.queryByText(/api latency/i)).not.toBeInTheDocument();
  });

  it("hides analytics when the contributor threshold is not met", async () => {
    fetchWithAuthMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        suppressed: true,
        total_queries: null,
        avg_confidence: null,
        volume_over_time: [],
        confidence_distribution: null,
      }),
    });

    render(<AnalyticsDashboard />);

    expect(await screen.findByText(/analytics are hidden/i)).toBeInTheDocument();
    expect(screen.getByText(/at least five distinct workspace members/i)).toBeInTheDocument();
    expect(screen.queryByText(/total queries|confidence distribution/i)).not.toBeInTheDocument();
  });
});
