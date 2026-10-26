import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import ProviderDeleteDialog from "../app/components/providers/ProviderDeleteDialog";

describe("provider destructive confirmation", () => {
  it("uses theme-aware surfaces and a readable destructive action", () => {
    render(
      <ProviderDeleteDialog
        open
        title="Terminate Connection"
        body="The provider will be disabled and can be resumed later."
        confirmLabel="Terminate Connection"
        onCancel={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    const heading = screen.getByRole("heading", { name: "Terminate Connection" });
    const panel = heading.closest(".provider-delete-dialog-panel");
    const confirm = screen.getByRole("button", { name: "Terminate Connection" });

    expect(panel).toHaveClass("bg-surface-0", "dark:bg-[rgba(10,14,11,0.96)]");
    expect(heading).toHaveClass("text-foreground");
    expect(confirm).toHaveClass(
      "bg-danger",
      "text-primary-foreground",
      "dark:bg-red-600",
      "dark:text-white",
    );
    expect(confirm).not.toHaveClass("text-white");
  });

  it("requires the confirmation dialog before destructive actions can run", () => {
    const onCancel = vi.fn();
    const onConfirm = vi.fn();

    const { rerender } = render(
      <ProviderDeleteDialog
        open={false}
        title="Delete provider"
        body="Deleting this provider is destructive."
        confirmLabel="Delete"
        onCancel={onCancel}
        onConfirm={onConfirm}
      />,
    );

    expect(screen.queryByRole("button", { name: /^delete$/i })).not.toBeInTheDocument();

    rerender(
      <ProviderDeleteDialog
        open
        title="Delete provider"
        body="Deleting this provider is destructive."
        confirmLabel="Delete"
        onCancel={onCancel}
        onConfirm={onConfirm}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });
});
