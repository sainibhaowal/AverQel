import { render, screen } from "@testing-library/react";

import ProviderModelsPanel from "../app/components/providers/ProviderModelsPanel";

const noop = () => {};

describe("provider local runtime errors", () => {
  it("shows safe empty-state diagnostics for LM Studio and hides unsupported install actions", () => {
    render(
      <ProviderModelsPanel
        activeServiceKind="chat"
        provider={{
          id: "provider-lmstudio",
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
          latest_health: {
            status: "error",
            latency_ms: null,
            http_status: null,
            error_code: "PROVIDER_TEST_FAILED",
            error_message_redacted: "LM Studio is unreachable or no models are loaded.",
            metadata_json: {},
            checked_at: null,
          },
        }}
        models={[]}
        pullModelName=""
        onPullModelNameChange={noop}
        onRefresh={noop}
        onPull={noop}
        defaultModel=""
        onDefaultModelChange={noop}
      />,
    );

    expect(
      screen.getByText(/no chat models identified\. try synchronizing\./i),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /pull/i })).not.toBeInTheDocument();
  });
});
