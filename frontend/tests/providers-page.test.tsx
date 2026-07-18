import { render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import ProvidersSettingsPage from "../app/dashboard/settings/providers/page";

vi.mock("@/lib/providers-api", () => ({
  listProviders: vi.fn(async () => [
    {
      id: "provider-1",
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
      metadata_json: {},
      created_at: "",
      updated_at: "",
      secrets: [],
      latest_health: null,
    },
    {
      id: "provider-2",
      tenant_id: "tenant-1",
      workspace_id: null,
      provider_type: "ollama",
      display_name: "Disabled Ollama",
      api_base_url: "http://127.0.0.1:11434",
      auth_mode: "local_no_key",
      enabled: false,
      is_local: true,
      supports_chat: true,
      supports_embeddings: true,
      supports_model_listing: true,
      supports_model_install: true,
      default_chat_model: null,
      default_embedding_model: null,
      timeout_seconds: 30,
      priority: 100,
      metadata_json: {},
      created_at: "",
      updated_at: "",
      secrets: [],
      latest_health: null,
    },
  ]),
  listAssignments: vi.fn(async () => []),
  listSupportedProviderTypes: vi.fn(async () => [
    {
      provider_type: "ollama",
      display_name: "Ollama",
      auth_modes: ["local_no_key"],
      supports_chat: true,
      supports_embeddings: true,
      supports_model_listing: true,
      supports_model_install: true,
      supports_account_linking: false,
      is_local: true,
    },
  ]),
  getOpenAIOAuthStatus: vi.fn(async () => ({
    available: false,
    connected: false,
    provider_type: "openai",
    message: "API key only",
  })),
  listProviderModels: vi.fn(async () => []),
  createProvider: vi.fn(),
  updateProvider: vi.fn(async (_id, payload) => ({
    id: _id,
    tenant_id: "tenant-1",
    workspace_id: null,
    provider_type: "ollama",
    display_name: "Ollama Local",
    api_base_url: "http://127.0.0.1:11434",
    auth_mode: "local_no_key",
    enabled: payload.enabled ?? true,
    is_local: true,
    supports_chat: true,
    supports_embeddings: true,
    supports_model_listing: true,
    supports_model_install: true,
    default_chat_model: payload.default_chat_model ?? null,
    default_embedding_model: payload.default_embedding_model ?? null,
    timeout_seconds: 30,
    priority: 100,
    metadata_json: {},
    created_at: "",
    updated_at: "",
    secrets: [],
    latest_health: null,
  })),
  testProvider: vi.fn(async () => ({
    provider_id: "provider-2",
    status: "healthy",
    latency_ms: 12,
    http_status: 200,
    error_code: null,
    error_message_redacted: null,
    metadata_json: {},
    checked_at: null,
  })),
  refreshProviderModels: vi.fn(async () => []),
  pullProviderModel: vi.fn(async () => ({ status: "accepted", message: "Model requested" })),
  createAssignment: vi.fn(async () => ({
    id: "assignment-1",
    tenant_id: "tenant-1",
    workspace_id: null,
    feature_scope: "chat",
    provider_config_id: "provider-1",
    model_name: null,
    enabled: true,
    priority: 100,
    created_at: "",
    updated_at: "",
  })),
  updateAssignment: vi.fn(async () => ({
    id: "assignment-1",
    tenant_id: "tenant-1",
    workspace_id: null,
    feature_scope: "chat",
    provider_config_id: "provider-1",
    model_name: null,
    enabled: true,
    priority: 100,
    created_at: "",
    updated_at: "",
  })),
  deleteProvider: vi.fn(async () => ({ provider_id: "provider-1", status: "disabled" })),
  disconnectProvider: vi.fn(async () => ({ provider_id: "provider-1", revoked_secret_count: 1 })),
  startOpenAIOAuth: vi.fn(async () => ({
    available: false,
    authorization_url: null,
    message: "API key only",
  })),
  rotateProviderSecret: vi.fn(async () => ({ provider_id: "provider-1", revoked_secret_count: 0 })),
}));

vi.mock("react-hot-toast", () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe("providers settings page", () => {
  it("renders the providers workspace shell", async () => {
    render(<ProvidersSettingsPage />);

    expect(await screen.findByText(/^Providers$/i)).toBeInTheDocument();
    expect(
      screen.getByText(/manage foundation models and runtime connectivity/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to settings/i })).toBeInTheDocument();
  });

  it("clears the loading state after providers resolve", async () => {
    render(<ProvidersSettingsPage />);

    await waitFor(() => {
      expect(screen.queryByText(/loading providers/i)).not.toBeInTheDocument();
    });
  });
});
