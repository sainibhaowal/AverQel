import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import ProviderForm from "../app/components/providers/ProviderForm";
import type { ProviderCatalogEntry } from "../lib/providers-api";

vi.mock("../lib/providers-api", async () => {
  const actual = await vi.importActual("../lib/providers-api");
  return {
    ...actual,
    previewProviderModels: vi.fn().mockResolvedValue([]),
  };
});

describe("provider form validation", () => {
  it("submits a provider payload using the active catalog entry", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const catalogEntry: ProviderCatalogEntry = {
      provider_type: "openai",
      display_name: "OpenAI",
      auth_modes: ["api_key"],
      supports_chat: true,
      supports_embeddings: true,
      supports_model_listing: true,
      supports_model_install: false,
      supports_account_linking: false,
      is_local: false,
    };

    render(
      <ProviderForm
        catalogEntry={catalogEntry}
        provider={null}
        models={[]}
        kind="chat"
        saving={false}
        busyAction={null}
        onCancel={() => {}}
        onSubmit={onSubmit}
      />,
    );

    fireEvent.change(screen.getByRole("textbox"), {
      target: { value: "https://api.openai.com/v1" },
    });
    fireEvent.change(screen.getByPlaceholderText(/enter secret value/i), {
      target: { value: "sk-test-1234" },
    });
    fireEvent.click(screen.getByRole("button", { name: /link family/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        provider_type: "openai",
        display_name: "OpenAI",
        auth_mode: "api_key",
        api_base_url: "https://api.openai.com/v1",
        supports_chat: true,
        supports_embeddings: true,
        api_key: "sk-test-1234",
      }),
    );
  });
});
