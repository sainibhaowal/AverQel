import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ fetchWithAuth: vi.fn() }));
const exports = vi.hoisted(() => ({
  downloadBlob: vi.fn(),
  exportDiagramPdf: vi.fn(),
  exportDiagramPng: vi.fn(),
  exportDiagramSvg: vi.fn(),
  safeExportName: (value: string, fallback: string) => value || fallback,
}));

vi.mock("@/lib/api", () => api);
vi.mock("@/lib/client-export", () => exports);

import GalleryBlock, { type GalleryPayload } from "../app/dashboard/query/_components/GalleryBlock";
import VisualBlockExport from "../app/dashboard/deepspace/_components/VisualBlockExport";

const imageUrl = "https://images.example.test/research.png";
const ownedUrl =
  "/api/v1/deepspace/library/conversation/files/123e4567-e89b-42d3-a456-426614174000/content";
const createObjectUrlDescriptor = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
const revokeObjectUrlDescriptor = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");

function restoreUrlProperty(
  name: "createObjectURL" | "revokeObjectURL",
  descriptor?: PropertyDescriptor,
) {
  if (descriptor) Object.defineProperty(URL, name, descriptor);
  else delete (URL as Partial<typeof URL>)[name];
}

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  restoreUrlProperty("createObjectURL", createObjectUrlDescriptor);
  restoreUrlProperty("revokeObjectURL", revokeObjectUrlDescriptor);
});

describe("DeepSpace gallery images", () => {
  it("renders visual-block export actions as readable rounded rectangles", () => {
    render(
      <VisualBlockExport
        block={{
          id: "chart-export-controls",
          type: "chart",
          chart_type: "line",
          series: [{ label: "Revenue", value: 12 }],
        }}
      >
        <div>chart preview</div>
      </VisualBlockExport>,
    );

    for (const name of [
      "Export chart source as JSON",
      "Export chart as SVG",
      "Export chart as PNG",
      "Export chart as PDF",
    ]) {
      const button = screen.getByRole("button", { name });
      expect(button).toHaveClass("visual-block-action", "rounded-lg");
      expect(button).not.toHaveClass("rounded-full", "theme-chip");
    }
  });

  it("caches generated image URLs, reloads the owned copy, and can retain it in Library", async () => {
    const onChange = vi.fn().mockResolvedValue(undefined);
    const onImportAsset = vi.fn().mockResolvedValue({
      url: imageUrl,
      owned_url: ownedUrl,
      mime_type: "image/png",
      status: "owned",
      file_id: "123e4567-e89b-42d3-a456-426614174000",
      retention: "temporary",
    });
    const onRetainAsset = vi.fn().mockResolvedValue({
      url: "",
      owned_url: ownedUrl,
      mime_type: "image/png",
      status: "owned",
      file_id: "123e4567-e89b-42d3-a456-426614174000",
      retention: "library",
    });
    const initial: GalleryPayload = {
      id: "gallery-1",
      block_id: "gallery-1",
      type: "gallery",
      title: "Research",
      items: [{ src: imageUrl, alt: "Research photo", caption: "Lab" }],
    };
    const view = render(
      <GalleryBlock
        payload={initial}
        onChange={onChange}
        onImportAsset={onImportAsset}
        onRetainAsset={onRetainAsset}
      />,
    );

    await waitFor(() => expect(onImportAsset).toHaveBeenCalledWith(imageUrl, "temporary"));
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith(
        expect.objectContaining({
          assets: [
            expect.objectContaining({ url: imageUrl, owned_url: ownedUrl, retention: "temporary" }),
          ],
          revision: 1,
        }),
      ),
    );

    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:owned-gallery-image"),
    });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    api.fetchWithAuth.mockResolvedValue({
      ok: true,
      blob: async () => new Blob(["png"], { type: "image/png" }),
    });
    const cached = onChange.mock.calls.at(-1)?.[0] as GalleryPayload;
    view.rerender(
      <GalleryBlock
        payload={cached}
        onChange={onChange}
        onImportAsset={onImportAsset}
        onRetainAsset={onRetainAsset}
      />,
    );
    await waitFor(() =>
      expect(screen.getByRole("img", { name: "Research photo" })).toHaveAttribute(
        "src",
        "blob:owned-gallery-image",
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "Save image to Library" }));
    await waitFor(() =>
      expect(onRetainAsset).toHaveBeenCalledWith("123e4567-e89b-42d3-a456-426614174000"),
    );
    expect(onChange.mock.calls.at(-1)?.[0]).toEqual(
      expect.objectContaining({
        assets: [expect.objectContaining({ url: imageUrl, retention: "library" })],
        revision: 2,
      }),
    );
  });

  it("uses the owned image preview if the original URL fails before the cache loads", async () => {
    let resolveOwnedImage: ((response: { ok: boolean; blob: () => Promise<Blob> }) => void) | null =
      null;
    api.fetchWithAuth.mockImplementation(
      () =>
        new Promise<{ ok: boolean; blob: () => Promise<Blob> }>((resolve) => {
          resolveOwnedImage = resolve;
        }),
    );
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn(() => "blob:owned-gallery-image"),
    });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });

    render(
      <GalleryBlock
        payload={{
          id: "gallery-cached-preview",
          type: "gallery",
          title: "Research photos",
          items: [{ src: imageUrl, alt: "Microscope" }],
          assets: [{ url: imageUrl, owned_url: ownedUrl, status: "owned" }],
        }}
      />,
    );

    const originalImage = screen.getByRole("img", { name: "Microscope" });
    fireEvent.error(originalImage);
    expect(screen.getByText(/This image is unavailable/)).toBeInTheDocument();
    await waitFor(() => expect(resolveOwnedImage).toBeTypeOf("function"));

    await act(async () => {
      resolveOwnedImage?.({
        ok: true,
        blob: async () => new Blob(["png"], { type: "image/png" }),
      });
    });

    await waitFor(() =>
      expect(screen.getByRole("img", { name: "Microscope" })).toHaveAttribute(
        "src",
        "blob:owned-gallery-image",
      ),
    );
  });

  it("embeds owned gallery photos in SVG export so PNG and PDF exports stay untainted", async () => {
    const imageBlob = new Blob(["photo-bytes"], { type: "image/png" });
    Object.defineProperty(imageBlob, "arrayBuffer", {
      value: async () => new TextEncoder().encode("photo-bytes").buffer,
    });
    api.fetchWithAuth.mockResolvedValue({
      ok: true,
      blob: async () => imageBlob,
    });
    render(
      <VisualBlockExport
        block={{
          id: "gallery-export",
          type: "gallery",
          title: "Research gallery",
          items: [{ src: imageUrl, alt: "Microscope", caption: "Study setup" }],
          assets: [
            {
              url: imageUrl,
              owned_url: ownedUrl,
              mime_type: "image/png",
              status: "owned",
              retention: "temporary",
            },
          ],
        }}
      >
        <div>gallery preview</div>
      </VisualBlockExport>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Export gallery as SVG" }));
    await waitFor(() => expect(exports.exportDiagramSvg).toHaveBeenCalledOnce());
    expect(exports.exportDiagramSvg.mock.calls[0]?.[0]).toContain("data:image/png;base64,");
    expect(exports.exportDiagramSvg.mock.calls[0]?.[0]).toContain("Microscope");
  });

  it("shows an error instead of claiming an image was cached when chat persistence fails", async () => {
    const onChange = vi.fn().mockRejectedValue(new Error("The gallery update could not be saved."));
    const onImportAsset = vi.fn().mockResolvedValue({
      url: imageUrl,
      owned_url: ownedUrl,
      mime_type: "image/png",
      status: "owned",
      file_id: "123e4567-e89b-42d3-a456-426614174000",
      retention: "temporary",
    });
    render(
      <GalleryBlock
        payload={{
          id: "gallery-save-failure",
          type: "gallery",
          items: [{ src: imageUrl, alt: "Research photo" }],
        }}
        onChange={onChange}
        onImportAsset={onImportAsset}
      />,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "The gallery update could not be saved.",
    );
    expect(onImportAsset).toHaveBeenCalledWith(imageUrl, "temporary");
    expect(onChange).toHaveBeenCalledOnce();
  });

  it("reports Library save failures for galleries", async () => {
    const onSaveArtifact = vi.fn().mockRejectedValue(new Error("The Library is unavailable."));
    render(
      <GalleryBlock
        payload={{
          id: "gallery-library-error",
          type: "gallery",
          title: "Research images",
          items: [{ src: imageUrl, alt: "Research photo" }],
        }}
        onSaveArtifact={onSaveArtifact}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Save gallery to Library" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("The Library is unavailable.");
    expect(screen.queryByText("Saved to Library.")).not.toBeInTheDocument();
    expect(onSaveArtifact).toHaveBeenCalledOnce();
  });
});
