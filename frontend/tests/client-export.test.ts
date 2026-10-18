import { vi } from "vitest";

import { diagramSvgToPng, sanitizeSvgForExport } from "../lib/client-export";

describe("client diagram exports", () => {
  it("removes external SVG resources before rasterization", () => {
    const sanitized = sanitizeSvgForExport(`
      <svg xmlns="http://www.w3.org/2000/svg">
        <style>@import url("https://fonts.example.test/font.css");</style>
        <image href="https://images.example.test/remote.png" />
        <image href="data:image/svg+xml;base64,PHN2Zy8+" />
        <image href="data:image/png;base64,AAAA" />
        <a href="https://example.test"><text>unsafe</text></a>
      </svg>
    `);

    expect(sanitized).not.toContain("remote.png");
    expect(sanitized).not.toContain("fonts.example.test");
    expect(sanitized).not.toContain("https://example.test");
    expect(sanitized).not.toContain("data:image/svg+xml");
    expect(sanitized).toContain("data:image/png;base64,AAAA");
  });

  it("converts a tainted-canvas SecurityError into a recoverable export message", async () => {
    const originalCreateObjectUrl = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
    const originalRevokeObjectUrl = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
    const createObjectUrl = vi.fn(() => "blob:diagram-export");
    const revokeObjectUrl = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: createObjectUrl,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: revokeObjectUrl,
    });

    class TestImage {
      crossOrigin = "";
      decoding = "";
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;

      set src(_value: string) {
        queueMicrotask(() => this.onload?.());
      }
    }

    const originalImage = globalThis.Image;
    const getContext = vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      fillRect: vi.fn(),
      drawImage: vi.fn(),
      fillStyle: "",
    } as unknown as CanvasRenderingContext2D);
    const toDataUrl = vi.spyOn(HTMLCanvasElement.prototype, "toDataURL").mockImplementation(() => {
      const error = new Error("Tainted canvases may not be exported.");
      Object.defineProperty(error, "name", { value: "SecurityError" });
      throw error;
    });
    vi.stubGlobal("Image", TestImage);

    try {
      await expect(
        diagramSvgToPng('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" />'),
      ).rejects.toThrow("PNG/PDF export was blocked by an external diagram resource");
      expect(createObjectUrl).toHaveBeenCalledOnce();
      expect(revokeObjectUrl).toHaveBeenCalledWith("blob:diagram-export");
    } finally {
      getContext.mockRestore();
      toDataUrl.mockRestore();
      vi.unstubAllGlobals();
      if (originalImage) vi.stubGlobal("Image", originalImage);
      if (originalCreateObjectUrl) {
        Object.defineProperty(URL, "createObjectURL", originalCreateObjectUrl);
      } else {
        delete (URL as Partial<typeof URL>).createObjectURL;
      }
      if (originalRevokeObjectUrl) {
        Object.defineProperty(URL, "revokeObjectURL", originalRevokeObjectUrl);
      } else {
        delete (URL as Partial<typeof URL>).revokeObjectURL;
      }
    }
  });

  it("uses Mermaid viewBox dimensions for percentage-sized SVGs and rasterizes at high resolution", async () => {
    const originalCreateObjectUrl = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
    const originalRevokeObjectUrl = Object.getOwnPropertyDescriptor(URL, "revokeObjectURL");
    const createObjectUrl = vi.fn(() => "blob:diagram-viewbox-export");
    const revokeObjectUrl = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      writable: true,
      value: createObjectUrl,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      writable: true,
      value: revokeObjectUrl,
    });

    class TestImage {
      crossOrigin = "";
      decoding = "";
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;

      set src(_value: string) {
        queueMicrotask(() => this.onload?.());
      }
    }

    const originalImage = globalThis.Image;
    const drawImage = vi.fn();
    const fillRect = vi.fn();
    const getContext = vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      fillRect,
      drawImage,
      fillStyle: "",
    } as unknown as CanvasRenderingContext2D);
    const toDataUrl = vi
      .spyOn(HTMLCanvasElement.prototype, "toDataURL")
      .mockReturnValue("data:image/png;base64,AAAA");
    vi.stubGlobal("Image", TestImage);

    try {
      const result = await diagramSvgToPng(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 1200 600" />',
      );

      expect(result).toEqual({ dataUrl: "data:image/png;base64,AAAA", width: 1200, height: 600 });
      expect(fillRect).toHaveBeenCalledWith(0, 0, 2400, 1200);
      expect(drawImage).toHaveBeenCalledWith(expect.any(TestImage), 0, 0, 2400, 1200);
      expect(toDataUrl).toHaveBeenCalledWith("image/png");
      expect(revokeObjectUrl).toHaveBeenCalledWith("blob:diagram-viewbox-export");

      const largeResult = await diagramSvgToPng(
        '<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 16000 8000" />',
      );
      expect(largeResult.width / largeResult.height).toBe(2);
      expect(largeResult.width).toBeLessThanOrEqual(8192);
      expect(largeResult.height).toBeLessThanOrEqual(8192);
    } finally {
      getContext.mockRestore();
      toDataUrl.mockRestore();
      vi.unstubAllGlobals();
      if (originalImage) vi.stubGlobal("Image", originalImage);
      if (originalCreateObjectUrl) {
        Object.defineProperty(URL, "createObjectURL", originalCreateObjectUrl);
      } else {
        delete (URL as Partial<typeof URL>).createObjectURL;
      }
      if (originalRevokeObjectUrl) {
        Object.defineProperty(URL, "revokeObjectURL", originalRevokeObjectUrl);
      } else {
        delete (URL as Partial<typeof URL>).revokeObjectURL;
      }
    }
  });
});
