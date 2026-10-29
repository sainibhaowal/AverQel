import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import OpenAICodexLoginPanel from "@/app/components/providers/OpenAICodexLoginPanel";

const cliAccount: ElectronCodexAccount = {
  id: "0123456789abcdef0123456789abcdef",
  email: null,
  name: "Codex CLI ChatGPT login",
  connected: true,
  source: "codex_cli",
  planType: "plus",
};
const browserAccount: ElectronCodexAccount = {
  id: "fedcba9876543210fedcba9876543210",
  email: "user@example.test",
  name: "User",
  connected: true,
  source: "chatgpt",
};
const model: ElectronCodexModel = { id: "gpt-5-codex", name: "GPT-5 Codex", kind: "chat" };

describe("OpenAICodexLoginPanel", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    delete window.electron;
  });

  it("prefers the local Codex CLI login and keeps browser sign-in as an explicit fallback", async () => {
    const status = vi.fn().mockResolvedValue({
      available: true,
      chatgptSignInAvailable: true,
      accounts: [cliAccount],
    });
    const connect = vi.fn().mockResolvedValue({ account: cliAccount, models: [model] });
    const models = vi.fn().mockResolvedValue([model]);
    const disconnect = vi.fn().mockResolvedValue({ ok: true });
    Object.defineProperty(window, "electron", {
      configurable: true,
      value: {
        isElectron: true,
        codex: { status, connect, models, disconnect },
      },
    });

    render(<OpenAICodexLoginPanel initialAccountId={null} onChange={vi.fn()} />);

    await waitFor(() => expect(models).toHaveBeenCalledWith(cliAccount.id));
    expect(screen.getByRole("button", { name: "Use Codex CLI login" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Sign in with ChatGPT instead" }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("combobox", { name: "Saved Codex account" }));
    expect(
      screen.getByRole("option", { name: "Use signed-in Codex CLI account (PLUS)" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Sign in with ChatGPT instead" }));
    await waitFor(() => expect(connect).toHaveBeenCalledWith(null, "chatgpt"));
    expect(status).toHaveBeenCalled();
  });

  it("explains when local removal succeeded but OpenAI revocation was not confirmed", async () => {
    const status = vi.fn().mockResolvedValue({
      available: true,
      chatgptSignInAvailable: true,
      accounts: [browserAccount],
    });
    const models = vi.fn().mockResolvedValue([model]);
    const disconnect = vi.fn().mockResolvedValue({ ok: true, revoked: false });
    Object.defineProperty(window, "electron", {
      configurable: true,
      value: {
        isElectron: true,
        codex: { status, connect: vi.fn(), models, disconnect },
      },
    });

    render(<OpenAICodexLoginPanel initialAccountId={browserAccount.id} onChange={vi.fn()} />);
    await waitFor(() => expect(models).toHaveBeenCalledWith(browserAccount.id));
    fireEvent.click(screen.getByRole("button", { name: "Remove from this desktop" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "OpenAI could not confirm revocation",
    );
    expect(disconnect).toHaveBeenCalledWith(browserAccount.id);
  });
});
