import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import BetaNoticeBanner from "../app/components/dashboard/BetaNoticeBanner";

const pushMock = vi.hoisted(() => vi.fn());
const fetchWithAuthMock = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/lib/api", () => ({
  fetchWithAuth: fetchWithAuthMock,
}));

const betaOn = {
  beta: { enabled: true, plan_id: "editor", plan_name: "Editor", resurface_hours: 36 },
};

function mockPlansOk(body: unknown) {
  fetchWithAuthMock.mockResolvedValue({ ok: true, json: async () => body });
}

describe("BetaNoticeBanner", () => {
  beforeEach(() => {
    pushMock.mockClear();
    fetchWithAuthMock.mockReset();
    window.localStorage.clear();
  });

  it("shows the beta grant and navigates to the plan page on click", async () => {
    mockPlansOk(betaOn);
    render(<BetaNoticeBanner />);

    const region = await screen.findByRole("region", { name: /Beta notice/i });
    expect(region).toHaveTextContent(/free until production release/i);

    fireEvent.click(screen.getByRole("button", { name: /View your Editor plan/i }));
    expect(pushMock).toHaveBeenCalledWith("/dashboard/settings/plan");
  });

  it("stays hidden when the beta block is disabled (admins, flag off)", async () => {
    mockPlansOk({ beta: { enabled: false } });
    render(<BetaNoticeBanner />);

    await waitFor(() => expect(fetchWithAuthMock).toHaveBeenCalled());
    expect(screen.queryByRole("region", { name: /Beta notice/i })).not.toBeInTheDocument();
  });

  it("honours Don't show again across visits", async () => {
    mockPlansOk(betaOn);
    const { unmount } = render(<BetaNoticeBanner />);
    await screen.findByRole("region", { name: /Beta notice/i });

    fireEvent.click(screen.getByRole("button", { name: /Don't show again/i }));
    expect(screen.queryByRole("region", { name: /Beta notice/i })).not.toBeInTheDocument();
    unmount();

    render(<BetaNoticeBanner />);
    await waitFor(() => expect(fetchWithAuthMock).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("region", { name: /Beta notice/i })).not.toBeInTheDocument();
  });

  it("resurfaces after the configured hours when only dismissed", async () => {
    mockPlansOk(betaOn);
    window.localStorage.setItem(
      "averqel_beta_notice",
      JSON.stringify({ lastShown: Date.now() - 37 * 3600 * 1000 }),
    );
    render(<BetaNoticeBanner />);

    await screen.findByRole("region", { name: /Beta notice/i });
  });

  it("stays hidden inside the resurface window", async () => {
    mockPlansOk(betaOn);
    window.localStorage.setItem(
      "averqel_beta_notice",
      JSON.stringify({ lastShown: Date.now() - 3600 * 1000 }),
    );
    render(<BetaNoticeBanner />);

    await waitFor(() => expect(fetchWithAuthMock).toHaveBeenCalled());
    expect(screen.queryByRole("region", { name: /Beta notice/i })).not.toBeInTheDocument();
  });
});
