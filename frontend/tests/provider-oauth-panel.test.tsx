import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import ProviderOAuthPanel from "../app/components/providers/ProviderOAuthPanel";

describe("provider oauth panel", () => {
  it("only enables connect when oauth is available", () => {
    const onConnect = vi.fn();
    const onDisconnect = vi.fn();

    const { rerender } = render(
      <ProviderOAuthPanel
        status={{
          available: false,
          connected: false,
          provider_type: "openai",
          message: "API key only",
        }}
        onConnect={onConnect}
        onDisconnect={onDisconnect}
      />,
    );

    expect(screen.getByRole("button", { name: /connect openai/i })).toBeDisabled();

    rerender(
      <ProviderOAuthPanel
        status={{
          available: true,
          connected: false,
          provider_type: "openai",
          message: "Official OAuth is available",
        }}
        onConnect={onConnect}
        onDisconnect={onDisconnect}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /connect openai/i }));
    expect(onConnect).toHaveBeenCalled();
  });
});
