import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WelcomeFlow from "../app/components/onboarding/WelcomeFlow";

const mocks = vi.hoisted(() => ({
  user: {
    id: "new-user",
    email: "new@example.test",
    tenant_id: "tenant-1",
    roles: ["user"],
    display_name: null as string | null,
    avatar: null as string | null,
    onboarding_completed: false,
  },
  updateUserProfile: vi.fn(),
  setTheme: vi.fn(),
  fetchWithAuth: vi.fn(),
  push: vi.fn(),
}));

vi.mock("@/app/context/AuthContext", () => ({
  useAuth: () => ({
    user: mocks.user,
    profileReady: true,
    updateUserProfile: (profile: Partial<typeof mocks.user>) => {
      Object.assign(mocks.user, profile);
      mocks.updateUserProfile(profile);
    },
  }),
}));
vi.mock("@/app/context/ThemeContext", () => ({
  useTheme: () => ({ theme: "dark", setTheme: mocks.setTheme, toggleTheme: vi.fn() }),
}));
vi.mock("@/lib/api", () => ({ fetchWithAuth: mocks.fetchWithAuth }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock("@/app/components/ui/AverQelLogo", () => ({
  default: () => <span>AverQel</span>,
}));
vi.mock("@/app/components/ui/DeepSpaceMark", () => ({
  default: () => <span>DeepSpace mark</span>,
}));
vi.mock("@/app/components/ui/NeoSISMark", () => ({ default: () => <span>NeoSIS mark</span> }));
vi.mock("../app/components/onboarding/QuickProviderSetup", () => ({
  default: ({ onOpenSettings }: { onOpenSettings: () => void }) => (
    <div>
      <p>Quick provider setup</p>
      <button type="button" onClick={onOpenSettings}>
        More provider options
      </button>
    </div>
  ),
}));

function successResponse(data: Record<string, unknown>) {
  return { ok: true, json: async () => data };
}

afterEach(() => {
  mocks.user.display_name = null;
  mocks.user.avatar = null;
  mocks.user.onboarding_completed = false;
  mocks.updateUserProfile.mockReset();
  mocks.setTheme.mockReset();
  mocks.fetchWithAuth.mockReset();
  mocks.push.mockReset();
  Reflect.deleteProperty(window, "electron");
});

describe("first-run welcome flow", () => {
  it("lets a new user personalize their profile, continue, and save completion", async () => {
    mocks.fetchWithAuth
      .mockResolvedValueOnce(successResponse({ display_name: "Ravi", avatar: null }))
      .mockResolvedValueOnce(successResponse({ onboarding_completed: true }));

    render(<WelcomeFlow neosisAvailable={false} />);
    expect(await screen.findByRole("dialog", { name: /Welcome/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(
      await screen.findByRole("heading", { name: "Your work, in one place" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(
      await screen.findByRole("heading", { name: "Make it feel like yours" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Ravi" } });
    fireEvent.click(screen.getByRole("button", { name: "Save and continue" }));

    expect(await screen.findByText("Quick provider setup")).toBeInTheDocument();
    const identityRequest = mocks.fetchWithAuth.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(String(identityRequest.body))).toEqual({
      display_name: "Ravi",
    });
    expect(mocks.updateUserProfile).toHaveBeenCalledWith({ display_name: "Ravi", avatar: null });

    fireEvent.click(screen.getByRole("button", { name: "Start using AverQel" }));
    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalledTimes(2));
    expect(mocks.updateUserProfile).toHaveBeenLastCalledWith({ onboarding_completed: true });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: /Welcome/ })).not.toBeInTheDocument(),
    );
  });

  it("can skip the welcome slides and persists completion", async () => {
    mocks.fetchWithAuth.mockResolvedValueOnce(successResponse({ onboarding_completed: true }));
    render(<WelcomeFlow neosisAvailable={false} />);

    fireEvent.click(await screen.findByRole("button", { name: "Skip setup" }));

    await waitFor(() => expect(mocks.fetchWithAuth).toHaveBeenCalledOnce());
    expect(JSON.parse(String(mocks.fetchWithAuth.mock.calls[0][1].body))).toEqual({
      onboarding_completed: true,
    });
    expect(screen.queryByRole("dialog", { name: /Welcome/ })).not.toBeInTheDocument();
  });

  it("does not show onboarding to accounts that already completed it", () => {
    mocks.user.onboarding_completed = true;
    render(<WelcomeFlow neosisAvailable={false} />);
    expect(screen.queryByRole("dialog", { name: /Welcome/ })).not.toBeInTheDocument();
  });

  it("records a light-theme selection while keeping the welcome dialog open", async () => {
    render(<WelcomeFlow neosisAvailable={false} />);

    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(
      await screen.findByRole("heading", { name: "Your work, in one place" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(
      await screen.findByRole("heading", { name: "Make it feel like yours" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Light" }));

    expect(mocks.setTheme).toHaveBeenCalledWith("light");
    expect(screen.getByRole("dialog", { name: /Make it feel like yours/ })).toHaveClass(
      "welcome-flow-dialog",
    );
  });
});
