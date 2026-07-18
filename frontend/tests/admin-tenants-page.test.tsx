import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import AdminTenantsPage from "../app/dashboard/admin/tenants/page";

const fetchWithAuthMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

describe("admin tenants page", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  it("loads tenant summaries", async () => {
    fetchWithAuthMock.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            tenant_id: "tenant-1",
            name: "Workspace One",
            created_at: "2026-04-01T00:00:00Z",
            updated_at: "2026-04-02T00:00:00Z",
            stats: {
              users_count: 2,
              active_users_count: 2,
              documents_count: 5,
              queries_count: 3,
              collections_count: 1,
            },
          },
        ],
      }),
    });

    render(<AdminTenantsPage />);

    expect(await screen.findByText("Workspace One")).toBeInTheDocument();
    expect(
      screen.getByText(/cross-tenant visibility without opening tenant content/i),
    ).toBeInTheDocument();
  });
});
