"use client";

import { useRef, useState, type ReactNode } from "react";
import { Check, Download, Save } from "lucide-react";

import {
  downloadBlob,
  exportDiagramPdf,
  exportDiagramPng,
  exportDiagramSvg,
  safeExportName,
} from "@/lib/client-export";
import { fetchWithAuth } from "@/lib/api";
import type { StructuredBlock } from "../_lib/deepspace-stream";

function xml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => {
    const entities: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&apos;",
    };
    return entities[character] ?? character;
  });
}

function fallbackSvg(block: StructuredBlock): string {
  const title = "title" in block ? String(block.title ?? "Visual") : "Visual";
  const lines: string[] = [];
  if (block.type === "card") {
    if (block.subtitle) lines.push(block.subtitle);
    if (block.layout && block.layout !== "standard") lines.push(`Layout: ${block.layout}`);
    if (block.image_alt) lines.push(`Image: ${block.image_alt}`);
    lines.push(...block.content.split(/\r?\n/));
    for (const metric of block.metrics ?? []) lines.push(`${metric.label}: ${metric.value}`);
    for (const detail of block.details ?? []) lines.push(`${detail.label}: ${detail.value}`);
    for (const action of block.actions ?? []) lines.push(`Action: ${action.label}`);
    for (const source of block.sources ?? []) lines.push(`Source: ${source.title} — ${source.url}`);
  } else if (block.type === "gallery") {
    lines.push(`${block.items.length} images`);
    block.items.forEach((item, index) => lines.push(`${index + 1}. ${item.caption || item.alt}`));
  } else if (block.type === "infographic") {
    lines.push(`${block.layout.replaceAll("_", " ")} infographic`);
    for (const item of block.items) {
      const time = item.date ? `${item.date} · ` : "";
      const value = item.value != null ? ` — ${item.value}` : "";
      lines.push(`${time}${item.title}${value}`);
      if (item.description) lines.push(`  ${item.description}`);
    }
    if (block.note) lines.push(block.note);
    for (const source of block.sources ?? []) lines.push(`Source: ${source.title} — ${source.url}`);
  } else if (block.type === "chart") {
    lines.push(`${block.chart_type} chart${block.equation ? ` · ${block.equation}` : ""}`);
    for (const point of block.series) lines.push(`${point.label}: ${point.value}`);
    for (const group of block.series_groups ?? []) {
      lines.push(group.name);
      for (const point of group.points) lines.push(`  ${point.label}: ${point.value}`);
    }
  } else if (block.type === "diagram") {
    lines.push(...(block.syntax || "Diagram").split(/\r?\n/));
    if (block.graph) {
      for (const node of block.graph.nodes) lines.push(`${node.id}: ${node.label}`);
      for (const edge of block.graph.edges)
        lines.push(`${edge.source} → ${edge.target}${edge.label ? ` (${edge.label})` : ""}`);
    }
  } else {
    lines.push(...block.headers.join(" · ").split(/\r?\n/));
    lines.push(...block.rows.map((row) => row.join(" · ")));
  }
  const wrapped = lines
    .flatMap((line) => {
      const words = line.trim().split(/\s+/);
      const result: string[] = [];
      let current = "";
      for (const word of words) {
        const next = current ? `${current} ${word}` : word;
        if (next.length > 88 && current) {
          result.push(current);
          current = word;
        } else current = next;
      }
      if (current) result.push(current);
      return result;
    })
    .slice(0, 80);
  const height = Math.max(180, 88 + wrapped.length * 22);
  const text = wrapped
    .map(
      (line, index) =>
        `<text x="32" y="${86 + index * 22}" font-family="Inter,Arial,sans-serif" font-size="13" fill="#263746">${xml(line)}</text>`,
    )
    .join("");
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="${height}" viewBox="0 0 1200 ${height}"><rect width="1200" height="${height}" rx="22" fill="#f8fafc"/><rect x="1" y="1" width="1198" height="${height - 2}" rx="21" fill="none" stroke="#cbd5e1"/><text x="32" y="48" font-family="Inter,Arial,sans-serif" font-size="22" font-weight="600" fill="#0f172a">${xml(title)}</text>${text}</svg>`;
}

const MAX_GALLERY_EXPORT_IMAGES = 24;
const MAX_GALLERY_EXPORT_BYTES = 24 * 1024 * 1024;
const MAX_GALLERY_EXPORT_IMAGE_BYTES = 8 * 1024 * 1024;

function imageExtension(mime: string): string | null {
  return (
    {
      "image/avif": "avif",
      "image/gif": "gif",
      "image/jpeg": "jpg",
      "image/png": "png",
      "image/webp": "webp",
    }[mime.toLowerCase()] ?? null
  );
}

async function blobDataUrl(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return `data:${blob.type};base64,${btoa(binary)}`;
}

async function gallerySvg(block: Extract<StructuredBlock, { type: "gallery" }>): Promise<string> {
  const width = 1200;
  const tileWidth = 560;
  const tileHeight = 360;
  const gap = 24;
  const top = 108;
  const items = block.items.slice(0, MAX_GALLERY_EXPORT_IMAGES);
  const encoded = new Map<string, string>();
  let totalBytes = 0;
  for (const item of items) {
    const asset = block.assets?.find(
      (candidate) => candidate.url === item.src && candidate.owned_url,
    );
    if (!asset?.owned_url) continue;
    try {
      const response = (await fetchWithAuth(asset.owned_url, { timeoutMs: 20_000 })) as Response;
      if (!response.ok) continue;
      const blob = await response.blob();
      if (!imageExtension(blob.type) || blob.size > MAX_GALLERY_EXPORT_IMAGE_BYTES) continue;
      if (totalBytes + blob.size > MAX_GALLERY_EXPORT_BYTES) break;
      totalBytes += blob.size;
      encoded.set(item.src, await blobDataUrl(blob));
    } catch {
      // An unavailable or CORS-blocked source is represented as an explicit
      // placeholder; it must not taint the SVG/PNG/PDF export canvas.
    }
  }
  const rows = Math.ceil(items.length / 2);
  const height = top + rows * tileHeight + Math.max(0, rows - 1) * gap + 28;
  const tiles = items
    .map((item, index) => {
      const x = 32 + (index % 2) * (tileWidth + gap);
      const y = top + Math.floor(index / 2) * (tileHeight + gap);
      const dataUrl = encoded.get(item.src);
      const image = dataUrl
        ? `<image href="${dataUrl}" x="${x + 12}" y="${y + 12}" width="${tileWidth - 24}" height="${tileHeight - 74}" preserveAspectRatio="xMidYMid meet" />`
        : `<rect x="${x + 12}" y="${y + 12}" width="${tileWidth - 24}" height="${tileHeight - 74}" rx="14" fill="#e2e8f0"/><text x="${x + tileWidth / 2}" y="${y + 150}" text-anchor="middle" font-size="15" fill="#64748b">Image unavailable for export</text>`;
      return `<g><rect x="${x}" y="${y}" width="${tileWidth}" height="${tileHeight}" rx="18" fill="#ffffff" stroke="#cbd5e1"/>${image}<text x="${x + 16}" y="${y + tileHeight - 40}" font-family="Inter,Arial,sans-serif" font-size="15" font-weight="600" fill="#0f172a">${xml(item.alt || `Image ${index + 1}`)}</text><text x="${x + 16}" y="${y + tileHeight - 17}" font-family="Inter,Arial,sans-serif" font-size="12" fill="#475569">${xml(item.caption ?? "")}</text></g>`;
    })
    .join("");
  const omitted = block.items.length - items.length;
  const unavailable = items.filter((item) => !encoded.has(item.src)).length;
  const noteText = [
    unavailable > 0 ? `${unavailable} image(s) could not be embedded.` : "",
    omitted > 0 ? `${omitted} additional image(s) omitted from this export.` : "",
  ]
    .filter(Boolean)
    .join(" ");
  const note = noteText
    ? `<text x="32" y="${height - 10}" font-family="Inter,Arial,sans-serif" font-size="12" fill="#64748b">${xml(noteText)}</text>`
    : "";
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" rx="22" fill="#f8fafc"/><text x="32" y="54" font-family="Inter,Arial,sans-serif" font-size="25" font-weight="700" fill="#0f172a">${xml(block.title ?? "Image gallery")}</text>${tiles}${note}</svg>`;
}

export default function VisualBlockExport({
  block,
  children,
  onSaveArtifact,
  className,
  contentClassName,
}: {
  block: StructuredBlock;
  children: ReactNode;
  onSaveArtifact?: (block: StructuredBlock) => void | Promise<void>;
  className?: string;
  contentClassName?: string;
}) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [savedRevision, setSavedRevision] = useState<number | null>(null);
  const revision = "revision" in block && typeof block.revision === "number" ? block.revision : 0;
  const saved = savedRevision === revision;
  const filename = safeExportName(
    "title" in block ? String(block.title ?? "visual") : block.type,
    "visual",
  );
  const source = async () => {
    if (block.type === "gallery") return gallerySvg(block);
    if (block.type === "card" || block.type === "infographic" || block.type === "table") {
      return fallbackSvg(block);
    }
    const svg =
      contentRef.current?.querySelector<SVGSVGElement>(
        '[data-visual-export-source="diagram"] svg',
      ) ??
      contentRef.current?.querySelector<SVGSVGElement>('svg[role="img"]') ??
      contentRef.current?.querySelector<SVGSVGElement>("svg");
    return svg ? new XMLSerializer().serializeToString(svg) : fallbackSvg(block);
  };
  const exportAs = async (format: "svg" | "png" | "pdf") => {
    setError(null);
    setBusy(format);
    try {
      const svg = await source();
      if (format === "svg") exportDiagramSvg(svg, `${filename}.svg`);
      else if (format === "png") await exportDiagramPng(svg, `${filename}.png`);
      else await exportDiagramPdf(svg, `${filename}.pdf`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The visual could not be exported.");
    } finally {
      setBusy(null);
    }
  };
  const downloadJson = () => {
    downloadBlob(
      new Blob([JSON.stringify(block, null, 2)], { type: "application/json;charset=utf-8" }),
      `${filename}${block.type === "diagram" && block.source === "graph_json" ? ".draw.json" : ".json"}`,
    );
  };
  const downloadMermaid = () => {
    if (block.type !== "diagram" || !block.syntax) return;
    downloadBlob(new Blob([block.syntax], { type: "text/plain;charset=utf-8" }), `${filename}.mmd`);
  };
  const saveArtifact = async () => {
    if (!onSaveArtifact) return;
    setError(null);
    setBusy("save");
    setSavedRevision(null);
    try {
      await onSaveArtifact(block);
      setSavedRevision(revision);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "The visual artifact could not be saved.",
      );
    } finally {
      setBusy(null);
    }
  };
  return (
    <section
      className={`my-3 min-w-0 ${className ?? ""}`}
      data-visual-block-id={block.id}
      data-visual-block-type={block.type}
    >
      <div className="mb-1 flex justify-end gap-1 transition">
        {onSaveArtifact ? (
          <button
            type="button"
            onClick={() => void saveArtifact()}
            disabled={busy !== null}
            aria-label="Save diagram artifact"
            className="visual-block-action visual-export-action inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[10px]"
          >
            {saved ? <Check size={11} /> : <Save size={11} />}
            {busy === "save" ? "Saving…" : saved ? "Saved" : "Save artifact"}
          </button>
        ) : null}
        <button
          type="button"
          onClick={downloadJson}
          aria-label={`Export ${block.type} source as JSON`}
          className="visual-block-action visual-export-action inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[10px] uppercase"
        >
          JSON
        </button>
        {block.type === "diagram" && block.source === "mermaid" ? (
          <button
            type="button"
            onClick={downloadMermaid}
            aria-label="Export diagram source as Mermaid"
            className="visual-block-action visual-export-action inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[10px] uppercase"
          >
            MMD
          </button>
        ) : null}
        {(["svg", "png", "pdf"] as const).map((format) => (
          <button
            key={format}
            type="button"
            disabled={busy !== null}
            onClick={() => void exportAs(format)}
            aria-label={`Export ${block.type} as ${format.toUpperCase()}`}
            className="visual-block-action visual-export-action inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[10px] uppercase disabled:opacity-50"
          >
            <Download size={11} /> {busy === format ? "…" : format}
          </button>
        ))}
      </div>
      <div ref={contentRef} className={contentClassName}>
        {children}
      </div>
      {error ? (
        <p className="mt-1 text-xs text-amber-500" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
