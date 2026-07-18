import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import AdminCollectionDetailPage from "../app/dashboard/admin/collections/[collectionId]/page";

const fetchWithAuthMock = vi.fn();
const pushMock = vi.fn();
const confirmMock = vi.fn(() => true);
let currentSection = "documents";

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.mock("../app/context/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: "user-2",
      email: "shared@example.com",
      roles: ["user"],
    },
  }),
}));

vi.mock("next/navigation", () => ({
  useParams: () => ({ collectionId: "collection-1" }),
  usePathname: () => "/dashboard/collections/collection-1",
  useRouter: () => ({ push: pushMock }),
  useSearchParams: () => ({
    get: (key: string) => (key === "section" ? currentSection : null),
  }),
}));

vi.stubGlobal("confirm", confirmMock);

function mockProfileResponse() {
  return {
    ok: true,
    json: async () => ({
      collection_code: "COLL-1234",
    }),
  };
}

function primeConnectedLoadMocks() {
  fetchWithAuthMock
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: "collection-1",
        name: "Research",
        description: "Papers",
        requester_access_role: "member",
        created_at: "2026-03-31T00:00:00Z",
        updated_at: "2026-03-31T00:00:00Z",
      }),
    })
    .mockResolvedValueOnce(mockProfileResponse())
    .mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          document_id: "doc-1",
          filename: "Guide.pdf",
          status: "ready",
          created_at: "2026-03-31T00:00:00Z",
        },
      ],
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          id: "perm-1",
          collection_id: "collection-1",
          user_id: "user-1",
          user_email: "owner@example.com",
          role: "member",
          created_at: "2026-03-31T00:00:00Z",
        },
        {
          id: "perm-2",
          collection_id: "collection-1",
          user_id: "user-2",
          user_email: "shared@example.com",
          role: "member",
          created_at: "2026-03-31T00:00:00Z",
        },
      ],
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            document_id: "doc-1",
            filename: "Guide.pdf",
            status: "ready",
            created_at: "2026-03-31T00:00:00Z",
          },
          {
            document_id: "doc-2",
            filename: "Playbook.txt",
            status: "ready",
            created_at: "2026-03-31T00:00:00Z",
          },
        ],
      }),
    })
    .mockResolvedValueOnce({ ok: true, json: async () => [] });
}

function primeConnectedLoadMocksWithoutDocument() {
  fetchWithAuthMock
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        id: "collection-1",
        name: "Research",
        description: "Papers",
        requester_access_role: "member",
        created_at: "2026-03-31T00:00:00Z",
        updated_at: "2026-03-31T00:00:00Z",
      }),
    })
    .mockResolvedValueOnce(mockProfileResponse())
    .mockResolvedValueOnce({
      ok: true,
      json: async () => [],
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          id: "perm-1",
          collection_id: "collection-1",
          user_id: "user-1",
          user_email: "owner@example.com",
          role: "member",
          created_at: "2026-03-31T00:00:00Z",
        },
        {
          id: "perm-2",
          collection_id: "collection-1",
          user_id: "user-2",
          user_email: "shared@example.com",
          role: "member",
          created_at: "2026-03-31T00:00:00Z",
        },
      ],
    })
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            document_id: "doc-1",
            filename: "Guide.pdf",
            status: "ready",
            created_at: "2026-03-31T00:00:00Z",
          },
          {
            document_id: "doc-2",
            filename: "Playbook.txt",
            status: "ready",
            created_at: "2026-03-31T00:00:00Z",
          },
        ],
      }),
    })
    .mockResolvedValueOnce({ ok: true, json: async () => [] });
}

describe("collection detail page", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    pushMock.mockReset();
    confirmMock.mockReset();
    confirmMock.mockReturnValue(true);
    currentSection = "documents";
  });

  it("uses distinct routes for documents and access modes", async () => {
    primeConnectedLoadMocks();

    render(<AdminCollectionDetailPage />);

    expect(await screen.findByRole("link", { name: /^shared documents$/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /^shared documents$/i })).toHaveAttribute(
      "href",
      "/dashboard/collections/collection-1?section=documents",
    );
    expect(screen.getByRole("link", { name: /^bridge members$/i })).toHaveAttribute(
      "href",
      "/dashboard/collections/collection-1?section=access",
    );
  });

  it("removes only the current user's document in document mode", async () => {
    primeConnectedLoadMocks();
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });
    primeConnectedLoadMocksWithoutDocument();

    render(<AdminCollectionDetailPage />);

    fireEvent.click(await screen.findByRole("button", { name: /remove document guide\.pdf/i }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/collections/collection-1/documents", {
        method: "DELETE",
        body: JSON.stringify({ document_ids: ["doc-1"] }),
      });
    });
  });

  it("shows the current user as a member without a duplicate self-disconnect action", async () => {
    currentSection = "access";
    primeConnectedLoadMocks();

    render(<AdminCollectionDetailPage />);

    expect(await screen.findByText(/^you$/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /disconnect access/i })).not.toBeInTheDocument();
  });

  it("disconnects the bridge and redirects back", async () => {
    primeConnectedLoadMocks();
    fetchWithAuthMock.mockResolvedValueOnce({ ok: true, json: async () => ({}) });

    render(<AdminCollectionDetailPage />);

    fireEvent.click(await screen.findByRole("button", { name: /leave collection/i }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith("/collections/collection-1/permissions", {
        method: "DELETE",
        body: JSON.stringify({ user_ids: [] }),
      });
    });
    expect(pushMock).toHaveBeenCalledWith("/dashboard/collections");
  });
});
