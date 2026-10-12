import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import ProviderListTable from "../app/components/providers/ProviderListTable";
import type { ProviderConfig } from "../lib/providers-api";

const provider: ProviderConfig = {
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
};

describe("provider list table", () => {
  it("aligns the hosted badge, selected marker, and remove button in the card header", () => {
    render(
      <ProviderListTable
        activeServiceKind="all"
        providers={[{ ...provider, is_local: false }]}
        selectedProviderId={provider.id}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        countLabel="ALL"
      />,
    );

    const hostedBadge = screen.getByText("Hosted");
    expect(hostedBadge.parentElement).toHaveClass("flex-row", "items-center");
    expect(hostedBadge.parentElement?.querySelector("svg")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove Ollama Local" })).toHaveClass("top-5");
  });

  it("shows the remove tooltip above the list clipping layer and preserves card selection", async () => {
    const onDelete = vi.fn();
    const onSelect = vi.fn();

    render(
      <ProviderListTable
        activeServiceKind="all"
        providers={[provider]}
        selectedProviderId={null}
        onSelect={onSelect}
        onDelete={onDelete}
        countLabel="ALL"
      />,
    );

    const removeButton = screen.getByRole("button", { name: "Remove Ollama Local" });
    expect(removeButton).toHaveClass("h-8", "w-8");
    fireEvent.focus(removeButton);

    const tooltip = await screen.findByRole("tooltip");
    expect(tooltip).toHaveTextContent("Remove connection");
    expect(tooltip).toHaveClass("fixed", "z-[10000]");

    fireEvent.click(removeButton);

    expect(onDelete).toHaveBeenCalledWith(provider);
    expect(onSelect).not.toHaveBeenCalled();
  });
});
