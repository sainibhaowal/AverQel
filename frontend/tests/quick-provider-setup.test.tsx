import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import QuickProviderSetup from "../app/components/onboarding/QuickProviderSetup";

const mocks = vi.hoisted(() => ({
  listSupportedProviderTypes: vi.fn(),
  previewProviderModels: vi.fn(),
  createProvider: vi.fn(),
}));

vi.mock("@/lib/providers-api", () => mocks);
vi.mock("@/app/components/providers/OpenAICodexLoginPanel", () => ({
  default: () => <div>Desktop Codex sign-in</div>,
}));

const openAi = {
  provider_type: "openai",
  display_name: "OpenAI API",
  auth_modes: ["api_key", "codex_desktop"],
  supports_chat: true,
  supports_embeddings: true,
  supports_reranking: false,
  supports_web_search: false,
  supports_model_listing: true,
  supports_model_install: false,
  supports_account_linking: false,
  is_local: false,
};

const larprouter = {
  ...openAi,
  provider_type: "larprouter",
  display_name: "LarpRouter",
  supports_embeddings: false,
};

afterEach(() => {
  mocks.listSupportedProviderTypes.mockReset();
  mocks.previewProviderModels.mockReset();
  mocks.createProvider.mockReset();
  Reflect.deleteProperty(window, "electron");
});

describe("QuickProviderSetup", () => {
  it("sets up LarpRouter with its OpenAI-compatible URL and discovered chat model", async () => {
    mocks.listSupportedProviderTypes.mockResolvedValue([openAi, larprouter]);
    mocks.previewProviderModels.mockResolvedValue([
      {
        id: null,
        provider_config_id: null,
        model_name: "claude-opus-4-7-1m",
        model_kind: "chat",
        display_name: "Claude Opus 4.7",
        context_window: null,
        capabilities_json: {},
        is_available: true,
        last_seen_at: null,
      },
    ]);
    mocks.createProvider.mockResolvedValue({
      display_name: "LarpRouter",
      default_chat_model: "claude-opus-4-7-1m",
    });
    const onConfigured = vi.fn();

    render(
      <QuickProviderSetup
        onConfigured={onConfigured}
        onOpenSettings={vi.fn()}
        onBusyChange={vi.fn()}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: /provider.*openai api/i }));
    fireEvent.click(await screen.findByRole("option", { name: "LarpRouter" }));
    fireEvent.change(screen.getByLabelText("API key"), {
      target: { value: "lrsk-test-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Find chat models" }));

    await screen.findByRole("option", { name: "Claude Opus 4.7" });
    expect(mocks.previewProviderModels).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_type: "larprouter",
        api_base_url: "https://larprouter.com/v1",
        supports_chat: true,
        supports_embeddings: false,
        supports_model_listing: true,
        api_key: "lrsk-test-key",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Save connection" }));

    await waitFor(() => expect(mocks.createProvider).toHaveBeenCalledOnce());
    expect(mocks.createProvider).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_type: "larprouter",
        display_name: "LarpRouter",
        api_base_url: "https://larprouter.com/v1",
        supports_chat: true,
        supports_embeddings: false,
        supports_model_listing: true,
        default_chat_model: "claude-opus-4-7-1m",
        api_key: "lrsk-test-key",
      }),
    );
    expect(onConfigured).toHaveBeenCalledWith("LarpRouter");
  });

  it("discovers a model and saves a named provider with that default model", async () => {
    mocks.listSupportedProviderTypes.mockResolvedValue([openAi]);
    mocks.previewProviderModels.mockResolvedValue([
      {
        id: null,
        provider_config_id: null,
        model_name: "gpt-example",
        model_kind: "chat",
        display_name: "GPT Example",
        context_window: null,
        capabilities_json: {},
        is_available: true,
        last_seen_at: null,
      },
    ]);
    mocks.createProvider.mockResolvedValue({
      display_name: "Work OpenAI",
      default_chat_model: "gpt-example",
    });
    const onConfigured = vi.fn();
    const onBusyChange = vi.fn();

    render(
      <QuickProviderSetup
        onConfigured={onConfigured}
        onOpenSettings={vi.fn()}
        onBusyChange={onBusyChange}
      />,
    );
    fireEvent.click(await screen.findByRole("button", { name: /provider.*openai api/i }));
    expect(await screen.findByRole("listbox", { name: "Provider" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "OpenAI API" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    fireEvent.change(screen.getByLabelText("Connection name"), {
      target: { value: "Work OpenAI" },
    });
    fireEvent.change(screen.getByLabelText("API key"), { target: { value: "secret-test-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Find chat models" }));

    await screen.findByRole("option", { name: "GPT Example" });
    fireEvent.click(screen.getByRole("button", { name: "Save connection" }));

    await waitFor(() => expect(mocks.createProvider).toHaveBeenCalledOnce());
    expect(mocks.createProvider).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_type: "openai",
        display_name: "Work OpenAI",
        auth_mode: "api_key",
        api_key: "secret-test-key",
        supports_chat: true,
        default_chat_model: "gpt-example",
      }),
    );
    expect(onConfigured).toHaveBeenCalledWith("Work OpenAI");
    expect(onBusyChange.mock.calls).toEqual([[true], [false]]);
    expect(await screen.findByRole("status")).toHaveTextContent("connected with gpt-example");
  });

  it("keeps local model connections disabled in the web app", async () => {
    mocks.listSupportedProviderTypes.mockResolvedValue([
      {
        ...openAi,
        provider_type: "ollama",
        display_name: "Ollama",
        auth_modes: ["local_no_key"],
        supports_embeddings: true,
        supports_model_install: true,
        is_local: true,
      },
    ]);

    render(
      <QuickProviderSetup onConfigured={vi.fn()} onOpenSettings={vi.fn()} onBusyChange={vi.fn()} />,
    );

    expect(
      await screen.findByText(/lm studio and ollama run on your computer through averqel desktop/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Runtime URL")).toBeDisabled();
  });

  it("shows local providers as desktop-only in the web picker", async () => {
    mocks.listSupportedProviderTypes.mockResolvedValue([
      openAi,
      {
        ...openAi,
        provider_type: "ollama",
        display_name: "Ollama",
        auth_modes: ["local_no_key"],
        is_local: true,
      },
    ]);

    render(
      <QuickProviderSetup onConfigured={vi.fn()} onOpenSettings={vi.fn()} onBusyChange={vi.fn()} />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /provider.*openai api/i }));
    const ollamaOption = screen.getByRole("option", { name: /ollama.*desktop app only/i });
    expect(ollamaOption).toBeDisabled();
    expect(ollamaOption).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("button", { name: /provider.*openai api/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("enables local setup in Electron and persists the desktop runtime target", async () => {
    Object.defineProperty(window, "electron", {
      configurable: true,
      value: { isElectron: true, codex: {}, localRuntime: {} },
    });
    const ollama = {
      ...openAi,
      provider_type: "ollama",
      display_name: "Ollama",
      auth_modes: ["local_no_key"],
      supports_embeddings: true,
      supports_model_install: true,
      is_local: true,
    };
    mocks.listSupportedProviderTypes.mockResolvedValue([ollama]);
    mocks.previewProviderModels.mockResolvedValue([
      {
        id: null,
        provider_config_id: null,
        model_name: "llama3.2",
        model_kind: "chat",
        display_name: "Llama 3.2",
        context_window: null,
        capabilities_json: {},
        is_available: true,
        last_seen_at: null,
      },
    ]);
    mocks.createProvider.mockResolvedValue({
      display_name: "Ollama",
      default_chat_model: "llama3.2",
    });

    render(
      <QuickProviderSetup onConfigured={vi.fn()} onOpenSettings={vi.fn()} onBusyChange={vi.fn()} />,
    );

    expect(await screen.findByLabelText("Runtime URL")).not.toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Find chat models" }));
    await screen.findByRole("option", { name: "Llama 3.2" });
    fireEvent.click(screen.getByRole("button", { name: "Save connection" }));

    await waitFor(() => expect(mocks.createProvider).toHaveBeenCalledOnce());
    expect(mocks.createProvider).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_type: "ollama",
        metadata_json: { runtime_target: "desktop", protocol: "desktop_local_runtime" },
      }),
    );
  });
});
