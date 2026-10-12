import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider } from "../app/context/AuthContext";
import DeepSpaceChatClient from "../app/dashboard/deepspace/_components/DeepSpaceChatClient";

const listProvidersMock = vi.fn();
const listProviderModelsMock = vi.fn();
const refreshProviderModelsMock = vi.fn();
const listAssignmentsMock = vi.fn();

vi.mock("@/lib/providers-api", () => ({
  listProviders: (...args: unknown[]) => listProvidersMock(...args),
  listProviderModels: (...args: unknown[]) => listProviderModelsMock(...args),
  listAssignments: (...args: unknown[]) => listAssignmentsMock(...args),
  refreshProviderModels: (...args: unknown[]) => refreshProviderModelsMock(...args),
  createAssignment: vi.fn(),
  updateAssignment: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  fetchWithAuth: vi.fn(async () => ({ ok: true, json: async () => ({ messages: [] }) })),
  isDesktopEnvironment: () => false,
  getAccessTokenExpiry: () => null,
}));

vi.mock("../app/dashboard/deepspace/_hooks/useDeepSpaceStream", () => ({
  useDeepSpaceStream: () => ({ start: vi.fn(), cancel: vi.fn() }),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceComposer", () => ({
  default: ({
    modelName,
    contextLimit,
    selectedProviderId,
    availableModels,
  }: {
    modelName?: string | null;
    contextLimit?: number | null;
    selectedProviderId?: string | null;
    availableModels?: Array<{
      providerName?: string;
      providerType?: string;
      supportedReasoningEfforts?: string[];
    }>;
  }) => (
    <>
      <output data-testid="composer-model-state">
        {modelName ?? "no-model"}|{contextLimit ?? "no-context"}
      </output>
      <output data-testid="composer-provider-state">
        {availableModels?.[0]?.providerName ?? "no-provider-name"}|
        {availableModels?.[0]?.providerType ?? "no-provider-type"}|{selectedProviderId ?? "no-id"}
      </output>
      <output data-testid="composer-reasoning-state">
        {availableModels?.[0]?.supportedReasoningEfforts?.join(",") ?? "no-reasoning-levels"}
      </output>
    </>
  ),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceThread", () => ({
  default: () => null,
}));

vi.mock("../app/components/dashboard/ChatSidebar", () => ({ default: () => null }));
vi.mock("../app/dashboard/deepspace/_components/DeepSpaceScrollTracker", () => ({
  default: () => null,
}));

describe("DeepSpace composer model default", () => {
  beforeEach(() => {
    listProvidersMock.mockResolvedValue([
      {
        id: "provider-1",
        display_name: "Qwen Cloud",
        provider_type: "openai-compatible",
        enabled: true,
        supports_chat: true,
        default_chat_model: "qwen3-32b",
      },
    ]);
    listAssignmentsMock.mockResolvedValue([]);
    refreshProviderModelsMock.mockReset();
    refreshProviderModelsMock.mockResolvedValue([]);
    listProviderModelsMock.mockResolvedValue([
      {
        model_name: "qwen3-32b",
        display_name: "Qwen 3 32B",
        model_kind: "chat",
        is_available: true,
        context_window: 131072,
        capabilities_json: { context_window_source: "provider" },
      },
    ]);
  });

  it("uses the enabled provider default immediately for the composer context meter", async () => {
    render(
      <AuthProvider>
        <DeepSpaceChatClient activeConversationId={null} />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("composer-model-state")).toHaveTextContent("qwen3-32b|131072");
      expect(screen.getByTestId("composer-provider-state")).toHaveTextContent(
        "Qwen Cloud|openai-compatible|provider-1",
      );
    });
  });

  it("refreshes a selected model with no catalog timestamp and applies its returned effort levels", async () => {
    listProvidersMock.mockResolvedValue([
      {
        id: "provider-1",
        display_name: "Qwen Cloud",
        provider_type: "openai-compatible",
        enabled: true,
        supports_chat: true,
        supports_model_listing: true,
        default_chat_model: "qwen3-32b",
      },
    ]);
    listProviderModelsMock.mockResolvedValue([
      {
        model_name: "qwen3-32b",
        display_name: "Qwen 3 32B",
        model_kind: "chat",
        is_available: true,
        context_window: 131072,
        last_seen_at: null,
        capabilities_json: {
          reasoning_capabilities_known: true,
          supported_reasoning_efforts: ["medium"],
        },
      },
    ]);

    let resolveRefresh!: (models: Array<Record<string, unknown>>) => void;
    refreshProviderModelsMock.mockImplementation(
      () => new Promise((resolve) => (resolveRefresh = resolve)),
    );

    render(
      <AuthProvider>
        <DeepSpaceChatClient activeConversationId={null} />
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(refreshProviderModelsMock).toHaveBeenCalledWith("provider-1");
      expect(screen.getByTestId("composer-model-state")).toHaveTextContent("qwen3-32b|131072");
      expect(screen.getByTestId("composer-reasoning-state")).toHaveTextContent("medium");
    });

    await act(async () => {
      resolveRefresh([
        {
          model_name: "qwen3-32b",
          display_name: "Qwen 3 32B",
          model_kind: "chat",
          is_available: true,
          context_window: 131072,
          last_seen_at: new Date().toISOString(),
          capabilities_json: {
            reasoning_capabilities_known: true,
            supported_reasoning_efforts: ["low", "high"],
          },
        },
      ]);
    });

    await waitFor(() => {
      expect(screen.getByTestId("composer-reasoning-state")).toHaveTextContent("low,high");
    });
  });
});
