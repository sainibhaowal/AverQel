import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PlanPage from "../app/dashboard/settings/plan/page";

const authState = vi.hoisted(() => ({ roles: ["user"] as string[] }));
const fetchWithAuthMock = vi.hoisted(() => vi.fn());

vi.mock("@/app/context/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "user-1", tenant_id: "tenant-1", roles: authState.roles },
  }),
}));

vi.mock("@/lib/api", () => ({
  fetchWithAuth: fetchWithAuthMock,
}));

const baseResponse = {
  current_plan: {
    id: "free",
    name: "Free",
    storage_limit_bytes: 500 * 1024 * 1024,
    description: "Essential AverQel workspace storage.",
    admin_account: false,
  },
  usage: {
    documents_bytes: 0,
    library_bytes: 0,
    artifacts_bytes: 0,
    pending_upload_bytes: 0,
    total_bytes: 0,
  },
  plans: [
    {
      id: "free",
      name: "Free",
      storage_limit_bytes: 500 * 1024 * 1024,
      description: "Essential AverQel workspace storage.",
      features: ["Documents and collections"],
      admin_only: false,
    },
    {
      id: "editor",
      name: "Editor",
      storage_limit_bytes: 1024 * 1024 * 1024,
      description: "Expanded workspace storage for editor accounts.",
      features: ["Everything in Free"],
      admin_only: false,
    },
    {
      id: "admin",
      name: "Admin",
      storage_limit_bytes: 1024 * 1024 * 1024,
      description: "Administrative workspace access and 1 GB storage.",
      features: ["Administrative workspace controls"],
      admin_only: true,
    },
  ],
  storage_scope: "Shared across this authenticated tenant/workspace.",
};

describe("plan page", () => {
  beforeEach(() => {
    authState.roles = ["user"];
    fetchWithAuthMock.mockResolvedValue({ ok: true, json: async () => baseResponse });
  });

  it("shows free/editor plans and hides the admin plan for normal users", async () => {
    render(<PlanPage />);

    await waitFor(() => expect(screen.getByText("Available plans")).toBeInTheDocument());
    expect(screen.getAllByRole("heading", { name: "Free" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Editor" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Admin" })).not.toBeInTheDocument();
  });

  it("shows the admin plan only for an admin account", async () => {
    authState.roles = ["admin"];
    render(<PlanPage />);

    await waitFor(() => expect(screen.getByRole("heading", { name: "Admin" })).toBeInTheDocument());
    expect(screen.getByText("Admin account")).toBeInTheDocument();
  });

  it("shows the beta grant notice when the API enables it", async () => {
    fetchWithAuthMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        ...baseResponse,
        beta: { enabled: true, plan_id: "editor", plan_name: "Editor", resurface_hours: 36 },
      }),
    });
    render(<PlanPage />);

    await waitFor(() =>
      expect(screen.getByText(/assigned to Editor/i)).toBeInTheDocument(),
    );
  });

  it("hides the beta grant notice when the API disables it", async () => {
    render(<PlanPage />);

    await waitFor(() => expect(screen.getByText("Available plans")).toBeInTheDocument());
    expect(screen.queryByText(/assigned to Editor/i)).not.toBeInTheDocument();
  });
});
