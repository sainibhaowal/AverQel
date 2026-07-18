import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import ExecutionModeDropdown from "../app/dashboard/deepspace/_components/ExecutionModeDropdown";

function Harness() {
  const [mode, setMode] = useState<"auto_review" | "full_access">("auto_review");

  return <ExecutionModeDropdown value={mode} onChange={setMode} compact />;
}

describe("ExecutionModeDropdown", () => {
  it("renders the menu in a portal and allows mode switching", () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: /auto-review/i }));

    expect(screen.getByRole("menu")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("menuitemradio", { name: /full access/i }));

    expect(screen.getByRole("button", { name: /full access/i })).toBeInTheDocument();
  });
});
