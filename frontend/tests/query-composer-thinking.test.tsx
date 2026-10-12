import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

const fetchWithAuthMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

import QueryComposer from "../app/dashboard/query/_components/QueryComposer";

const composerDefaults = {
  query: "",
  searchMode: "hybrid" as const,
  selectedCollectionId: "",
  collectionOptions: [],
  collectionScopeLoading: false,
  isStreaming: false,
  filtersOpen: false,
  supportsThinking: false,
  thinkingEnabled: false,
  onQueryChange: () => {},
  onSearchModeChange: () => {},
  onCollectionChange: () => {},
  onToggleFilters: () => {},
  onThinkingChange: () => {},
  onSubmit: () => {},
  onStop: () => {},
};

describe("QueryComposer thinking toggle", () => {
  it("hides the think toggle when the active model does not support thinking", () => {
    render(
      <QueryComposer
        query=""
        searchMode="hybrid"
        selectedCollectionId=""
        collectionOptions={[]}
        collectionScopeLoading={false}
        isStreaming={false}
        filtersOpen={false}
        supportsThinking={false}
        thinkingEnabled={false}
        onQueryChange={() => {}}
        onSearchModeChange={() => {}}
        onCollectionChange={() => {}}
        onToggleFilters={() => {}}
        onThinkingChange={() => {}}
        onSubmit={() => {}}
        onStop={() => {}}
      />,
    );

    expect(screen.queryByText(/Think Off/i)).not.toBeInTheDocument();
  });

  it("toggles thinking when the active model supports it", () => {
    const onThinkingChange = vi.fn();

    render(
      <QueryComposer
        query=""
        searchMode="hybrid"
        selectedCollectionId=""
        collectionOptions={[]}
        collectionScopeLoading={false}
        isStreaming={false}
        filtersOpen={false}
        supportsThinking={true}
        thinkingEnabled={false}
        onQueryChange={() => {}}
        onSearchModeChange={() => {}}
        onCollectionChange={() => {}}
        onToggleFilters={() => {}}
        onThinkingChange={onThinkingChange}
        onSubmit={() => {}}
        onStop={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Think Off/i }));
    expect(onThinkingChange).toHaveBeenCalledWith(true);
  });

  it("shows adaptive retrieval depth instead of a manual top-k control", () => {
    render(
      <QueryComposer
        query=""
        searchMode="hybrid"
        selectedCollectionId=""
        collectionOptions={[]}
        collectionScopeLoading={false}
        isStreaming={false}
        filtersOpen={true}
        supportsThinking={false}
        thinkingEnabled={false}
        onQueryChange={() => {}}
        onSearchModeChange={() => {}}
        onCollectionChange={() => {}}
        onToggleFilters={() => {}}
        onThinkingChange={() => {}}
        onSubmit={() => {}}
        onStop={() => {}}
      />,
    );

    expect(screen.getByText(/^Retrieval Depth$/i)).toBeInTheDocument();
    expect(screen.getByText(/AVERQEL adjusts retrieval depth automatically/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Context Depth/i)).not.toBeInTheDocument();
  });
});

describe("QueryComposer model search and queue controls", () => {
  it("searches provider-grouped models and selects the matching provider model", () => {
    const onModelSelect = vi.fn();
    render(
      <QueryComposer
        {...composerDefaults}
        availableModels={[
          {
            providerId: "provider-nvidia",
            providerName: "NVIDIA",
            providerType: "openai-compatible",
            modelName: "nvidia/model-a",
            displayName: "Model A",
          },
          {
            providerId: "provider-openai",
            providerName: "OpenAI",
            providerType: "openai",
            modelName: "gpt-model-b",
            displayName: "Model B",
          },
        ]}
        onModelSelect={onModelSelect}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Select Model/i }));
    fireEvent.change(screen.getByRole("searchbox", { name: "Search models" }), {
      target: { value: "nvidia" },
    });

    expect(screen.getByText("NVIDIA")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Model A" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Model B" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Model A" }));
    expect(onModelSelect).toHaveBeenCalledWith("provider-nvidia", "nvidia/model-a");
  });

  it("shows queued prompts and exposes pause and per-item removal controls", () => {
    const onToggleQueuePaused = vi.fn();
    const onRemoveQueueItem = vi.fn();
    render(
      <QueryComposer
        {...composerDefaults}
        isStreaming
        queueItems={[
          {
            id: "queued-1",
            query: "Compare these policies",
            attachments: [{ id: "doc-1", name: "policy.pdf" }],
          },
        ]}
        queuePaused={false}
        onToggleQueuePaused={onToggleQueuePaused}
        onRemoveQueueItem={onRemoveQueueItem}
      />,
    );

    expect(screen.getByText("1 queued query")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /1 queued query/i }));
    fireEvent.click(screen.getByRole("button", { name: "Pause query queue" }));
    expect(onToggleQueuePaused).toHaveBeenCalledOnce();
    expect(screen.getByText("Compare these policies")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove queued query 1" }));
    expect(onRemoveQueueItem).toHaveBeenCalledWith("queued-1");
  });

  it("forwards selected files to the Documents Hub upload handler", () => {
    const onFilesSelected = vi.fn();
    render(<QueryComposer {...composerDefaults} onFilesSelected={onFilesSelected} />);
    const file = new File(["source text"], "source.txt", { type: "text/plain" });

    fireEvent.change(screen.getByLabelText("Choose documents to attach"), {
      target: { files: [file] },
    });

    expect(onFilesSelected).toHaveBeenCalledOnce();
    expect(onFilesSelected.mock.calls[0][0]?.[0]).toBe(file);
  });

  it("lets users attach an already-indexed Documents Hub file directly", async () => {
    const document = {
      document_id: "existing-sales-table",
      filename: "legacy-sales.csv",
      size_bytes: 128,
      tabular: true,
    };
    const onExistingDocumentSelect = vi.fn();
    fetchWithAuthMock.mockResolvedValue({
      ok: true,
      json: async () => ({ items: [document], total: 1 }),
    });

    render(
      <QueryComposer {...composerDefaults} onExistingDocumentSelect={onExistingDocumentSelect} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Choose existing Documents Hub files" }));
    fireEvent.click(await screen.findByRole("button", { name: /legacy-sales\.csv/ }));

    expect(onExistingDocumentSelect).toHaveBeenCalledWith(document);
  });
});
