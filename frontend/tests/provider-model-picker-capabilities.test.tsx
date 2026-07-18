import { fireEvent, render, screen } from "@testing-library/react";

import ProviderModelPicker from "../app/components/providers/ProviderModelPicker";
import type { ProviderModel } from "../lib/providers-api";

const models: ProviderModel[] = [
  {
    id: "chat-1",
    provider_config_id: "provider-1",
    model_name: "qwen-chat",
    model_kind: "chat",
    display_name: "Qwen Chat",
    context_window: 32768,
    capabilities_json: { runtime: "ollama" },
    is_available: true,
    last_seen_at: null,
  },
  {
    id: "embed-1",
    provider_config_id: "provider-1",
    model_name: "nomic-embed",
    model_kind: "embedding",
    display_name: "Nomic Embed",
    context_window: 8192,
    capabilities_json: { runtime: "ollama", supports_embeddings: true },
    is_available: true,
    last_seen_at: null,
  },
];

describe("provider model picker", () => {
  it("shows capability hints in option labels", () => {
    render(
      <ProviderModelPicker
        label="Default embedding model"
        value=""
        models={models}
        onChange={() => {}}
        kinds={["embedding"]}
        allowClear
      />,
    );

    expect(screen.getAllByLabelText(/default embedding model/i).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /not assigned/i }));
    expect(
      screen.getAllByText(/uses generic runtime fallback if available/i).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/ollama · 8k/i)).toBeInTheDocument();
  });
});
