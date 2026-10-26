import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const fetchWithAuthMock = vi.fn();

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

import DeepSpaceSchedulesPanel from "../app/dashboard/deepspace/_components/DeepSpaceSchedulesPanel";

describe("DeepSpaceSchedulesPanel tab lifecycle", () => {
  it("refreshes quietly when returning to the panel", async () => {
    fetchWithAuthMock.mockResolvedValue({ ok: true, json: async () => [] });
    const view = render(<DeepSpaceSchedulesPanel conversationId="conversation-1" isPanelActive />);

    await waitFor(() => expect(fetchWithAuthMock).toHaveBeenCalledTimes(1));
    expect(screen.queryByRole("status", { name: /loading scheduled work/i })).toBeNull();

    view.rerender(
      <DeepSpaceSchedulesPanel conversationId="conversation-1" isPanelActive={false} />,
    );
    view.rerender(<DeepSpaceSchedulesPanel conversationId="conversation-1" isPanelActive />);

    await waitFor(() => expect(fetchWithAuthMock).toHaveBeenCalledTimes(2));
    expect(screen.queryByRole("status", { name: /loading scheduled work/i })).toBeNull();
  });
});
