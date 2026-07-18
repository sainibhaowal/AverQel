import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import ProviderOAuthPanel from "../app/components/providers/ProviderOAuthPanel";

describe("provider oauth gating", () => {
  it("hides usable account-link actions when oauth support is unavailable", () => {
    const onConnect = vi.fn();
    const onDisconnect = vi.fn();

    render(
      <ProviderOAuthPanel
        status={{
          available: false,
          connected: false,
          provider_type: "openai",
          message: "OpenAI account linking is disabled until officially verified and configured.",
        }}
        onConnect={onConnect}
        onDisconnect={onDisconnect}
      />,
    );

    const connectButton = screen.getByRole("button", { name: /connect openai/i });
    const disconnectButton = screen.getByRole("button", { name: /disconnect/i });

    expect(connectButton).toBeDisabled();
    expect(disconnectButton).toBeDisabled();
    expect(
      screen.getByText(/disabled until officially verified and configured/i),
    ).toBeInTheDocument();

    fireEvent.click(connectButton);
    fireEvent.click(disconnectButton);

    expect(onConnect).not.toHaveBeenCalled();
    expect(onDisconnect).not.toHaveBeenCalled();
  });
});
