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

function exportableSvg(svg: string): string {
  const documentNode = new DOMParser().parseFromString(svg, "image/svg+xml");
  documentNode.querySelectorAll("script, iframe, object, embed").forEach((node) => node.remove());
  documentNode.querySelectorAll("*").forEach((node) => {
    for (const attribute of Array.from(node.attributes)) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim().toLowerCase();
      if (name.startsWith("on") || (name.endsWith("href") && !value.startsWith("#"))) {
        node.removeAttribute(attribute.name);
      }
    }
  });
  return new XMLSerializer().serializeToString(documentNode.documentElement);
}

export function exportDiagramSvg(svg: string, filename: string): void {
  downloadBlob(new Blob([exportableSvg(svg)], { type: "image/svg+xml;charset=utf-8" }), filename);
}

function svgDimensions(svg: string): { width: number; height: number } {
  const root = new DOMParser().parseFromString(svg, "image/svg+xml").documentElement;
  const viewBox = root
    .getAttribute("viewBox")
    ?.trim()
    .split(/[\s,]+/)
    .map(Number);
  const width = Number.parseFloat(root.getAttribute("width") ?? "");
  const height = Number.parseFloat(root.getAttribute("height") ?? "");
  const resolvedWidth = Number.isFinite(width) && width > 0 ? width : (viewBox?.[2] ?? 1200);
  const resolvedHeight = Number.isFinite(height) && height > 0 ? height : (viewBox?.[3] ?? 800);
  return {
    width: Math.max(1, Math.min(resolvedWidth, 8192)),
    height: Math.max(1, Math.min(resolvedHeight, 8192)),
  };
}

export async function diagramSvgToPng(
  svg: string,
): Promise<{ dataUrl: string; width: number; height: number }> {
  const safeSvg = exportableSvg(svg);
  const { width, height } = svgDimensions(safeSvg);
  const imageUrl = URL.createObjectURL(
    new Blob([safeSvg], { type: "image/svg+xml;charset=utf-8" }),
  );
  try {
    const image = new Image();
    image.decoding = "async";
    await new Promise<void>((resolve, reject) => {
      image.onload = () => resolve();
      image.onerror = () => reject(new Error("The diagram image could not be rendered."));
      image.src = imageUrl;
    });
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas export is unavailable in this browser.");
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, width, height);
    context.drawImage(image, 0, 0, width, height);
    return { dataUrl: canvas.toDataURL("image/png"), width, height };
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
