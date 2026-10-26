import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, vi } from "vitest";

const { fetchWithAuthMock } = vi.hoisted(() => ({ fetchWithAuthMock: vi.fn() }));

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
}));

import ProtocolMatrixDialog from "../app/components/dashboard/documents/ProtocolMatrixDialog";

const supportedFormats = {
  items: [
    {
      extension: ".pdf",
      category: "pdf",
      extraction_method: "pdf_text",
      needs_conversion: false,
    },
  ],
};

describe("ProtocolMatrixDialog", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows a stable loading state, then the supported formats", async () => {
    let resolveResponse!: (response: {
      ok: boolean;
      json: () => Promise<typeof supportedFormats>;
    }) => void;
    fetchWithAuthMock.mockReturnValue(
      new Promise((resolve) => {
        resolveResponse = resolve;
      }),
    );

    render(<ProtocolMatrixDialog />);
    fireEvent.click(screen.getByRole("button", { name: /protocol matrix/i }));

    expect(screen.getByRole("status")).toHaveTextContent("Loading supported formats");
    await act(async () => {
      resolveResponse({ ok: true, json: async () => supportedFormats });
    });

    expect(await screen.findByRole("dialog", { name: "Supported Formats" })).toBeInTheDocument();
    expect(await screen.findByText(".pdf")).toBeInTheDocument();
    expect(fetchWithAuthMock).toHaveBeenCalledWith("/documents/supported-formats");
  });

  it("closes the dialog without changing the supported-formats request", async () => {
    fetchWithAuthMock.mockResolvedValue({
      ok: true,
      json: async () => supportedFormats,
    });

    render(<ProtocolMatrixDialog />);
    fireEvent.click(screen.getByRole("button", { name: /protocol matrix/i }));
    expect(await screen.findByRole("dialog", { name: "Supported Formats" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Close supported formats" }));
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Supported Formats" })).not.toBeInTheDocument();
    });
  });

  it("offers a retry when formats fail to load", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    fetchWithAuthMock.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce({
      ok: true,
      json: async () => supportedFormats,
    });

    render(<ProtocolMatrixDialog />);
    fireEvent.click(screen.getByRole("button", { name: /protocol matrix/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Supported formats could not be loaded.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText(".pdf")).toBeInTheDocument();
    expect(fetchWithAuthMock).toHaveBeenCalledTimes(2);
  });
});
