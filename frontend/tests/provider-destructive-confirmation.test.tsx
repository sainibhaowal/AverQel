import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import ProviderDeleteDialog from "../app/components/providers/ProviderDeleteDialog";

describe("provider destructive confirmation", () => {
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
