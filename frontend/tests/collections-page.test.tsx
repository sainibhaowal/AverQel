import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import AdminCollectionsPage from "../app/dashboard/admin/collections/page";

const fetchWithAuthMock = vi.fn();
const confirmMock = vi.fn(() => true);
const pushMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard/collections",
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => ({ get: () => null }),
}));

vi.stubGlobal("confirm", confirmMock);

describe("collections admin page", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    confirmMock.mockReset();
    confirmMock.mockReturnValue(true);
    pushMock.mockReset();
    window.history.replaceState(null, "", "/dashboard/collections");
  });

  it("loads connected bridges through the shared authenticated API client", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          id: "collection-1",
          name: "Research",
          description: "Papers and notes",
          requester_access_role: "member",
          created_at: "2026-03-19T00:00:00Z",
        },
      ],
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ collection_code: "COLL-1234" }),
    });

    render(<AdminCollectionsPage />);

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/collections");
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/collections/invitations");
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/auth/profile");
    });

    expect(await screen.findByText(/research/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /manage collection/i })).toHaveAttribute(
      "href",
      "/dashboard/collections/collection-1?section=documents",
    );
  });

  it("creates a bridge through the shared authenticated API client", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ collection_code: "COLL-1234" }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          id: "collection-1",
          name: "Policies",
          description: "Ops",
          requester_access_role: "member",
          created_at: "2026-03-19T00:00:00Z",
        },
      ],
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ collection_code: "COLL-1234" }),
    });

    render(<AdminCollectionsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /\+ new collection/i }));
    fireEvent.click(screen.getByRole("button", { name: /group chat/i }));
    fireEvent.change(screen.getByPlaceholderText(/collection name/i), {
      target: { value: "Policies" },
    });
    fireEvent.change(screen.getByPlaceholderText(/description/i), {
      target: { value: "Ops" },
    });
    fireEvent.click(screen.getByRole("button", { name: /create group/i }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/collections", {
        method: "POST",
        body: JSON.stringify({ name: "Policies", description: "Ops" }),
      });
    });
  });

  it("disconnects a bridge through the shared authenticated API client", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          id: "collection-1",
          name: "Research",
          description: "Papers and notes",
          requester_access_role: "member",
          created_at: "2026-03-19T00:00:00Z",
        },
      ],
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ collection_code: "COLL-1234" }),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({}),
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    });
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ collection_code: "COLL-1234" }),
    });

    render(<AdminCollectionsPage />);

    fireEvent.click(await screen.findByRole("button", { name: /leave collection/i }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/collections/collection-1/permissions", {
        method: "DELETE",
        body: JSON.stringify({ user_ids: [] }),
      });
    });
  });
});
