import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AccountProfileMenu from "../app/components/profile/AccountProfileMenu";

const authState = vi.hoisted(() => ({
  user: {
    id: "user-1",
    email: "ravi@example.test",
    tenant_id: "tenant-1",
    roles: ["editor"],
    display_name: "Ravi",
    avatar: null,
    account_status: "active" as string | undefined,
    totp_enabled: true as boolean | undefined,
  },
  profileReady: true,
}));

vi.mock("@/app/context/AuthContext", () => ({ useAuth: () => authState }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: React.AnchorHTMLAttributes<HTMLAnchorElement>) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

afterEach(() => {
  authState.profileReady = true;
  authState.user.account_status = "active";
  authState.user.totp_enabled = true;
  vi.clearAllMocks();
});

describe("AccountProfileMenu", () => {
  it("shows the display name in the header and account details in a dismissible menu", () => {
    render(<AccountProfileMenu />);
    fireEvent.click(screen.getByRole("button", { name: "Account menu for Ravi" }));

    expect(screen.getByRole("dialog", { name: "Account information" })).toBeInTheDocument();
    expect(screen.getByText("ravi@example.test")).toBeInTheDocument();
    const dialog = screen.getByRole("dialog", { name: "Account information" });
    expect(within(dialog).getByText("Editor")).toBeInTheDocument();
    expect(within(dialog).getByText("Enabled")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Profile/ })).toHaveAttribute(
      "href",
      "/dashboard/settings/profile",
    );
    expect(screen.getByRole("link", { name: /Providers/ })).toHaveAttribute(
      "href",
      "/dashboard/settings/providers",
    );

    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("dialog", { name: "Account information" })).not.toBeInTheDocument();
  });

  it("does not imply two-step verification is disabled while account details are loading", () => {
    authState.profileReady = false;
    render(<AccountProfileMenu />);
    fireEvent.click(screen.getByRole("button", { name: "Account menu for Ravi" }));
    expect(screen.getByText("Checking…")).toBeInTheDocument();
  });

  it("shows unavailable instead of guessing when security details could not be loaded", () => {
    authState.user.account_status = undefined;
    authState.user.totp_enabled = undefined;
    render(<AccountProfileMenu />);
    fireEvent.click(screen.getByRole("button", { name: "Account menu for Ravi" }));
    const dialog = screen.getByRole("dialog", { name: "Account information" });
    expect(within(dialog).getByText("Status unavailable")).toBeInTheDocument();
    expect(within(dialog).getByText("Unavailable")).toBeInTheDocument();
  });
});
