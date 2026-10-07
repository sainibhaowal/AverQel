import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import StorageDetailsPage from "../app/dashboard/settings/storage/page";

const fetchWithAuthMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => ({
  fetchWithAuth: fetchWithAuthMock,
}));

const response = {
  current_plan: {
    id: "free",
    name: "Free",
    storage_limit_bytes: 500 * 1024 * 1024,
    description: "Essential AverQel workspace storage.",
    admin_account: false,
  },
  usage: { total_bytes: 12 * 1024 * 1024 },
  metrics: [
    {
      key: "documents",
      label: "Uploaded documents",
      description: "Original document objects uploaded for this tenant.",
      bytes: 12 * 1024 * 1024,
      record_count: 2,
      included_in_quota: true,
      measurement: "Exact object size",
    },
    {
      key: "chat_history",
      label: "Chat history and notes",
      description: "Conversation titles, notes, messages, and message versions.",
      bytes: 1000,
      record_count: 4,
      included_in_quota: false,
      measurement: "Estimated logical text bytes",
    },
  ],
  quota_metering_note: "Safe aggregate metrics only.",
  generated_at: "2026-09-22T10:00:00+00:00",
};

describe("storage details page", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockImplementation(async (endpoint: string) => ({
      ok: true,
      json: async () =>
        endpoint === "/storage/retention"
          ? { mode: "off", days: 0, policy_version: 1, automatic_purge_enabled: false }
          : response,
    }));
  });

  it("shows live quota and expandable category inventory", async () => {
    render(<StorageDetailsPage />);

    await waitFor(() => expect(screen.getByText("Storage used by category")).toBeInTheDocument());
    expect(screen.getByText("Visual storage overview")).toBeInTheDocument();
    expect(screen.getByText("Live meter")).toBeInTheDocument();
    expect(screen.getByText("Metered category distribution")).toBeInTheDocument();
    expect(
      screen.getByRole("img", { name: /percent of storage allocation used/i }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Uploaded documents").length).toBeGreaterThanOrEqual(1);
    const categoryButton = screen.getByRole("button", { name: /uploaded documents/i });
    expect(categoryButton).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(categoryButton);
    expect(categoryButton).toHaveAttribute("aria-expanded", "true");
    fireEvent.click(categoryButton);
    expect(categoryButton).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByText("Account data inventory")).toBeInTheDocument();
    expect(screen.getByText("Safe aggregate metrics only.")).toBeInTheDocument();
  });

  it("shows the safe storage inactivity policy choices", async () => {
    render(<StorageDetailsPage />);

    await waitFor(() => expect(screen.getByLabelText("Inactivity period")).toBeInTheDocument());
    expect(screen.getByText("Archive-first · purge disabled")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Off" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "30 days" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "60 days" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "90 days" })).toBeInTheDocument();
  });
});
