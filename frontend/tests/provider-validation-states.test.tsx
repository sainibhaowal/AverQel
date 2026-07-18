import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import ProviderForm from "../app/components/providers/ProviderForm";
import type { ProviderCatalogEntry } from "../lib/providers-api";
import { previewProviderModels } from "../lib/providers-api";

vi.mock("../lib/providers-api", async () => {
  const actual = await vi.importActual("../lib/providers-api");
  return {
    ...actual,
    previewProviderModels: vi.fn().mockResolvedValue([]),
  };
});

const openAiCatalogEntry: ProviderCatalogEntry = {
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

const lmStudioCatalogEntry: ProviderCatalogEntry = {
  provider_type: "lmstudio",
  display_name: "LM Studio",
  auth_modes: ["local_no_key", "api_key"],
  supports_chat: true,
  supports_embeddings: true,
  supports_model_listing: true,
  supports_model_install: false,
  supports_account_linking: false,
  is_local: true,
};

const sentenceTransformersCatalogEntry: ProviderCatalogEntry = {
  provider_type: "sentence-transformers",
  display_name: "AverQel Server Embeddings",
  auth_modes: ["none"],
  supports_chat: false,
  supports_embeddings: true,
  supports_model_listing: true,
  supports_model_install: false,
  supports_account_linking: false,
  is_local: false,
};

const previewProviderModelsMock = vi.mocked(previewProviderModels);

describe("provider validation states", () => {
  afterEach(() => {
    previewProviderModelsMock.mockReset();
    previewProviderModelsMock.mockResolvedValue([]);
  });

  it("submits hosted providers with the entered API base URL", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <ProviderForm
        catalogEntry={openAiCatalogEntry}
        provider={null}
        models={[]}
        kind="chat"
        saving={false}
        busyAction={null}
        onCancel={() => {}}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "https://api.openai.com/v1" },
    });
    fireEvent.change(screen.getByPlaceholderText(/enter secret value/i), {
      target: { value: "sk-1234" },
    });
    fireEvent.click(screen.getByRole("button", { name: /link family/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_type: "openai",
        api_base_url: "https://api.openai.com/v1",
        auth_mode: "api_key",
      }),
    );
  });

  it("normalizes lmstudio root URLs to the v1 API base before submit", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <ProviderForm
        catalogEntry={lmStudioCatalogEntry}
        provider={null}
        models={[]}
        kind="chat"
        saving={false}
        busyAction={null}
        onCancel={() => {}}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "http://127.0.0.1:1234" },
    });
    fireEvent.click(screen.getByRole("button", { name: /link family/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_type: "lmstudio",
        api_base_url: "http://127.0.0.1:1234/v1",
      }),
    );
  });

  it("auto-loads provider models from a valid lmstudio endpoint before save", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    vi.useFakeTimers();
    previewProviderModelsMock.mockResolvedValue([
      {
        id: null,
        provider_config_id: null,
        model_name: "mistralai/ministral-3-3b",
        model_kind: "chat",
        display_name: "Ministral 3B",
        context_window: null,
        capabilities_json: {},
        is_available: true,
        last_seen_at: null,
      },
      {
        id: null,
        provider_config_id: null,
        model_name: "text-embedding-nomic-embed-text-v1.5",
        model_kind: "embedding",
        display_name: "Nomic Embed",
        context_window: null,
        capabilities_json: {},
        is_available: true,
        last_seen_at: null,
      },
    ]);

    render(
      <ProviderForm
        catalogEntry={lmStudioCatalogEntry}
        provider={null}
        models={[]}
        kind="chat"
        saving={false}
        busyAction={null}
        onCancel={() => {}}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "http://host.docker.internal:1234/v1" },
    });

    await act(async () => {
      vi.advanceTimersByTime(650);
      await Promise.resolve();
    });

    expect(previewProviderModelsMock).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_type: "lmstudio",
        api_base_url: "http://host.docker.internal:1234/v1",
        auth_mode: "local_no_key",
      }),
    );
    expect(screen.getByText(/2 models found/i)).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("does not preview models while the runtime URL is still invalid", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    vi.useFakeTimers();

    render(
      <ProviderForm
        catalogEntry={lmStudioCatalogEntry}
        provider={null}
        models={[]}
        kind="chat"
        saving={false}
        busyAction={null}
        onCancel={() => {}}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "host.docker.internal:1234" },
    });

    await act(async () => {
      vi.advanceTimersByTime(650);
      await Promise.resolve();
    });

    expect(previewProviderModelsMock).not.toHaveBeenCalled();
    expect(
      screen.getByText(/enter a valid http\(s\) runtime url to preview models\./i),
    ).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("strips invisible characters from pasted lmstudio URLs before preview", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    vi.useFakeTimers();

    render(
      <ProviderForm
        catalogEntry={lmStudioCatalogEntry}
        provider={null}
        models={[]}
        kind="chat"
        saving={false}
        busyAction={null}
        onCancel={() => {}}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "http://host.docker.internal:1234/v1\uFEFF" },
    });

    await act(async () => {
      vi.advanceTimersByTime(650);
      await Promise.resolve();
    });

    expect(previewProviderModelsMock).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_type: "lmstudio",
        api_base_url: "http://host.docker.internal:1234/v1",
      }),
    );
    vi.useRealTimers();
  });

  it("shows base URL guidance for local lmstudio runtimes", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <ProviderForm
        catalogEntry={lmStudioCatalogEntry}
        provider={null}
        models={[]}
        kind="chat"
        saving={false}
        busyAction={null}
        onCancel={() => {}}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.getByPlaceholderText("https://api.provider.ai/v1")).toBeInTheDocument();
    expect(screen.getByText(/managed chat runtime/i)).toBeInTheDocument();
  });

  it("auto-loads built-in server embedding models without requiring a base URL", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    vi.useFakeTimers();
    previewProviderModelsMock.mockResolvedValue([
      {
        id: null,
        provider_config_id: null,
        model_name: "BAAI/bge-small-en-v1.5",
        model_kind: "embedding",
        display_name: "BGE Small English v1.5",
        context_window: 512,
        capabilities_json: {},
        is_available: true,
        last_seen_at: null,
      },
      {
        id: null,
        provider_config_id: null,
        model_name: "intfloat/multilingual-e5-small",
        model_kind: "embedding",
        display_name: "Multilingual E5 Small",
        context_window: 512,
        capabilities_json: {},
        is_available: true,
        last_seen_at: null,
      },
    ]);

    render(
      <ProviderForm
        catalogEntry={sentenceTransformersCatalogEntry}
        provider={null}
        models={[]}
        kind="embedding"
        saving={false}
        busyAction={null}
        onCancel={() => {}}
        onSubmit={onSubmit}
      />,
    );

    await act(async () => {
      vi.advanceTimersByTime(650);
      await Promise.resolve();
    });

    expect(previewProviderModelsMock).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_type: "sentence-transformers",
        api_base_url: null,
        auth_mode: "none",
      }),
    );
    expect(screen.getByText(/managed runtime; no url needed\./i)).toBeInTheDocument();
    expect(screen.getByText(/2 models found/i)).toBeInTheDocument();
    vi.useRealTimers();
  });
});
