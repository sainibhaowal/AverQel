import { render, screen } from "@testing-library/react";

import ProviderModelsPanel from "../app/components/providers/ProviderModelsPanel";
import type { ProviderConfig } from "../lib/providers-api";

const ollamaProvider: ProviderConfig = {
  id: "provider-ollama",
  tenant_id: "tenant-1",
  workspace_id: null,
  provider_type: "ollama",
  display_name: "Ollama Local",
  api_base_url: "http://127.0.0.1:11434",
  auth_mode: "local_no_key",
  enabled: true,
  is_local: true,
  supports_chat: true,
  supports_embeddings: true,
  supports_model_listing: true,
  supports_model_install: true,
  default_chat_model: null,
  default_embedding_model: null,
  timeout_seconds: 30,
  priority: 100,
  metadata_json: { runtime: "ollama" },
  created_at: "",
  updated_at: "",
  secrets: [],
  latest_health: null,
};

const lmStudioProvider: ProviderConfig = {
  ...ollamaProvider,
  id: "provider-lmstudio",
  provider_type: "lmstudio",
  display_name: "LM Studio Local",
  api_base_url: "http://127.0.0.1:1234/v1",
  supports_model_install: false,
  metadata_json: { runtime: "lmstudio" },
};

describe("provider model pull flow", () => {
  it("shows pull controls only for runtimes that officially support install", () => {
    const { rerender } = render(
      <ProviderModelsPanel
        activeServiceKind="chat"
        provider={ollamaProvider}
        models={[]}
        pullModelName=""
        onPullModelNameChange={() => {}}
        onRefresh={() => {}}
        onPull={() => {}}
        defaultModel=""
        onDefaultModelChange={() => {}}
      />,
    );

    expect(screen.getByRole("button", { name: /^pull$/i })).toBeInTheDocument();
    expect(screen.getByText(/runtime pull/i)).toBeInTheDocument();

    rerender(
      <ProviderModelsPanel
        activeServiceKind="chat"
        provider={lmStudioProvider}
        models={[]}
        pullModelName=""
        onPullModelNameChange={() => {}}
        onRefresh={() => {}}
        onPull={() => {}}
        defaultModel=""
        onDefaultModelChange={() => {}}
      />,
    );

    expect(screen.queryByRole("button", { name: /^pull$/i })).not.toBeInTheDocument();
  });
});
