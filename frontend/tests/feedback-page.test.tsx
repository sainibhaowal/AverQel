import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import FeedbackPage from "../app/dashboard/feedback/page";

const fetchWithAuthMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
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
});
