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
        total_queries: 42,
        avg_confidence: 0.87,
        volume_over_time: [{ date: "2026-03-19", count: 4 }],
        confidence_distribution: { high: 3, medium: 1, low: 0 },
        api_latency_p95_ms: null,
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

  it("renders real latency card when api_latency_p95_ms is provided", async () => {
    fetchWithAuthMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        total_queries: 10,
        avg_confidence: 0.75,
        volume_over_time: [],
        confidence_distribution: { high: 5, medium: 3, low: 2 },
        api_latency_p95_ms: 245.0,
      }),
    });

    render(<AnalyticsDashboard />);

    expect(await screen.findByText(/api latency/i)).toBeInTheDocument();
    expect(screen.getByText("245ms")).toBeInTheDocument();
  });

  it("formats latency as seconds when value is 1000ms or more", async () => {
    fetchWithAuthMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        total_queries: 5,
        avg_confidence: 0.6,
        volume_over_time: [],
        confidence_distribution: { high: 2, medium: 2, low: 1 },
        api_latency_p95_ms: 1200.0,
      }),
    });

    render(<AnalyticsDashboard />);

    expect(await screen.findByText("1.20s")).toBeInTheDocument();
  });
});
