import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import AppTooltipLayer from "../app/components/ui/AppTooltipLayer";

describe("app tooltip layer", () => {
  it("replaces native title tooltips with the shared accessible tooltip", async () => {
    const rendered = render(<AppTooltipLayer />);
    const trigger = document.createElement("button");
    trigger.title = "Open this secure file in Library";
    document.body.append(trigger);
    const labeledTrigger = document.createElement("button");
    labeledTrigger.textContent = "Open file";
    labeledTrigger.title = "Opens this file in the library";

    try {
      await waitFor(() => {
        expect(trigger).not.toHaveAttribute("title");
        expect(trigger).toHaveAttribute("data-averqel-tooltip", "Open this secure file in Library");
      });
      expect(trigger).toHaveAttribute("aria-label", "Open this secure file in Library");
      expect(trigger).not.toHaveAttribute("aria-description");

      fireEvent.focusIn(trigger);
      const tooltip = await screen.findByRole("tooltip");
      expect(tooltip).toHaveTextContent("Open this secure file in Library");
      expect(tooltip).toHaveClass("averqel-tooltip-surface");
      expect(trigger).toHaveAttribute("aria-describedby", "averqel-app-tooltip");

      fireEvent.focusOut(trigger);
      await waitFor(() => expect(screen.queryByRole("tooltip")).not.toBeInTheDocument());

      document.body.append(labeledTrigger);
      await waitFor(() => expect(labeledTrigger).not.toHaveAttribute("title"));
      expect(labeledTrigger).not.toHaveAttribute("aria-label");
      expect(labeledTrigger).toHaveAttribute("aria-description", "Opens this file in the library");
      labeledTrigger.remove();
    } finally {
      trigger.remove();
      labeledTrigger.remove();
      rendered.unmount();
    }
  });

  it("replaces iframe titles while preserving their accessible name", async () => {
    const rendered = render(<AppTooltipLayer />);
    const frame = document.createElement("iframe");
    frame.title = "PDF preview";
    document.body.append(frame);

    try {
      await new Promise((resolve) => setTimeout(resolve, 0));
      expect(frame).not.toHaveAttribute("title");
      expect(frame).toHaveAttribute("data-averqel-tooltip", "PDF preview");
      expect(frame).toHaveAttribute("aria-label", "PDF preview");
    } finally {
      frame.remove();
      rendered.unmount();
    }
  });
});
