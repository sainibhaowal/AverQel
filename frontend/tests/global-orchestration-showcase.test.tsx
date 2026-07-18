import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("framer-motion", () => ({
  motion: {
    div: ({ children, ...props }: { children?: ReactNode; [key: string]: unknown }) => {
      const domProps = { ...props };
      delete domProps.initial;
      delete domProps.whileInView;
      delete domProps.viewport;
      delete domProps.transition;
      delete domProps.animate;
      return <div {...domProps}>{children}</div>;
    },
  },
}));

import GlobalOrchestrationShowcase from "../app/components/marketing/GlobalOrchestrationShowcase";

describe("GlobalOrchestrationShowcase", () => {
  it("renders the global orchestration marketing section", () => {
    render(<GlobalOrchestrationShowcase />);

    expect(
      screen.getByText(/One.*mission brain for chat, subagents, proactive work, and connectors\./i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Open Orchestration/i)).toBeInTheDocument();
    expect(screen.getByText(/Read the Architecture/i)).toBeInTheDocument();
  });
});
