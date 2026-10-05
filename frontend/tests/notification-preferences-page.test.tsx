import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import NotificationSettingsPage from "../app/dashboard/settings/notifications/page";

const fetchWithAuthMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

const categories = [
  { code: "support", label: "Support", channels: ["in_app", "email"] },
  { code: "feedback", label: "Feedback", channels: ["in_app", "email"] },
  { code: "query", label: "Query", channels: ["in_app", "email"] },
  { code: "provider", label: "Provider", channels: ["in_app", "email"] },
  { code: "storage", label: "Storage", channels: ["in_app", "email"] },
  { code: "plan", label: "Plan", channels: ["in_app", "email"] },
  { code: "system", label: "System", channels: ["in_app", "email"] },
  { code: "documents", label: "Documents", channels: ["in_app", "email"] },
  { code: "deepspace", label: "DeepSpace", channels: ["in_app", "email"] },
  { code: "collection_moderation", label: "Collection moderation", channels: ["in_app", "email"] },
  { code: "collections", label: "Collections", channels: ["in_app"] },
];

function preferences(overrides: Record<string, unknown> = {}) {
  return {
    email_enabled: false,
    email_delivery_available: true,
    digest_frequency: "none",
    timezone: "UTC",
    preferences_configured: true,
    muted_domains: [],
    categories,
    ...overrides,
  };
}

describe("notification preferences page", () => {
  beforeEach(() => fetchWithAuthMock.mockReset());

  it("renders categories from the API and saves timezone and mute choices", async () => {
    const initial = preferences();
    fetchWithAuthMock
      .mockResolvedValueOnce({ ok: true, json: async () => initial })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...initial, muted_domains: ["collections"] }),
      });

    render(<NotificationSettingsPage />);
    expect(await screen.findByText("DeepSpace")).toBeInTheDocument();
    expect(screen.getByText("Collections")).toBeInTheDocument();
    expect(screen.getByText("Collection moderation")).toBeInTheDocument();
    const collectionsMute = screen.getByRole("checkbox", {
      name: "Mute Collections notifications",
    });
    expect(collectionsMute).not.toBeChecked();
    fireEvent.click(collectionsMute);
    expect(collectionsMute).toBeChecked();
    expect(await screen.findByText("Muted")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));

    await waitFor(() => expect(fetchWithAuthMock).toHaveBeenCalledTimes(2));
    const [, request] = fetchWithAuthMock.mock.calls[1] as [string, RequestInit];
    expect(JSON.parse(String(request.body))).toMatchObject({
      timezone: "UTC",
      muted_domains: ["collections"],
    });
    expect(await screen.findByText("Saved")).toBeInTheDocument();
  });

  it("shows retry when loading fails instead of leaving an endless spinner", async () => {
    fetchWithAuthMock
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        json: async () => ({ detail: "Temporarily unavailable" }),
      })
      .mockResolvedValueOnce({ ok: true, json: async () => preferences() });

    render(<NotificationSettingsPage />);
    expect(await screen.findByText("Temporarily unavailable")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Email delivery")).toBeInTheDocument();
  });

  it("allows disabling an existing email opt-in while SMTP is unavailable", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => preferences({ email_enabled: true, email_delivery_available: false }),
    });

    render(<NotificationSettingsPage />);
    const toggle = await screen.findByRole("checkbox", { name: "Send notification email" });
    expect(toggle).toBeEnabled();
    fireEvent.click(toggle);
    expect(toggle).not.toBeChecked();
  });

  it("shows an in-app-only interface when email delivery is unavailable", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => preferences({ email_delivery_available: false }),
    });

    render(<NotificationSettingsPage />);

    expect(
      await screen.findByText("Choose which updates appear in your in-app notification center"),
    ).toBeInTheDocument();
    const preferencesPanel = screen.getByText("In-app notification categories").closest("section");
    expect(preferencesPanel).toHaveClass("w-full");
    expect(preferencesPanel).not.toHaveClass("max-w-3xl");
    const pageContent = preferencesPanel?.closest(".dashboard-theme-scope");
    expect(pageContent).toHaveClass("w-full", "min-w-0");
    expect(pageContent).not.toHaveClass("p-4", "sm:p-6", "lg:p-8");
    expect(
      screen.getByText(/Check a category to mute it\. Muted notifications are hidden/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Active")).toHaveLength(11);
    expect(screen.queryByText("Email cadence")).not.toBeInTheDocument();
    expect(screen.queryByText("Digest time zone")).not.toBeInTheDocument();
    expect(screen.queryByText("In-app · Email")).not.toBeInTheDocument();
    expect(screen.queryByRole("checkbox", { name: "Send notification email" })).toBeNull();
  });
});
