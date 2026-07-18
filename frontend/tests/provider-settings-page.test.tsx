import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import ProviderForm from "../app/components/providers/ProviderForm";
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
  updateProvider: vi.fn(),
  testProvider: vi.fn(),
  refreshProviderModels: vi.fn(async () => []),
  pullProviderModel: vi.fn(),
  createAssignment: vi.fn(),
  updateAssignment: vi.fn(),
  deleteProvider: vi.fn(async () => ({ provider_id: "provider-1", status: "disabled" })),
  disconnectProvider: vi.fn(),
  startOpenAIOAuth: vi.fn(async () => ({
    available: false,
    authorization_url: null,
    message: "API key only",
  })),
  rotateProviderSecret: vi.fn(),
}));

vi.mock("react-hot-toast", () => ({
  default: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

describe("provider settings page", () => {
  it("renders the provider settings surface", async () => {
    render(<ProvidersSettingsPage />);

    expect(await screen.findByText(/^providers$/i)).toBeInTheDocument();
  });

  it("hides delete for built-in managed providers", async () => {
    vi.mocked(
      await import("@/lib/providers-api").then((module) => module.listProviders),
    ).mockResolvedValue([
      {
        id: "provider-managed",
        tenant_id: "tenant-1",
        workspace_id: null,
        provider_type: "sentence-transformers",
        display_name: "AverQel Server Embeddings",
        api_base_url: null,
        auth_mode: "none",
        enabled: true,
        is_local: false,
        supports_chat: false,
        supports_embeddings: true,
        supports_reranking: false,
        supports_model_listing: true,
        supports_model_install: false,
        default_chat_model: null,
        default_embedding_model: "BAAI/bge-small-en-v1.5",
        default_reranker_model: null,
        timeout_seconds: 30,
        priority: 100,
        metadata_json: { managed_by_averqel: true },
        created_at: "",
        updated_at: "",
        secrets: [],
        latest_health: null,
      },
    ]);

    render(<ProvidersSettingsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /embedding/i }));
    expect((await screen.findAllByText(/averqel server embeddings/i)).length).toBeGreaterThan(0);
    expect(screen.getByText(/managed runtime; no url needed/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
  });

  it("sends a PATCH-compatible payload when updating a provider", async () => {
    const onSubmit = vi.fn(async () => {});

    render(
      <ProviderForm
        catalogEntry={null}
        provider={{
          id: "provider-1",
          tenant_id: "tenant-1",
          workspace_id: null,
          provider_type: "lmstudio",
          display_name: "LM Studio",
          api_base_url: "http://127.0.0.1:1234/v1",
          auth_mode: "local_no_key",
          enabled: true,
          is_local: true,
          supports_chat: true,
          supports_embeddings: true,
          supports_reranking: false,
          supports_model_listing: true,
          supports_model_install: false,
          default_chat_model: "qwen2.5-coder",
          default_embedding_model: null,
          default_reranker_model: null,
          timeout_seconds: 30,
          priority: 100,
          metadata_json: {},
          created_at: "",
          updated_at: "",
          secrets: [],
          latest_health: null,
        }}
        models={[]}
        kind="chat"
        saving={false}
        busyAction={null}
        onCancel={() => {}}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /update connectivity/i }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(
        expect.not.objectContaining({
          provider_type: expect.anything(),
          auth_mode: expect.anything(),
          supports_chat: expect.anything(),
          supports_embeddings: expect.anything(),
          supports_reranking: expect.anything(),
          supports_model_listing: expect.anything(),
          supports_model_install: expect.anything(),
          is_local: expect.anything(),
        }),
      );
    });
  });
});
