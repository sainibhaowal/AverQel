import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SmartCollectionsPanel from "../app/dashboard/documents/organization/SmartCollectionsPanel";

const fetchWithAuthMock = vi.fn();
const pushMock = vi.fn();

vi.mock("../lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("../app/components/ui/AverQelDialogHost", () => ({
  averqelConfirm: vi.fn().mockResolvedValue(true),
}));

describe("smart collections page", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
    pushMock.mockReset();
    fetchWithAuthMock.mockImplementation((path: string) => {
      if (path === "/documents/organization/smart-collections")
        return Promise.resolve({ ok: true, json: async () => ({ items: [] }) });
      if (path === "/documents/organization/tags")
        return Promise.resolve({ ok: true, json: async () => ({ items: [] }) });
      if (path === "/documents/organization/folders")
        return Promise.resolve({ ok: true, json: async () => ({ items: [] }) });
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
  });

  it("submits multiple conditions instead of limiting a collection to one rule", async () => {
    render(<SmartCollectionsPanel />);
    fireEvent.change(await screen.findByPlaceholderText("Smart Collection name"), {
      target: { value: "Financial reports" },
    });
    fireEvent.change(screen.getAllByPlaceholderText("Condition value")[0], {
      target: { value: "indexed" },
    });
    fireEvent.click(screen.getByRole("button", { name: /add condition/i }));
    fireEvent.change(screen.getAllByPlaceholderText("Condition value")[1], {
      target: { value: "application/pdf" },
    });

    fetchWithAuthMock.mockImplementation((path: string, init?: RequestInit) => {
      if (path === "/documents/organization/smart-collections" && init?.method === "POST")
        return Promise.resolve({
          ok: true,
          json: async () => ({
            id: "collection-1",
            name: "Financial reports",
            match_mode: "all",
            conditions: [
              { field: "status", operator: "equals", value: "indexed" },
              { field: "status", operator: "equals", value: "application/pdf" },
            ],
            enabled: true,
          }),
        });
      return Promise.resolve({ ok: true, json: async () => ({ items: [] }) });
    });

    fireEvent.click(screen.getByRole("button", { name: /create collection/i }));

    await waitFor(() => {
      const request = fetchWithAuthMock.mock.calls.find(
        ([path, init]) =>
          path === "/documents/organization/smart-collections" && init?.method === "POST",
      );
      expect(request).toBeTruthy();
      expect(JSON.parse(String(request?.[1]?.body)).conditions).toHaveLength(2);
    });
  });
});
