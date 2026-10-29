import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ProviderDropdown from "../app/components/providers/ProviderDropdown";

describe("provider dropdown search shell", () => {
  it("keeps one rounded-square shell while preserving searchable options", () => {
    render(
      <ProviderDropdown
        label="Model"
        value=""
        placeholder="Choose a model"
        searchable
        searchPlaceholder="Search by model name, ID, context, or capability"
        onChange={vi.fn()}
        options={[
          { value: "mistral-small", label: "Mistral Small" },
          { value: "openai-mini", label: "OpenAI Mini" },
        ]}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Choose a model" }));

    const search = screen.getByRole("searchbox", {
      name: "Search by model name, ID, context, or capability",
    });
    const shell = search.parentElement;
    const listbox = screen.getByRole("listbox", { name: "Model" });

    expect(shell).toHaveClass("provider-dropdown-search-shell", "rounded-lg", "border");
    expect(search).toHaveClass("search-shell-input");

    fireEvent.change(search, { target: { value: "mistral" } });
    expect(within(listbox).getByRole("option", { name: "Mistral Small" })).toBeInTheDocument();
    expect(within(listbox).queryByRole("option", { name: "OpenAI Mini" })).not.toBeInTheDocument();
  });
});
