import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import FeedbackPage from "../app/dashboard/feedback/page";

const fetchWithAuthMock = vi.fn();

vi.mock("../lib/api", () => ({
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

describe("feedback page navigation", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    fetchWithAuthMock.mockImplementation(async (url: string) => ({
      ok: true,
      json: async () => (url.endsWith("/campaigns") ? [] : []),
    }));
  });

  it("returns to the dashboard through the shared page header", async () => {
    render(<FeedbackPage />);

    expect(screen.getByRole("link", { name: "Back To Dashboard" })).toHaveAttribute(
      "href",
      "/dashboard",
    );
    await waitFor(() => expect(fetchWithAuthMock).toHaveBeenCalledTimes(2));
  });

  it("shows a retryable error instead of an empty history when loading fails", async () => {
    fetchWithAuthMock.mockImplementation(async (url: string) =>
      url.endsWith("/campaigns")
        ? { ok: true, json: async () => [] }
        : { ok: false, status: 503, json: async () => ({}) },
    );

    render(<FeedbackPage />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your feedback history could not be loaded.",
    );
    expect(screen.queryByText("Your submitted feedback and team replies will appear here.")).toBeNull();

    fetchWithAuthMock.mockImplementation(async () => ({ ok: true, json: async () => [] }));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(screen.getByText("Your submitted feedback and team replies will appear here.")).toBeInTheDocument();
  });
});
