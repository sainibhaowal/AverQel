import { render, screen } from "@testing-library/react";

import DeepSpaceComposer from "../app/dashboard/deepspace/_components/DeepSpaceComposer";

describe("DeepSpaceComposer web search", () => {
  it("shows auto policy indicators instead of manual toggles", () => {
    render(
      <DeepSpaceComposer
        query="latest AI news"
        isStreaming={false}
        onQueryChange={() => {}}
        onSubmit={() => {}}
        onStop={() => {}}
      />,
    );

    expect(screen.getByText(/auto-review/i)).toBeInTheDocument();
    expect(screen.getByText(/runtime/i)).toBeInTheDocument();
    expect(() => screen.getByRole("button", { name: /web off/i })).toThrow();
  });
});
