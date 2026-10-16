"use client";

import { jsPDF } from "jspdf";

export function safeExportName(value: string, fallback: string): string {
  const normalized = value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return normalized || fallback;
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function sanitizeSvgForExport(svg: string): string {
  const documentNode = new DOMParser().parseFromString(svg, "image/svg+xml");
  documentNode.querySelectorAll("script, iframe, object, embed").forEach((node) => node.remove());
  documentNode.querySelectorAll("image").forEach((node) => {
    // An SVG loaded into a blob-backed Image can taint the rasterization
    // canvas when it still references a remote image. Keep data/blob assets,
    // which are self-contained, and remove only the unsafe external asset.
    for (const attributeName of ["href", "xlink:href"]) {
      const value = node.getAttribute(attributeName)?.trim().toLowerCase() ?? "";
      if (
        value.startsWith("data:image/svg+xml") ||
        (value && !value.startsWith("data:") && !value.startsWith("blob:"))
      ) {
        node.remove();
        break;
      }
    }
  });
  documentNode.querySelectorAll("*").forEach((node) => {
    for (const attribute of Array.from(node.attributes)) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim().toLowerCase();
      const hasExternalCssUrl = /url\(\s*[\"']?(?:https?:|\/\/|file:)/i.test(value);
      if (
        name.startsWith("on") ||
        (name.endsWith("href") &&
          !value.startsWith("#") &&
          !value.startsWith("data:") &&
          !value.startsWith("blob:")) ||
        hasExternalCssUrl
      ) {
        node.removeAttribute(attribute.name);
      }
    }
  });
  documentNode.querySelectorAll("style").forEach((node) => {
    // CSS imports and remote font/image URLs can taint a canvas even when no
    // <image> element is present. Mermaid diagrams do not need those remote
    // resources to remain exportable.
    const css = node.textContent ?? "";
    if (/@import|url\(\s*[\"']?(?:https?:|\/\/|file:)/i.test(css)) node.remove();
  });
  return new XMLSerializer().serializeToString(documentNode.documentElement);
}

export function exportDiagramSvg(svg: string, filename: string): void {
  downloadBlob(
    new Blob([sanitizeSvgForExport(svg)], { type: "image/svg+xml;charset=utf-8" }),
    filename,
  );
}

function svgDimensions(svg: string): { width: number; height: number } {
  const root = new DOMParser().parseFromString(svg, "image/svg+xml").documentElement;
  const viewBox = root
    .getAttribute("viewBox")
    ?.trim()
    .split(/[\s,]+/)
    .map(Number);
  const parseAbsoluteDimension = (value: string | null): number | null => {
    const match = value?.trim().match(/^(\d+(?:\.\d+)?)(?:px)?$/i);
    if (!match) return null;
    const parsed = Number(match[1]);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  };
  const width = parseAbsoluteDimension(root.getAttribute("width"));
  const height = parseAbsoluteDimension(root.getAttribute("height"));
  const viewBoxWidth = viewBox?.[2];
  const viewBoxHeight = viewBox?.[3];
  // Mermaid commonly emits percentage dimensions. Use its viewBox in that
  // case so exports keep the diagram's real proportions and full resolution.
  const resolvedWidth = viewBoxWidth && viewBoxWidth > 0 ? viewBoxWidth : (width ?? 1200);
  const resolvedHeight = viewBoxHeight && viewBoxHeight > 0 ? viewBoxHeight : (height ?? 800);
  const dimensionScale = Math.min(1, 8192 / resolvedWidth, 8192 / resolvedHeight);
  return {
    width: Math.max(1, Math.round(resolvedWidth * dimensionScale)),
    height: Math.max(1, Math.round(resolvedHeight * dimensionScale)),
  };
}

export async function diagramSvgToPng(
  svg: string,
): Promise<{ dataUrl: string; width: number; height: number }> {
  const safeSvg = sanitizeSvgForExport(svg);
  const { width, height } = svgDimensions(safeSvg);
  const imageUrl = URL.createObjectURL(
    new Blob([safeSvg], { type: "image/svg+xml;charset=utf-8" }),
  );
  try {
    const image = new Image();
    image.crossOrigin = "anonymous";
    image.decoding = "async";
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("The diagram image could not be rendered."));
      image.src = imageUrl;
    });
    const canvas = document.createElement("canvas");
    const maxCanvasSide = 16_384;
    const maxCanvasPixels = 64_000_000;
    const scale = Math.min(
      2,
      maxCanvasSide / width,
      maxCanvasSide / height,
      Math.sqrt(maxCanvasPixels / (width * height)),
    );
    canvas.width = Math.max(1, Math.round(width * scale));
    canvas.height = Math.max(1, Math.round(height * scale));
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas export is unavailable in this browser.");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    try {
      return { dataUrl: canvas.toDataURL("image/png"), width, height };
    } catch (error) {
      const errorName =
        error && typeof error === "object" && "name" in error
          ? String((error as { name?: unknown }).name)
          : "";
      if (
        (typeof DOMException !== "undefined" &&
          error instanceof DOMException &&
          error.name === "SecurityError") ||
        errorName === "SecurityError" ||
        (error instanceof Error && /tainted canvas|securityerror/i.test(error.message))
      ) {
        throw new Error(
          "PNG/PDF export was blocked by an external diagram resource. Export SVG or remove the external image and retry.",
        );
      }
      throw error;
    }
  } finally {
    URL.revokeObjectURL(imageUrl);
  }
}

export async function exportDiagramPng(svg: string, filename: string): Promise<void> {
  const png = await diagramSvgToPng(svg);
  const response = await fetch(png.dataUrl);
  downloadBlob(await response.blob(), filename);
}

export async function exportDiagramPdf(svg: string, filename: string): Promise<void> {
  const png = await diagramSvgToPng(svg);
  const orientation = png.width >= png.height ? "landscape" : "portrait";
  const pdf = new jsPDF({ orientation, unit: "pt", format: "a4" });
  const pageWidth = pdf.internal.pageSize.getWidth();
  const pageHeight = pdf.internal.pageSize.getHeight();
  const margin = 28;
  const scale = Math.min(
    (pageWidth - margin * 2) / png.width,
    (pageHeight - margin * 2) / png.height,
  );
  const width = png.width * scale;
  const height = png.height * scale;
  pdf.addImage(
    png.dataUrl,
    "PNG",
    (pageWidth - width) / 2,
    (pageHeight - height) / 2,
    width,
    height,
  );
  pdf.save(filename);
}
