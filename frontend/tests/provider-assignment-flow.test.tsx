import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import ProviderAssignmentsEditor from "../app/components/providers/ProviderAssignmentsEditor";

describe("provider assignment flow", () => {
  it("lets an operator save a chat assignment with a compatible provider", () => {
    const onSave = vi.fn();

    render(
      <ProviderAssignmentsEditor
        assignments={[]}
        providers={[
          {
            id: "provider-1",
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
            default_chat_model: "gpt-4.1-mini",
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
          "provider-1": [
            {
              id: "model-1",
              provider_config_id: "provider-1",
              model_name: "gpt-4.1-mini",
              model_kind: "chat",
              display_name: "GPT 4.1 Mini",
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

    fireEvent.click(screen.getAllByRole("button", { name: /save/i })[0]);
    expect(onSave).toHaveBeenCalled();
  });
});
