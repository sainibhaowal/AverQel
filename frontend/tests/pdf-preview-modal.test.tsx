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
    const createObjectURL = vi.fn((blob: Blob) =>
      blob.type === "application/pdf" ? "blob:secure-pdf" : "blob:secure-page",
    );
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

    apiMocks.fetchWithAuth.mockImplementation(async (url: string) => {
      if (url === "/documents/doc-1/download") {
        return new Response(new Blob(["pdf"], { type: "application/pdf" }), {
          headers: { "content-type": "application/pdf" },
        });
      }
      if (url === "/documents/doc-1/full-text") {
        return Response.json({ content: "Extracted PDF text" });
      }
      if (url === "/documents/doc-1/pages/79") {
        return new Response(new Blob(["page"], { type: "image/png" }), {
          headers: { "content-type": "image/png" },
        });
      }
      throw new Error(`Unexpected document preview request: ${url}`);
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

    await waitFor(() => {
      expect(apiMocks.fetchWithAuth).toHaveBeenCalledWith(
        "/documents/doc-1/download",
        expect.objectContaining({ timeoutMs: 45_000 }),
      );
      expect(apiMocks.fetchWithAuth).toHaveBeenCalledWith(
        "/documents/doc-1/full-text",
        expect.objectContaining({ timeoutMs: 45_000 }),
      );
      expect(apiMocks.fetchWithAuth).toHaveBeenCalledWith(
        "/documents/doc-1/pages/79",
        expect.objectContaining({ timeoutMs: 45_000 }),
      );
    });

    const pagePreview = await screen.findByRole("img", { name: "example.pdf, page 79" });
    expect(pagePreview).toHaveAttribute("src", "blob:secure-page");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open original file in a new tab" }));
    });
    expect(open).toHaveBeenCalledWith("blob:secure-pdf#page=79", "_blank", "noopener,noreferrer");
  });
});
