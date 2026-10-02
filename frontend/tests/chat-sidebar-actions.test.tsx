import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ChatSidebar from "../app/components/dashboard/ChatSidebar";

const fetchWithAuthMock = vi.fn();
const promptMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.mock("@/app/components/ui/AverQelDialogHost", () => ({
  averqelConfirm: vi.fn().mockResolvedValue(true),
  averqelPrompt: (...args: unknown[]) => promptMock(...args),
  averqelAlert: vi.fn().mockResolvedValue(undefined),
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

  it("lets a conversation owner pin retention protection without sending admin-only fields", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            id: "conv-1",
            title: "Retention-safe conversation",
            updated_at: "2026-04-19T00:29:00Z",
          },
        ],
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        pinned: false,
        legal_hold: false,
        admin_exempt: false,
        protection_reason: null,
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });

    render(
      <ChatSidebar
        endpointBase="/deepspace/chats"
        currentConversationId="conv-1"
        onSelectConversation={() => {}}
        onNewChat={() => {}}
        enableRetentionControls
      />,
    );

    expect(await screen.findByText("Retention-safe conversation")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /retention protection for retention-safe/i }),
    );
    expect(await screen.findByRole("dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/pin this conversation/i));
    fireEvent.click(screen.getByRole("button", { name: /save protection/i }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        "/deepspace/chats/conv-1/retention/protection",
        { method: "PATCH", body: JSON.stringify({ pinned: true }) },
      );
    });
    expect(screen.queryByLabelText(/legal hold/i)).not.toBeInTheDocument();
  });

  it("shows legal-hold and administrator-exemption controls only to tenant admins", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [{ id: "conv-1", title: "Admin retention", updated_at: "2026-04-19T00:29:00Z" }],
      }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        pinned: false,
        legal_hold: false,
        admin_exempt: false,
        protection_reason: null,
      }),
    });

    render(
      <ChatSidebar
        endpointBase="/deepspace/chats"
        currentConversationId="conv-1"
        onSelectConversation={() => {}}
        onNewChat={() => {}}
        enableRetentionControls
        isTenantAdmin
      />,
    );

    expect(await screen.findByText("Admin retention")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /retention protection for admin retention/i }),
    );
    expect(await screen.findByLabelText(/legal hold/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/administrator exemption/i)).toBeInTheDocument();
  });
});
