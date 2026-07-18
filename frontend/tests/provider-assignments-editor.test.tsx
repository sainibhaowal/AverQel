import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import ProviderAssignmentsEditor from "../app/components/providers/ProviderAssignmentsEditor";

describe("provider assignments editor", () => {
  it("filters providers by feature capability and saves a scope", () => {
    const onSave = vi.fn();

    render(
      <ProviderAssignmentsEditor
        assignments={[]}
        providers={[
          {
            id: "chat-provider",
            tenant_id: "tenant-1",
            workspace_id: null,
            provider_type: "openai",
            display_name: "Chat Provider",
            api_base_url: null,
            auth_mode: "api_key",
            enabled: true,
            is_local: false,
            supports_chat: true,
            supports_embeddings: false,
            supports_model_listing: true,
            supports_model_install: false,
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
            id: "embed-provider",
            tenant_id: "tenant-1",
            workspace_id: null,
            provider_type: "custom",
            display_name: "Embedding Provider",
            api_base_url: null,
            auth_mode: "api_key",
            enabled: true,
            is_local: false,
            supports_chat: false,
            supports_embeddings: true,
            supports_model_listing: true,
            supports_model_install: false,
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
        ]}
        modelsByProvider={{
          "chat-provider": [
            {
              id: null,
              provider_config_id: null,
              model_name: "gpt-4.1",
              model_kind: "chat",
              display_name: null,
              context_window: null,
              capabilities_json: {},
              is_available: true,
              last_seen_at: null,
            },
            {
              id: null,
              provider_config_id: null,
              model_name: "text-embedding-3-large",
              model_kind: "embedding",
              display_name: null,
              context_window: null,
              capabilities_json: {},
              is_available: true,
              last_seen_at: null,
            },
          ],
          "embed-provider": [
            {
              id: null,
              provider_config_id: null,
              model_name: "text-embedding-3-large",
              model_kind: "embedding",
              display_name: null,
              context_window: null,
              capabilities_json: {},
              is_available: true,
              last_seen_at: null,
            },
            {
              id: null,
              provider_config_id: null,
              model_name: "gpt-4.1-mini",
              model_kind: "chat",
              display_name: null,
              context_window: null,
              capabilities_json: {},
              is_available: true,
              last_seen_at: null,
            },
          ],
        }}
        onSave={onSave}
      />,
    );

    expect(screen.getAllByRole("option", { name: /chat provider/i }).length).toBeGreaterThan(0);
    expect(screen.queryAllByRole("option", { name: /embedding provider/i }).length).toBeGreaterThan(
      0,
    );
    expect(screen.queryAllByRole("option", { name: /gpt-4\.1-mini/i }).length).toBe(0);

    fireEvent.click(screen.getAllByRole("button", { name: /save/i })[0]);
    expect(onSave).toHaveBeenCalled();
  });
});
