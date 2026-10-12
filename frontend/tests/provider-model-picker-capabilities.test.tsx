import { fireEvent, render, screen, within } from "@testing-library/react";
import { vi } from "vitest";

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

  it("searches model IDs and selects the result without closing when the search is focused", () => {
    const onChange = vi.fn();
    render(
      <ProviderModelPicker
        label="Chat model"
        value=""
        models={models}
        onChange={onChange}
        kinds={["chat"]}
      />,
    );

    const trigger = screen.getByRole("button", { name: /select chat model/i });
    fireEvent.click(trigger);
    const search = screen.getByRole("searchbox", { name: /search by model name, id/i });
    fireEvent.click(search);
    fireEvent.change(search, { target: { value: "QWEN-CHAT" } });

    const optionList = screen.getByRole("listbox", { name: /chat model/i });
    const result = within(optionList).getByRole("option", { name: /qwen chat/i });
    expect(result).toBeInTheDocument();
    expect(
      within(optionList).queryByRole("option", { name: /nomic embed/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(result);

    expect(onChange).toHaveBeenCalledWith("qwen-chat");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("searches nested capability metadata and reports when there are no matches", () => {
    render(
      <ProviderModelPicker
        label="Embedding model"
        value=""
        models={models}
        onChange={() => {}}
        kinds={["embedding"]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /select embedding interface/i }));
    const search = screen.getByRole("searchbox", { name: /search by model name, id/i });
    const optionList = screen.getByRole("listbox", { name: /embedding model/i });
    fireEvent.change(search, { target: { value: "supports embeddings" } });
    expect(within(optionList).getByRole("option", { name: /nomic embed/i })).toBeInTheDocument();

    fireEvent.change(search, { target: { value: "not-a-real-model" } });
    expect(within(optionList).getByText(/no models match your search/i)).toBeInTheDocument();
  });

  it("lets custom endpoints use an exact model ID when discovery has no catalog", () => {
    const onChange = vi.fn();
    render(
      <ProviderModelPicker
        label="Chat model ID"
        value=""
        models={[]}
        onChange={onChange}
        kinds={["chat"]}
        allowCustomValue
        placeholder="Search or enter chat model ID"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /search or enter chat model id/i }));
    const search = screen.getByRole("searchbox", { name: /search by model name, id/i });
    fireEvent.change(search, { target: { value: "minimax/minimax-m2.5" } });

    const optionList = screen.getByRole("listbox", { name: /chat model id/i });
    fireEvent.click(within(optionList).getByRole("option", { name: /use exact id/i }));

    expect(onChange).toHaveBeenCalledWith("minimax/minimax-m2.5");
  });
});
