import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";

import ProviderForm from "../app/components/providers/ProviderForm";
import {
  previewProviderModels,
  type ProviderCatalogEntry,
  type ProviderConfig,
  type ProviderModel,
} from "../lib/providers-api";

vi.mock("../lib/providers-api", async () => {
  const actual = await vi.importActual("../lib/providers-api");
  return {
    ...actual,
    previewProviderModels: vi.fn().mockResolvedValue([]),
  };
});

describe("provider form validation", () => {
  it("uses LarpRouter defaults, discovers chat models, and submits its API key", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const discoveredModel: ProviderModel = {
      id: null,
      provider_config_id: null,
      model_name: "claude-opus-4-7-1m",
      model_kind: "chat",
      display_name: "Claude Opus 4.7",
      context_window: 1_000_000,
      capabilities_json: {},
      is_available: true,
      last_seen_at: null,
    };
    vi.mocked(previewProviderModels).mockClear().mockResolvedValue([discoveredModel]);
    const catalogEntry: ProviderCatalogEntry = {
      provider_type: "larprouter",
      display_name: "LarpRouter",
      auth_modes: ["api_key"],
      supports_chat: true,
      supports_embeddings: false,
      supports_model_listing: true,
      supports_model_install: false,
      supports_account_linking: false,
      is_local: false,
    };

    render(
      <ProviderForm
        catalogEntry={catalogEntry}
        provider={null}
        models={[]}
        kind="chat"
        saving={false}
        busyAction={null}
        onCancel={() => {}}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByDisplayValue("https://larprouter.com/v1")).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/enter secret value/i), {
      target: { value: "lrsk-test-key" },
    });
    await waitFor(() =>
      expect(previewProviderModels).toHaveBeenCalledWith(
        expect.objectContaining({
          provider_type: "larprouter",
          api_base_url: "https://larprouter.com/v1",
          supports_chat: true,
          supports_embeddings: false,
          supports_model_listing: true,
          api_key: "lrsk-test-key",
        }),
      ),
    );

    await screen.findByText("1 models found");
    fireEvent.click(screen.getByRole("button", { name: "Not Assigned" }));
    const modelListbox = screen.getByRole("listbox", { name: "Select chat model" });
    fireEvent.click(within(modelListbox).getByRole("option", { name: /claude opus 4\.7/i }));
    fireEvent.click(screen.getByRole("button", { name: /link family/i }));

    expect(onSubmit).toHaveBeenCalledWith(
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
  });

  it("submits a provider payload using the active catalog entry", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const catalogEntry: ProviderCatalogEntry = {
      provider_type: "openai",
      display_name: "OpenAI",
      auth_modes: ["api_key"],
      supports_chat: true,
      supports_embeddings: true,
      supports_model_listing: true,
      supports_model_install: false,
      supports_account_linking: false,
      is_local: false,
    };

    await act(async () => {
      render(
        <ProviderForm
          catalogEntry={catalogEntry}
          provider={null}
          models={[]}
          kind="chat"
          saving={false}
          busyAction={null}
          onCancel={() => {}}
          onSubmit={onSubmit}
        />,
      );
      await Promise.resolve();
    });

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "https://api.openai.com/v1" },
    });
    fireEvent.change(screen.getByPlaceholderText(/enter secret value/i), {
      target: { value: "sk-test-1234" },
    });
    fireEvent.click(screen.getByRole("button", { name: /link family/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_type: "openai",
        display_name: "OpenAI",
        auth_mode: "api_key",
        api_base_url: "https://api.openai.com/v1",
        supports_chat: true,
        supports_embeddings: true,
        api_key: "sk-test-1234",
      }),
    );
  });

  it("uses a directional sweep for the waiting-for-token state", async () => {
    const catalogEntry: ProviderCatalogEntry = {
      provider_type: "openai",
      display_name: "OpenAI",
      auth_modes: ["api_key"],
      supports_chat: true,
      supports_embeddings: true,
      supports_model_listing: true,
      supports_model_install: false,
      supports_account_linking: false,
      is_local: false,
    };

    render(
      <ProviderForm
        catalogEntry={catalogEntry}
        provider={null}
        models={[]}
        kind="chat"
        saving={false}
        busyAction={null}
        onCancel={() => {}}
        onSubmit={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const badge = await screen.findByText(/waiting for token/i);
    expect(badge).toHaveClass("waiting-token-sweep");
    expect(badge).not.toHaveClass("animate-pulse");
  });

  it("discovers Cline models and allows selecting a discovered model", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const discoveredModel: ProviderModel = {
      id: null,
      provider_config_id: null,
      model_name: "anthropic/claude-sonnet-4-6",
      model_kind: "chat",
      display_name: "Claude Sonnet 4.6",
      context_window: 200000,
      capabilities_json: {},
      is_available: true,
      last_seen_at: null,
    };
    vi.mocked(previewProviderModels).mockClear().mockResolvedValue([discoveredModel]);
    const catalogEntry: ProviderCatalogEntry = {
      provider_type: "cline",
      display_name: "Cline API",
      auth_modes: ["api_key"],
      supports_chat: true,
      supports_embeddings: false,
      supports_model_listing: true,
      supports_model_install: false,
      supports_account_linking: false,
      is_local: false,
    };

    await act(async () => {
      render(
        <ProviderForm
          catalogEntry={catalogEntry}
          provider={null}
          models={[]}
          kind="chat"
          saving={false}
          busyAction={null}
          onCancel={() => {}}
          onSubmit={onSubmit}
        />,
      );
      await Promise.resolve();
    });

    expect(screen.getByDisplayValue("https://api.cline.bot/api/v1")).toBeInTheDocument();
    expect(screen.getByText(/search cline's model catalog by name or id/i)).toBeInTheDocument();
    expect(screen.getByText(/model access is checked only by a chat request/i)).toBeInTheDocument();
    await waitFor(() =>
      expect(previewProviderModels).toHaveBeenCalledWith(
        expect.objectContaining({
          provider_type: "cline",
          api_base_url: "https://api.cline.bot/api/v1",
          supports_model_listing: true,
          api_key: null,
        }),
      ),
    );

    const modelSelect = screen.getByLabelText("Chat model ID");
    await waitFor(() =>
      expect(
        within(modelSelect).getByRole("option", { name: /claude sonnet 4\.6/i }),
      ).toBeInTheDocument(),
    );
    fireEvent.change(modelSelect, {
      target: { value: discoveredModel.model_name },
    });
    expect(screen.getByRole("button", { name: /claude sonnet 4\.6/i })).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText(/enter secret value/i), {
      target: { value: "cline-test-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: /link family/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_type: "cline",
        supports_model_listing: true,
        supports_embeddings: false,
        default_chat_model: "anthropic/claude-sonnet-4-6",
        api_key: "cline-test-key",
      }),
    );
  });

  it("explains that a reachable Cline catalog does not verify chat access", async () => {
    const provider: ProviderConfig = {
      id: "cline-provider",
      tenant_id: "tenant",
      workspace_id: null,
      provider_type: "cline",
      display_name: "Cline API",
      api_base_url: "https://api.cline.bot/api/v1",
      auth_mode: "api_key",
      enabled: true,
      is_local: false,
      supports_chat: true,
      supports_embeddings: false,
      supports_reranking: false,
      supports_web_search: false,
      supports_model_listing: true,
      supports_model_install: false,
      default_chat_model: "anthropic/claude-sonnet-4-6",
      default_embedding_model: null,
      timeout_seconds: 30,
      priority: 100,
      metadata_json: {},
      created_at: "2026-10-09T00:00:00Z",
      updated_at: "2026-10-09T00:00:00Z",
      secrets: [],
      latest_health: {
        status: "degraded",
        latency_ms: 100,
        http_status: null,
        error_code: "chat_access_not_verified",
        error_message_redacted: "Cline's public catalog is reachable.",
        metadata_json: {
          listing: "public_catalog",
          chat_probe: "not_run",
          model_count: 469,
        },
        checked_at: "2026-10-09T00:00:00Z",
      },
    };

    await act(async () => {
      render(
        <ProviderForm
          catalogEntry={null}
          provider={provider}
          models={[]}
          kind="chat"
          saving={false}
          busyAction={null}
          onCancel={() => {}}
          onSubmit={vi.fn().mockResolvedValue(undefined)}
        />,
      );
      await Promise.resolve();
    });

    expect(screen.getByText("Degraded")).toBeInTheDocument();
    expect(screen.getByText("Catalog reachable; chat access not verified.")).toBeInTheDocument();
  });

  it("preserves the connected Codex model's reasoning levels when saving", async () => {
    const account: ElectronCodexAccount = {
      id: "0123456789abcdef0123456789abcdef",
      email: null,
      name: "Codex CLI ChatGPT login",
      connected: true,
      source: "codex_cli",
    };
    const model: ElectronCodexModel = {
      id: "gpt-5.6-luna",
      name: "GPT-5.6 Luna",
      kind: "chat",
      supportedReasoningEfforts: ["low", "medium", "high", "very_high", "extreme_high"],
    };
    const provider: ProviderConfig = {
      id: "codex-provider",
      tenant_id: "tenant",
      workspace_id: null,
      provider_type: "openai",
      display_name: "OpenAI Codex",
      api_base_url: null,
      auth_mode: "codex_desktop",
      enabled: true,
      is_local: false,
      supports_chat: true,
      supports_embeddings: false,
      supports_reranking: false,
      supports_web_search: false,
      supports_model_listing: true,
      supports_model_install: false,
      default_chat_model: model.id,
      default_embedding_model: null,
      timeout_seconds: 30,
      priority: 100,
      metadata_json: {
        codex_desktop: {
          account_id: account.id,
          models: [{ id: model.id, name: model.name }],
        },
      },
      created_at: "2026-10-09T00:00:00Z",
      updated_at: "2026-10-09T00:00:00Z",
      secrets: [],
      latest_health: null,
    };
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const status = vi.fn().mockResolvedValue({
      available: true,
      accounts: [account],
    });
    const models = vi.fn().mockResolvedValue([model]);
    Object.defineProperty(window, "electron", {
      configurable: true,
      value: {
        isElectron: true,
        codex: { status, models, connect: vi.fn(), disconnect: vi.fn() },
      },
    });

    render(
      <ProviderForm
        catalogEntry={null}
        provider={provider}
        models={[]}
        kind="chat"
        saving={false}
        busyAction={null}
        onCancel={() => {}}
        onSubmit={onSubmit}
      />,
    );

    await waitFor(() => expect(models).toHaveBeenCalledWith(account.id));
    fireEvent.click(screen.getByRole("button", { name: /update connectivity/i }));

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          metadata_json: {
            codex_desktop: {
              account_id: account.id,
              models: [
                {
                  id: model.id,
                  name: model.name,
                  supported_reasoning_efforts: model.supportedReasoningEfforts,
                },
              ],
            },
          },
        }),
      ),
    );
    delete window.electron;
  });
});
