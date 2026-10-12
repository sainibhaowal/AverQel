import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const fetchWithAuthMock = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

import QueryDatasetPreview from "../app/dashboard/query/_components/QueryDatasetPreview";

function response(payload: unknown) {
  return { ok: true, status: 200, json: async () => payload };
}

describe("Grounded Query table preview", () => {
  it("jumps directly to a source row using a bounded page request", async () => {
    fetchWithAuthMock.mockReset();
    fetchWithAuthMock.mockImplementation(async (url: string) => {
      const startRow = Number(new URL(url, "http://localhost").searchParams.get("start_row"));
      return response({
        filename: "sales.csv",
        columns: ["customer"],
        omitted_column_count: 0,
        rows: [{ source_row_number: startRow, customer: "Northwind" }],
        truncated_cells: 0,
        start_row: startRow,
        limit: 100,
        has_more: true,
        row_count: 100_000,
      });
    });

    render(
      <QueryDatasetPreview documentId="document-1" documentName="sales.csv" onClose={vi.fn()} />,
    );
    await screen.findByText("Northwind");
    fireEvent.change(screen.getByLabelText("Jump to source row"), {
      target: { value: "60001" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Go/ }));

    await waitFor(() => {
      expect(fetchWithAuthMock).toHaveBeenCalledWith(
        "/queries/datasets/document-1/rows?start_row=60001&limit=100",
        expect.objectContaining({ timeoutMs: 30_000 }),
      );
    });
    expect(await screen.findByText("60,001")).toBeInTheDocument();
  });
});
