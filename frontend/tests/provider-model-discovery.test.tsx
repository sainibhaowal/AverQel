import { render, screen } from "@testing-library/react";

import ProviderModelsPanel from "../app/components/providers/ProviderModelsPanel";
import type { ProviderConfig, ProviderModel } from "../lib/providers-api";

const provider: ProviderConfig = {
  id: "provider-1",
  tenant_id: "tenant-1",
  workspace_id: null,
  provider_type: "lmstudio",
  display_name: "LM Studio Local",
  api_base_url: "http://127.0.0.1:1234/v1",
  auth_mode: "local_no_key",
  enabled: true,
  is_local: true,
  supports_chat: true,
  supports_embeddings: true,
  supports_reranking: true,
  supports_model_listing: true,
  supports_model_install: false,
  default_chat_model: "qwen2.5-coder-7b",
  default_embedding_model: "nomic-embed-text",
  default_reranker_model: "BAAI/bge-reranker-v2-m3",
  timeout_seconds: 30,
  priority: 100,
  metadata_json: { runtime: "lmstudio" },
  created_at: "",
  updated_at: "",
  secrets: [],
  latest_health: null,
};

const models: ProviderModel[] = [
  {
    id: "1",
    provider_config_id: "provider-1",
    model_name: "qwen2.5-coder-7b",
    model_kind: "chat",
    display_name: "Qwen 2.5 Coder 7B",
    context_window: 32768,
    capabilities_json: {
      runtime: "lmstudio",
      selection_only: true,
      supports_chat: true,
      supports_embeddings: false,
      install_supported: false,
    },
    is_available: true,
    last_seen_at: null,
  },
  {
    id: "3",
    provider_config_id: "provider-1",
    model_name: "BAAI/bge-reranker-v2-m3",
    model_kind: "reranker",
    display_name: "BGE Reranker v2 M3",
    context_window: 8192,
    capabilities_json: {
      runtime: "sentence-transformers-cross-encoder",
      supports_reranking: true,
      install_supported: false,
    },
    is_available: true,
    last_seen_at: null,
  },
  {
    id: "2",
    provider_config_id: "provider-1",
    model_name: "nomic-embed-text",
    model_kind: "embedding",
    display_name: "Nomic Embed Text",
    context_window: 8192,
    capabilities_json: {
      runtime: "lmstudio",
      selection_only: true,
      supports_chat: false,
      supports_embeddings: true,
      install_supported: false,
    },
    is_available: true,
    last_seen_at: null,
  },
];

describe("provider model discovery panel", () => {
  it("shows only chat-capable models in the chat view", () => {
    render(
      <ProviderModelsPanel
        activeServiceKind="chat"
        provider={provider}
        models={models}
        pullModelName=""
        onPullModelNameChange={() => {}}
        onRefresh={() => {}}
        onPull={() => {}}
        defaultModel={provider.default_chat_model || ""}
        onDefaultModelChange={() => {}}
      />,
    );

    expect(screen.getByText(/primary conversational assistant/i)).toBeInTheDocument();
    expect(screen.getAllByText(/qwen 2.5 coder 7b/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/nomic embed text/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/bge reranker v2 m3/i)).not.toBeInTheDocument();
  });

  it("shows only embedding models in the embedding view", () => {
    render(
      <ProviderModelsPanel
        activeServiceKind="embedding"
        provider={provider}
        models={models}
        pullModelName=""
        onPullModelNameChange={() => {}}
        onRefresh={() => {}}
        onPull={() => {}}
        defaultModel={provider.default_embedding_model || ""}
        onDefaultModelChange={() => {}}
      />,
    );

    expect(screen.getByText(/intelligence embedding interface/i)).toBeInTheDocument();
    expect(screen.getAllByText(/nomic embed text/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/qwen 2.5 coder 7b/i)).not.toBeInTheDocument();
  });
});
