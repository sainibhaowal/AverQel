import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DeepSpaceChatClient from "../app/dashboard/deepspace/_components/DeepSpaceChatClient";

const listProvidersMock = vi.fn();
const listProviderModelsMock = vi.fn();
const listAssignmentsMock = vi.fn();

vi.mock("@/lib/providers-api", () => ({
  listProviders: (...args: unknown[]) => listProvidersMock(...args),
  listProviderModels: (...args: unknown[]) => listProviderModelsMock(...args),
  listAssignments: (...args: unknown[]) => listAssignmentsMock(...args),
  refreshProviderModels: vi.fn(),
  createAssignment: vi.fn(),
  updateAssignment: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  fetchWithAuth: vi.fn(async () => ({ ok: true, json: async () => ({ messages: [] }) })),
}));

vi.mock("../app/dashboard/deepspace/_hooks/useDeepSpaceStream", () => ({
  useDeepSpaceStream: () => ({ start: vi.fn(), cancel: vi.fn() }),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceComposer", () => ({
  default: ({ modelName, contextLimit }: { modelName?: string | null; contextLimit?: number | null }) => (
    <output data-testid="composer-model-state">
      {modelName ?? "no-model"}|{contextLimit ?? "no-context"}
    </output>
  ),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceThread", () => ({
  default: () => null,
}));

vi.mock("../app/components/dashboard/ChatSidebar", () => ({ default: () => null }));
vi.mock("../app/dashboard/deepspace/_components/DeepSpaceScrollTracker", () => ({ default: () => null }));

describe("DeepSpace composer model default", () => {
  beforeEach(() => {
    listProvidersMock.mockResolvedValue([
      {
        id: "provider-1",
        enabled: true,
        supports_chat: true,
        default_chat_model: "qwen3-32b",
      },
    ]);
    listAssignmentsMock.mockResolvedValue([]);
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
    render(<DeepSpaceChatClient activeConversationId={null} />);

    await waitFor(() => {
      expect(screen.getByTestId("composer-model-state")).toHaveTextContent("qwen3-32b|131072");
    });
  });
});
