import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { vi } from "vitest";
import { listProviders, refreshProviderModels, type ProviderConfig } from "@/lib/providers-api";

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

  it("keeps the provider panel fixed and constrains both inventory views to scrolling", async () => {
    const previousWidth = window.innerWidth;
    const scrollTo = vi.spyOn(window, "scrollTo").mockImplementation(() => {});
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 540 });

    try {
      render(<ProvidersSettingsPage />);

      const inventoryHeading = await screen.findByRole("heading", {
        name: "Inventory",
        level: 3,
      });
      const panel = inventoryHeading.closest("aside");
      expect(panel).not.toBeNull();
      expect(panel).toHaveClass("providers-inventory-panel");
      expect(panel).toHaveClass("h-[min(46rem,calc(100dvh-8rem))]");
      expect(panel?.parentElement).toHaveClass("overflow-x-hidden", "overflow-y-auto");

      const inventoryToggle = within(panel!).getByRole("button", {
        name: /inventory contents/i,
      });
      expect(inventoryToggle).toHaveAttribute("aria-expanded", "true");

      const inventoryContent = await within(panel!).findByRole("region", {
        name: "Connected provider inventory",
      });
      expect(inventoryContent).toHaveClass(
        "flex-1",
        "min-h-0",
        "overflow-x-hidden",
        "overflow-y-auto",
      );
      expect(inventoryContent.querySelector(".scrollbar-thin")).toHaveClass(
        "overflow-x-hidden",
        "overflow-y-auto",
      );
      expect(inventoryContent.parentElement).toHaveClass(
        "flex",
        "flex-col",
        "flex-1",
        "min-h-0",
        "overflow-hidden",
      );

      fireEvent.click(inventoryToggle);
      expect(inventoryToggle).toHaveAttribute("aria-expanded", "false");
      expect(panel).toHaveClass("h-[min(46rem,calc(100dvh-8rem))]");

      fireEvent.click(inventoryToggle);
      expect(inventoryToggle).toHaveAttribute("aria-expanded", "true");

      fireEvent.click(within(panel!).getByRole("button", { name: "Browse provider families" }));

      expect(
        await within(panel!).findByRole("heading", { name: "Select Family", level: 3 }),
      ).toBeInTheDocument();
      expect(panel).toHaveClass("h-[min(46rem,calc(100dvh-8rem))]");
      const familyContent = within(panel!).getByRole("region", { name: "Provider families" });
      expect(familyContent).toHaveClass(
        "flex-1",
        "min-h-0",
        "overflow-x-hidden",
        "overflow-y-auto",
      );
      expect(familyContent.parentElement).toHaveClass(
        "flex",
        "flex-col",
        "flex-1",
        "min-h-0",
        "overflow-hidden",
      );
    } finally {
      Object.defineProperty(window, "innerWidth", {
        configurable: true,
        value: previousWidth,
      });
      scrollTo.mockRestore();
    }
  });

  it("keeps inventory open and avoids reloading models when resizing across the narrow breakpoint", async () => {
    const previousWidth = window.innerWidth;
    const responsiveProvider: ProviderConfig = {
      id: "provider-responsive",
      tenant_id: "tenant-1",
      workspace_id: null,
      provider_type: "ollama",
      display_name: "Responsive Ollama",
      api_base_url: "http://127.0.0.1:11434",
      auth_mode: "local_no_key",
      enabled: true,
      is_local: true,
      supports_chat: true,
      supports_embeddings: false,
      supports_reranking: false,
      supports_web_search: false,
      supports_model_listing: true,
      supports_model_install: true,
      default_chat_model: "llama3",
      default_embedding_model: null,
      default_reranker_model: null,
      timeout_seconds: 30,
      priority: 100,
      metadata_json: {},
      created_at: "",
      updated_at: "",
      secrets: [],
      latest_health: null,
    };
    vi.mocked(listProviders).mockResolvedValueOnce([responsiveProvider]);
    vi.mocked(refreshProviderModels).mockClear();
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 });
    const { unmount } = render(<ProvidersSettingsPage />);

    try {
      const inventoryHeading = await screen.findByRole("heading", {
        name: "Inventory",
        level: 3,
      });
      const panel = inventoryHeading.closest("aside");
      expect(panel).not.toBeNull();

      await waitFor(() =>
        expect(vi.mocked(refreshProviderModels)).toHaveBeenCalledWith("provider-responsive"),
      );
      const modelRefreshCallsAfterSelection = vi.mocked(refreshProviderModels).mock.calls.length;

      Object.defineProperty(window, "innerWidth", { configurable: true, value: 900 });
      fireEvent.resize(window);

      const inventoryToggle = await within(panel!).findByRole("button", {
        name: /inventory contents/i,
      });
      expect(inventoryToggle).toHaveAttribute("aria-expanded", "true");
      expect(
        within(panel!).getByRole("region", { name: "Connected provider inventory" }),
      ).toBeInTheDocument();

      Object.defineProperty(window, "innerWidth", { configurable: true, value: 760 });
      fireEvent.resize(window);
      Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 });
      fireEvent.resize(window);

      await waitFor(() => expect(panel).toHaveClass("min-h-0", "overflow-hidden"));
      expect(panel).not.toHaveClass("h-full");
      expect(
        within(panel!).getByRole("region", { name: "Connected provider inventory" }),
      ).toBeInTheDocument();
      expect(vi.mocked(refreshProviderModels)).toHaveBeenCalledTimes(
        modelRefreshCallsAfterSelection,
      );
    } finally {
      unmount();
      Object.defineProperty(window, "innerWidth", {
        configurable: true,
        value: previousWidth,
      });
    }
  });

  it("keeps the desktop inventory and family panel filling the available workspace", async () => {
    const previousWidth = window.innerWidth;
    const previousVisualViewport = window.visualViewport;
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 });
    Object.defineProperty(window, "visualViewport", { configurable: true, value: undefined });

    try {
      render(<ProvidersSettingsPage />);

      const inventoryHeading = await screen.findByRole("heading", {
        name: "Inventory",
        level: 3,
      });
      const panel = inventoryHeading.closest("aside");
      expect(panel).not.toBeNull();
      expect(panel).toHaveClass("providers-inventory-panel");
      expect(panel).toHaveClass("min-h-0", "overflow-hidden");
      expect(panel).not.toHaveClass("h-full");
      expect(panel?.parentElement?.querySelector(".providers-setup-panel")).toBeInTheDocument();
      expect(panel?.parentElement).toHaveClass(
        "h-full",
        "grid-rows-[minmax(0,1fr)]",
        "overflow-hidden",
      );
      expect(panel?.closest(".providers-page-enter")).toHaveClass("h-full", "min-h-0");

      fireEvent.click(within(panel!).getByRole("button", { name: "Browse provider families" }));
      expect(
        await within(panel!).findByRole("heading", { name: "Select Family", level: 3 }),
      ).toBeInTheDocument();
      expect(panel).toHaveClass("min-h-0", "overflow-hidden");
      expect(within(panel!).getByRole("region", { name: "Provider families" })).toHaveClass(
        "flex-1",
        "min-h-0",
        "overflow-x-hidden",
        "overflow-y-auto",
      );
    } finally {
      Object.defineProperty(window, "innerWidth", {
        configurable: true,
        value: previousWidth,
      });
      Object.defineProperty(window, "visualViewport", {
        configurable: true,
        value: previousVisualViewport,
      });
    }
  });
});
