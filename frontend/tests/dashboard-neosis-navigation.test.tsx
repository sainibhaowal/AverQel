import type { ReactNode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DashboardLayout from "../app/dashboard/layout";

const routerState = vi.hoisted(() => ({ pathname: "/dashboard" }));
const toastError = vi.hoisted(() => vi.fn());
const authState = vi.hoisted(() => ({
  user: { email: "neosis-navigation@example.test", roles: [] as string[] } as null | {
    email: string;
    roles: string[];
  },
}));

vi.mock("react-hot-toast", () => ({ default: { error: toastError } }));

vi.mock("next/navigation", () => ({
  usePathname: () => routerState.pathname,
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/app/context/AuthContext", () => ({
  useAuth: () => ({
    user: authState.user,
    logout: vi.fn(),
    loading: false,
    userDisabled: false,
  }),
}));

vi.mock("@/app/context/ThemeContext", () => ({
  useTheme: () => ({ theme: "dark", toggleTheme: vi.fn() }),
}));

vi.mock("@/app/components/layout/AuthGuard", () => ({
  default: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

vi.mock("@/app/components/dashboard/SystemStatus", () => ({ default: () => null }));
vi.mock("@/app/components/layout/NotificationCenter", () => ({ default: () => null }));
vi.mock("@/app/components/ui/AverQelLogo", () => ({ default: () => null }));
vi.mock("@/app/components/ui/Breadcrumbs", () => ({ default: () => null }));
vi.mock("@/app/components/dashboard/BetaNoticeBanner", () => ({ default: () => null }));
vi.mock("@/app/components/auth/DisabledOverlay", () => ({ default: () => null }));
vi.mock("@/app/components/providers/CodexRuntimeBridge", () => ({ default: () => null }));

function installElectronBridge(
  neosisAvailable: () => Promise<boolean>,
  openNeosis: () => Promise<{
    ok: boolean;
    error?: string;
  }>,
) {
  Object.defineProperty(window, "electron", {
    configurable: true,
    value: {
      isElectron: true,
      workspace: { neosisAvailable, openNeosis },
    },
  });
}

afterEach(() => {
  Reflect.deleteProperty(window, "electron");
  authState.user = { email: "neosis-navigation@example.test", roles: [] };
  vi.clearAllMocks();
});

describe("packaged NeoSIS dashboard navigation", () => {
  it("does not show NeoSIS in a browser without the Electron bridge", () => {
    render(<DashboardLayout>Dashboard content</DashboardLayout>);

    expect(
      screen.queryByRole("button", { name: "Open NeoSIS local workspace" }),
    ).not.toBeInTheDocument();
  });

  it("shows the NeoSIS switch in the app header and below DeepSpace only in the packaged app", async () => {
    installElectronBridge(vi.fn().mockResolvedValue(true), vi.fn().mockResolvedValue({ ok: true }));

    render(<DashboardLayout>Dashboard content</DashboardLayout>);

    expect(
      await screen.findByRole("button", { name: "Switch to NeoSIS workspace" }),
    ).toBeInTheDocument();
    const neosisButton = await screen.findByRole("button", { name: "Open NeoSIS local workspace" });
    const deepSpaceLink = screen.getByRole("link", { name: "DeepSpace" });
    expect(
      deepSpaceLink.compareDocumentPosition(neosisButton) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("opens NeoSIS from the sidebar and reports startup failures", async () => {
    const openNeosis = vi
      .fn()
      .mockResolvedValue({ ok: false, error: "NeoSIS runtime is missing." });
    installElectronBridge(vi.fn().mockResolvedValue(true), openNeosis);

    render(<DashboardLayout>Dashboard content</DashboardLayout>);
    fireEvent.click(await screen.findByRole("button", { name: "Open NeoSIS local workspace" }));

    await waitFor(() => expect(openNeosis).toHaveBeenCalledOnce());
    expect(toastError).toHaveBeenCalledWith("NeoSIS runtime is missing.");
  });

  it("opens NeoSIS from the centered app header switch", async () => {
    const openNeosis = vi.fn().mockResolvedValue({ ok: true });
    installElectronBridge(vi.fn().mockResolvedValue(true), openNeosis);

    render(<DashboardLayout>Dashboard content</DashboardLayout>);
    fireEvent.click(await screen.findByRole("button", { name: "Switch to NeoSIS workspace" }));

    await waitFor(() => expect(openNeosis).toHaveBeenCalledOnce());
  });

  it("hides NeoSIS when the desktop build has no bundled runtime", async () => {
    const neosisAvailable = vi.fn().mockResolvedValue(false);
    installElectronBridge(neosisAvailable, vi.fn().mockResolvedValue({ ok: true }));

    render(<DashboardLayout>Dashboard content</DashboardLayout>);

    await waitFor(() => expect(neosisAvailable).toHaveBeenCalledOnce());
    expect(
      screen.queryByRole("button", { name: "Open NeoSIS local workspace" }),
    ).not.toBeInTheDocument();
  });

  it("hides the workspace switch while there is no signed-in user", async () => {
    authState.user = null;
    installElectronBridge(vi.fn().mockResolvedValue(true), vi.fn().mockResolvedValue({ ok: true }));

    render(<DashboardLayout>Dashboard content</DashboardLayout>);

    await waitFor(() => expect(window.electron?.workspace.neosisAvailable).toHaveBeenCalledOnce());
    expect(
      screen.queryByRole("button", { name: "Switch to NeoSIS workspace" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Open NeoSIS local workspace" }),
    ).not.toBeInTheDocument();
  });
});
