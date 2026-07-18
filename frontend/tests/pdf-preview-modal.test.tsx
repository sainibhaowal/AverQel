import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PDFPreviewModal from "../app/components/query/PDFPreviewModal";

const apiMocks = vi.hoisted(() => ({
  fetchWithAuth: vi.fn(),
}));

vi.mock("../lib/api", () => ({
  fetchWithAuth: apiMocks.fetchWithAuth,
}));

describe("PDFPreviewModal", () => {
  beforeEach(() => {
    apiMocks.fetchWithAuth.mockReset();
    vi.restoreAllMocks();
  });

  it("loads the preview with auth and preserves the cited page in the blob viewer", async () => {
    const createObjectURL = vi.fn(() => "blob:secure-pdf");
    const revokeObjectURL = vi.fn();
    const open = vi.fn();

    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: revokeObjectURL,
    });
    Object.defineProperty(window, "open", {
      configurable: true,
      value: open,
    });

    apiMocks.fetchWithAuth.mockResolvedValue({
      ok: true,
      blob: vi.fn().mockResolvedValue(new Blob(["pdf"], { type: "application/pdf" })),
    });

    render(
      <PDFPreviewModal
        isOpen={true}
        documentId="doc-1"
        documentName="example.pdf"
        pageNumber={79}
        onClose={() => {}}
      />,
    );

    expect(apiMocks.fetchWithAuth).toHaveBeenCalledWith("/documents/doc-1/view");

    const iframe = await screen.findByTitle("PDF Preview");
    await waitFor(() => expect(iframe).toHaveAttribute("src", "blob:secure-pdf#page=79"));

    await act(async () => {
      fireEvent.click(screen.getByTitle("Open in New Tab"));
    });
    expect(open).toHaveBeenCalledWith("blob:secure-pdf#page=79", "_blank", "noopener,noreferrer");
  });
});
