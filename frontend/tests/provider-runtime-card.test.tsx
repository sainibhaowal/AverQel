import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ProviderRuntimeCard from "../app/components/providers/ProviderRuntimeCard";
import type { ProviderConfig } from "../lib/providers-api";

const embeddingProvider: ProviderConfig = {
  id: "provider-embedding",
  tenant_id: "tenant-1",
  workspace_id: null,
  provider_type: "sentence-transformers",
  display_name: "AverQel Server Embeddings",
  api_base_url: null,
  auth_mode: "local_no_key",
  enabled: true,
  is_local: true,
  supports_chat: false,
  supports_embeddings: true,
  supports_model_listing: false,
  supports_model_install: false,
  default_chat_model: null,
  default_embedding_model: "BAAI/bge-small-en-v1.5",
  timeout_seconds: 30,
  priority: 100,
  metadata_json: {},
  created_at: "",
  updated_at: "",
  secrets: [],
  latest_health: null,
};

describe("provider runtime card", () => {
  it("stays compact while keeping its status and actions readable", () => {
    render(
      <ProviderRuntimeCard
        title="Embedding active"
        provider={embeddingProvider}
        onPing={vi.fn()}
        onDisconnect={vi.fn()}
      />,
    );

    const heading = screen.getByRole("heading", { name: "AverQel Server Embeddings" });
    const card = heading.closest(".providers-runtime-card") as HTMLElement | null;

    expect(card).toHaveClass("h-fit", "self-start", "gap-4");
    expect(card).toHaveTextContent("BAAI/bge-small-en-v1.5");
    expect(screen.getByText("Embedding active")).toHaveClass("font-bold", "text-foreground/75");
    expect(screen.getByText("BAAI/bge-small-en-v1.5")).toHaveClass(
      "font-medium",
      "text-foreground/75",
    );
    expect(within(card!).getByText("Unchecked")).toHaveClass("px-2", "py-0.5", "text-[10px]");
    expect(within(card!).getByRole("button", { name: /verify/i })).toHaveClass("py-2.5");
    expect(within(card!).getByRole("button", { name: /terminate/i })).toHaveClass("py-2.5");
  });
});
