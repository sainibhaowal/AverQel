import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import QueryComposer from "../app/dashboard/query/_components/QueryComposer";

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
