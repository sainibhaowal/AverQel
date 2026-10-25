import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DeepSpaceLibraryDrawer from "../app/dashboard/deepspace/_components/DeepSpaceLibraryDrawer";

const { fetchWithAuthMock } = vi.hoisted(() => ({ fetchWithAuthMock: vi.fn() }));

vi.mock("@/lib/api", () => ({
  fetchWithAuth: (...args: unknown[]) => fetchWithAuthMock(...args),
  uploadWithAuthProgress: vi.fn(),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceLibraryFileWorkspace", () => ({
  default: ({
    name,
    value,
    previewUrl,
    previewContentType,
  }: {
    name: string;
    value: string;
    previewUrl?: string | null;
    previewContentType?: string | null;
  }) => (
    <div
      data-testid="library-file-workspace"
      data-preview-url={previewUrl ?? ""}
      data-preview-content-type={previewContentType ?? ""}
    >
      {name}: {value}
    </div>
  ),
}));

vi.mock("../app/dashboard/deepspace/_components/DeepSpaceVisualArtifactWorkspace", () => ({
  default: () => <div data-testid="visual-artifact-workspace" />,
  isVisualArtifactDocument: () => false,
}));

const file = {
  id: "file-1",
  name: "notes.md",
  content_type: "text/markdown",
  source: "user_upload",
  size_bytes: 12,
  is_binary: false,
};

function jsonResponse(body: unknown) {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } satisfies Partial<Response>;
}

function renderDrawer() {
  return render(<DeepSpaceLibraryDrawer open conversationId="conversation-1" onClose={() => {}} />);
}

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("DeepSpace Library drawer loading", () => {
  beforeEach(() => {
    fetchWithAuthMock.mockImplementation(async (endpoint: string) => {
      if (endpoint.endsWith("/entries")) {
        return jsonResponse({ files: [file], folders: [] });
      }
      if (endpoint.endsWith("/uploads")) return jsonResponse([]);
      if (endpoint.endsWith(`/files/${file.id}`)) {
        return jsonResponse({ ...file, content: "Full preview content" });
      }
      throw new Error(`Unhandled fetchWithAuth call: ${endpoint}`);
    });
  });

  it("loads full file content after the user selects a list entry", async () => {
    renderDrawer();

    const fileName = await screen.findByText(file.name);
    expect(screen.queryByTestId("library-file-workspace")).not.toBeInTheDocument();
    fireEvent.click(fileName);

    expect(await screen.findByTestId("library-file-workspace")).toHaveTextContent(
      "notes.md: Full preview content",
    );
    expect(fetchWithAuthMock).toHaveBeenCalledWith(
      `/deepspace/library/conversation-1/files/${file.id}`,
      expect.objectContaining({ timeoutMs: 30_000, silentTimeout: true }),
    );
  });

  it("opens an attachment file with one recoverable detail request", async () => {
    renderDrawer();
    await screen.findByText(file.name);

    await act(async () => {
      window.dispatchEvent(
        new CustomEvent("deepspace-library-open", { detail: { fileId: file.id } }),
      );
    });

    expect(await screen.findByTestId("library-file-workspace")).toHaveTextContent(
      "notes.md: Full preview content",
    );
    await waitFor(() => {
      const detailRequests = fetchWithAuthMock.mock.calls.filter(([endpoint]) =>
        String(endpoint).endsWith(`/files/${file.id}`),
      );
      expect(detailRequests).toHaveLength(1);
      expect(detailRequests[0]?.[1]).toEqual(
        expect.objectContaining({ timeoutMs: 30_000, silentTimeout: true }),
      );
    });
  });

  it("shows a retry action after the file request fails and recovers on retry", async () => {
    let attempts = 0;
    fetchWithAuthMock.mockImplementation(async (endpoint: string) => {
      if (endpoint.endsWith("/entries")) return jsonResponse({ files: [file], folders: [] });
      if (endpoint.endsWith("/uploads")) return jsonResponse([]);
      if (endpoint.endsWith(`/files/${file.id}`)) {
        attempts += 1;
        if (attempts === 1) throw new Error("request timed out");
        return jsonResponse({ ...file, content: "Recovered preview" });
      }
      throw new Error(`Unhandled fetchWithAuth call: ${endpoint}`);
    });
    renderDrawer();

    fireEvent.click(await screen.findByText(file.name));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The file could not be loaded. Check the connection and retry.",
    );

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("library-file-workspace")).toHaveTextContent(
      "Recovered preview",
    );
    expect(attempts).toBe(2);
  });

  it("surfaces a missing-file response and lets the user retry", async () => {
    let attempts = 0;
    fetchWithAuthMock.mockImplementation(async (endpoint: string) => {
      if (endpoint.endsWith("/entries")) return jsonResponse({ files: [file], folders: [] });
      if (endpoint.endsWith("/uploads")) return jsonResponse([]);
      if (endpoint.endsWith(`/files/${file.id}`)) {
        attempts += 1;
        if (attempts === 1) {
          return {
            ok: false,
            status: 404,
            json: async () => ({}),
          } satisfies Partial<Response>;
        }
        return jsonResponse({ ...file, content: "File loaded after retry" });
      }
      throw new Error(`Unhandled fetchWithAuth call: ${endpoint}`);
    });
    renderDrawer();

    fireEvent.click(await screen.findByText(file.name));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This file is no longer available in the Library.",
    );

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByTestId("library-file-workspace")).toHaveTextContent(
      "File loaded after retry",
    );
    expect(attempts).toBe(2);
  });

  it("shows a retry action when the entries request fails", async () => {
    let attempts = 0;
    fetchWithAuthMock.mockImplementation(async (endpoint: string) => {
      if (endpoint.endsWith("/entries")) {
        attempts += 1;
        if (attempts === 1) throw new Error("request timed out");
        return jsonResponse({ files: [file], folders: [] });
      }
      if (endpoint.endsWith("/uploads")) return jsonResponse([]);
      throw new Error(`Unhandled fetchWithAuth call: ${endpoint}`);
    });
    renderDrawer();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Library files could not be loaded. Check the connection and retry.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText(file.name)).toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it("loads a BMP visual derivative through the authenticated preview route", async () => {
    const image = {
      ...file,
      id: "image-1",
      name: "scan.bmp",
      content_type: "image/bmp",
      is_binary: true,
      size_bytes: 8_000_000,
      extracted_text: "OCR result",
    };
    const createObjectURL = vi.fn(() => "blob:bmp-preview");
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL: vi.fn() });
    fetchWithAuthMock.mockImplementation(async (endpoint: string) => {
      if (endpoint.endsWith("/entries")) return jsonResponse({ files: [image], folders: [] });
      if (endpoint.endsWith("/uploads")) return jsonResponse([]);
      if (endpoint.endsWith(`/files/${image.id}`)) return jsonResponse(image);
      if (endpoint.endsWith(`/files/${image.id}/preview`)) {
        return {
          ok: true,
          status: 200,
          blob: async () => new Blob(["preview"], { type: "image/jpeg" }),
          headers: new Headers({ "content-type": "image/jpeg" }),
        } satisfies Partial<Response>;
      }
      throw new Error(`Unhandled fetchWithAuth call: ${endpoint}`);
    });

    const { unmount } = renderDrawer();
    fireEvent.click(await screen.findByText(image.name));

    const workspace = await screen.findByTestId("library-file-workspace");
    expect(workspace).toHaveAttribute("data-preview-url", "blob:bmp-preview");
    expect(workspace).toHaveAttribute("data-preview-content-type", "image/jpeg");
    expect(fetchWithAuthMock).toHaveBeenCalledWith(
      `/deepspace/library/conversation-1/files/${image.id}/preview`,
      expect.objectContaining({ timeoutMs: 75_000, silentTimeout: true }),
    );
    expect(createObjectURL).toHaveBeenCalledOnce();
    unmount();
  });
});
