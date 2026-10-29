import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import RoundedSelect from "../app/components/ui/RoundedSelect";

const options = [
  { value: "original", label: "Export…" },
  { value: "pdf", label: "PDF" },
  { value: "markdown", label: "Markdown" },
];

describe("RoundedSelect", () => {
  it("opens a rounded animated listbox and updates an uncontrolled selection", () => {
    const onChange = vi.fn();
    render(
      <RoundedSelect
        label="Export file format"
        defaultValue="original"
        options={options}
        onChange={onChange}
      />,
    );

    const trigger = screen.getByRole("combobox", { name: "Export file format" });
    expect(trigger).toHaveClass("rounded-lg");
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(trigger);

    const listbox = screen.getByRole("listbox", { name: "Export file format" });
    expect(listbox).toHaveClass("rounded-2xl");
    expect(screen.getByRole("option", { name: "PDF" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("option", { name: "PDF" }));

    expect(onChange).toHaveBeenCalledWith("pdf");
    expect(trigger).toHaveTextContent("PDF");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
  });

  it("supports keyboard navigation and restores focus when Escape closes the menu", async () => {
    render(<RoundedSelect label="Format" value="original" options={options} onChange={vi.fn()} />);
    const trigger = screen.getByRole("combobox", { name: "Format" });

    fireEvent.keyDown(trigger, { key: "ArrowDown" });
    const selectedOption = screen.getByRole("option", { name: "Export…" });
    expect(selectedOption).toHaveFocus();
    fireEvent.keyDown(selectedOption, { key: "ArrowDown" });
    expect(screen.getByRole("option", { name: "PDF" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("option", { name: "PDF" }), { key: "m" });
    expect(screen.getByRole("option", { name: "Markdown" })).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(trigger).toHaveFocus();
    await waitFor(() => expect(screen.queryByRole("listbox")).not.toBeInTheDocument());
  });

  it("disables empty selectors and does not open disabled selectors", () => {
    const { rerender } = render(<RoundedSelect label="Empty" options={[]} onChange={vi.fn()} />);
    const emptyTrigger = screen.getByRole("combobox", { name: "Empty" });
    expect(emptyTrigger).toBeDisabled();
    fireEvent.click(emptyTrigger);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();

    rerender(<RoundedSelect label="Disabled" options={options} disabled onChange={vi.fn()} />);
    const disabledTrigger = screen.getByRole("combobox", { name: "Disabled" });
    expect(disabledTrigger).toBeDisabled();
    fireEvent.click(disabledTrigger);
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });
});
