import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import RuntimePreferencesDropdown, {
  type RuntimePreferencesValue,
} from "../app/dashboard/deepspace/_components/RuntimePreferencesDropdown";

function Harness() {
  const [value, setValue] = useState<RuntimePreferencesValue>({
    planner_mode: "default",
    subagent_profile: "default",
    runtime_hooks_enabled: true,
    workspace_mode_enabled: true,
  });

  return (
    <RuntimePreferencesDropdown
      value={value}
      conversationScoped
      onChange={(changes) => setValue((current) => ({ ...current, ...changes }))}
    />
  );
}

describe("RuntimePreferencesDropdown", () => {
  it("renders in a portal and lets users update runtime controls", () => {
    render(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: /runtime/i }));

    expect(screen.getByRole("dialog", { name: /deepspace runtime controls/i })).toBeInTheDocument();

    // Click on the Structured segmented control button
    fireEvent.click(screen.getByRole("button", { name: /^structured$/i }));

    // Open subagent profile bias dropdown
    fireEvent.click(screen.getByRole("button", { name: /subagent profile bias/i }));
    // Select the Analysis option
    fireEvent.click(screen.getByRole("button", { name: /analysis/i }));

    // Toggle runtime hooks
    fireEvent.click(screen.getByText(/runtime hooks/i));
    // Toggle workspace code mode
    fireEvent.click(screen.getByText(/workspace code mode/i));

    // Verify correct selections are active
    expect(screen.getByRole("button", { name: /^structured$/i })).toHaveClass("text-slate-900");
    expect(screen.getByRole("button", { name: /subagent profile bias/i })).toHaveTextContent(
      /analysis/i,
    );
  });
});
