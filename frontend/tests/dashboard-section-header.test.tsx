import { render, screen } from "@testing-library/react";
import { FileText } from "lucide-react";
import { describe, expect, it } from "vitest";

import DashboardSectionHeader from "../app/components/ui/DashboardSectionHeader";

describe("DashboardSectionHeader action layout", () => {
  it("places requested actions on a full-width row below the title", () => {
    const { container } = render(
      <DashboardSectionHeader
        title="Documents Hub"
        subtitle="Secure document ingestion and intelligence"
        icon={FileText}
        actionsLayout="below"
        actions={<button type="button">Add documents</button>}
      />,
    );

    const root = container.firstElementChild;
    const actions = screen.getByRole("button", { name: "Add documents" }).parentElement;

    expect(root).toHaveClass("flex-col");
    expect(root).not.toHaveClass("md:flex-row");
    expect(actions).toHaveClass("w-full", "justify-start", "sm:justify-end");
  });

  it("preserves the existing inline layout by default", () => {
    const { container } = render(
      <DashboardSectionHeader
        title="Settings"
        subtitle="Manage your workspace"
        icon={FileText}
        actions={<button type="button">Save</button>}
      />,
    );

    const root = container.firstElementChild;
    const actions = screen.getByRole("button", { name: "Save" }).parentElement;

    expect(root).toHaveClass("md:flex-row", "md:justify-between");
    expect(actions).not.toHaveClass("w-full");
  });
});
