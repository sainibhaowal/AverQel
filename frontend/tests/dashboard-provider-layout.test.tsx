import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import DashboardLayout from "../app/dashboard/layout";

const routerState = vi.hoisted(() => ({ pathname: "/dashboard/settings/providers" }));

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
    user: { email: "provider-layout@example.test", roles: ["admin"] },
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
vi.mock("@/app/components/ui/AverQelLogo", () => ({
  default: (props: {
    size?: string;
    showWordmark?: boolean;
    animateWordmark?: boolean;
    wordmarkVisible?: boolean;
  }) => (
    <span
      data-testid="averqel-nav-logo"
      data-size={props.size}
      data-show-wordmark={String(props.showWordmark)}
      data-animate-wordmark={String(props.animateWordmark)}
      data-wordmark-visible={String(props.wordmarkVisible)}
    />
  ),
}));
vi.mock("@/app/components/ui/Breadcrumbs", () => ({ default: () => null }));
vi.mock("@/app/components/dashboard/BetaNoticeBanner", () => ({
  default: () => <div data-testid="beta-notice" />,
}));
vi.mock("@/app/components/auth/DisabledOverlay", () => ({ default: () => null }));
vi.mock("@/app/components/providers/CodexRuntimeBridge", () => ({ default: () => null }));

describe("dashboard provider route layout", () => {
  it("bounds provider settings to the workspace while retaining the beta banner", () => {
    const previousWidth = window.innerWidth;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 });

    try {
      render(
        <DashboardLayout>
          <div data-testid="provider-route-content" />
        </DashboardLayout>,
      );

      expect(screen.getByRole("main")).toHaveClass("overflow-y-hidden");
      expect(screen.getByTestId("beta-notice")).toBeInTheDocument();
      const navLogo = screen.getByTestId("averqel-nav-logo");
      expect(navLogo).toHaveAttribute("data-size", "footer");
      expect(navLogo).toHaveAttribute("data-show-wordmark", "true");
      expect(navLogo).toHaveAttribute("data-wordmark-visible", "true");

      const routeContent = screen.getByTestId("provider-route-content");
      expect(routeContent.parentElement).toHaveClass("flex", "min-h-0", "flex-1", "flex-col");
      expect(routeContent.parentElement?.parentElement).toHaveClass(
        "h-full",
        "min-h-0",
        "flex-col",
      );
    } finally {
      Object.defineProperty(window, "innerWidth", {
        configurable: true,
        value: previousWidth,
      });
    }
  });
});
