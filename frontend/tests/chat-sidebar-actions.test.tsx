import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ChatSidebar from "../app/components/dashboard/ChatSidebar";

const fetchWithAuthMock = vi.fn();
const promptMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.stubGlobal("prompt", promptMock);

describe("chat sidebar actions", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    promptMock.mockReset();
  });

  it("renames the active conversation from the sidebar", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            id: "conv-1",
            title: "Untitled Note",
            updated_at: "2026-04-19T00:29:00Z",
          },
        ],
      }),
    });
    promptMock.mockReturnValueOnce("Deep research plan");
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: "conv-1",
        title: "Deep research plan",
        updated_at: "2026-04-19T00:30:00Z",
      }),
    });

    render(
      <ChatSidebar
        endpointBase="/deepspace/chats"
        currentConversationId="conv-1"
        onSelectConversation={() => {}}
        onNewChat={() => {}}
      />,
    );

    expect(await screen.findByText("Untitled Note")).toBeInTheDocument();

    fireEvent.click(screen.getByTitle(/rename conversation/i));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/deepspace/chats/conv-1", {
        method: "PATCH",
        body: JSON.stringify({ title: "Deep research plan" }),
      });
    });
    expect(await screen.findByText("Deep research plan")).toBeInTheDocument();
  });

  it("shows selection mode and bulk deletes selected query conversations", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            id: "conv-1",
            title: "What are the findings?",
            updated_at: "2026-04-19T00:29:00Z",
          },
          {
            id: "conv-2",
            title: "How many docs do we have?",
            updated_at: "2026-04-19T00:20:00Z",
          },
        ],
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true });

    render(
      <ChatSidebar
        endpointBase="/chats"
        currentConversationId="conv-1"
        onSelectConversation={() => {}}
        onNewChat={() => {}}
      />,
    );

    expect(await screen.findByText("What are the findings?")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByText("What are the findings?"));
    fireEvent.click(screen.getByRole("button", { name: /delete selected \(1\)/i }));
    fireEvent.click(await screen.findByRole("button", { name: /delete conversations/i }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/chats/bulk-delete", {
        method: "POST",
        body: JSON.stringify({ conversation_ids: ["conv-1"] }),
      });
    });
  });
});
