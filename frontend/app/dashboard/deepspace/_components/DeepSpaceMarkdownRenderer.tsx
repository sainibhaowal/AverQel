"use client";

import { memo, useEffect, useId, useMemo, useState, type ReactNode } from "react";
import { Check, ChevronDown, Copy, Download } from "lucide-react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { normalizeMarkdown, normalizeThinkingDisplay } from "../_lib/markdown";
import { isMermaidErrorSvg } from "../../query/_lib/mermaid";
import { sanitizeMermaidSyntax } from "../../query/_components/CodeBlock";
import AdaptiveMarkdownTable from "../../_components/AdaptiveMarkdownTable";
import ChartBlock from "../../query/_components/ChartBlock";
import GraphBlock from "../../query/_components/GraphBlock";
import GalleryBlock, {
  parseGalleryPayload,
  type GalleryAssetRef,
  type GalleryAssetRetention,
} from "../../query/_components/GalleryBlock";
import VisualBlockExport from "./VisualBlockExport";
import { parseVisualChart } from "../../query/_lib/chart-parser";
import {
  inferVisualFenceKind,
  normalizePersistedRichContent,
  unwrapPersistedVisualFence,
} from "../../query/_lib/visual-fences";
import type {
  StreamChartBlock,
  StreamCardBlock,
  StreamDiagramBlock,
  StreamGalleryBlock,
  StructuredBlock,
} from "../_lib/deepspace-stream";
import { exportDiagramPdf, exportDiagramPng, exportDiagramSvg } from "@/lib/client-export";
import { useTheme } from "../../../context/ThemeContext";

import { RichInfoCard } from "./DeepSpaceRichContent";

const MERMAID_EXPORT_ITEM_CLASS =
  "text-foreground rounded-lg px-3 py-2 text-left text-xs transition-colors duration-150 enabled:hover:bg-primary/10 enabled:hover:text-primary focus-visible:bg-primary/10 focus-visible:text-primary focus-visible:ring-2 focus-visible:ring-primary/30 focus-visible:outline-none motion-reduce:transition-none disabled:cursor-not-allowed disabled:opacity-40";

function DeepSpaceTableHeader({ children }: { children?: ReactNode }) {
  return (
    <th className="border-b border-white/10 bg-white/5 px-4 py-3 text-xs uppercase">{children}</th>
  );
}
DeepSpaceTableHeader.displayName = "th";

function DeepSpaceTableCell({ children }: { children?: ReactNode }) {
  return (
    <td className="text-foreground/80 border-b border-white/5 px-4 py-3 text-sm">{children}</td>
  );
}
DeepSpaceTableCell.displayName = "td";

function MermaidPreview({ source }: { source: string }) {
  const id = useId().replace(/:/g, "");
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [copied, setCopied] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [exporting, setExporting] = useState<"png" | "pdf" | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const sanitizedSource = useMemo(() => sanitizeMermaidSyntax(source), [source]);
  const { theme } = useTheme();

  useEffect(() => {
    let cancelled = false;
    void import("mermaid")
      .then(async ({ default: mermaid }) => {
        const isDark = theme === "dark";
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          suppressErrorRendering: true,
          theme: isDark ? "dark" : "default",
          // SVG text labels keep Mermaid exports self-contained and rasterizable.
          // HTML labels use foreignObject nodes that can taint PNG/PDF canvases.
          htmlLabels: false,
          fontFamily: "inherit",
          themeVariables: {
            primaryColor: isDark ? "#1e293b" : "#f8fafc",
            primaryTextColor: isDark ? "#e2e8f0" : "#0f172a",
            primaryBorderColor: isDark ? "#64748b" : "#475569",
            secondaryColor: isDark ? "#0f172a" : "#ffffff",
            tertiaryColor: isDark ? "#111827" : "#f1f5f9",
            lineColor: isDark ? "#94a3b8" : "#475569",
            nodeTextColor: isDark ? "#e2e8f0" : "#0f172a",
            mainBkg: isDark ? "#0f172a" : "#ffffff",
          },
        });
        const parsed = await mermaid.parse(sanitizedSource, { suppressErrors: true });
        if (!parsed) throw new Error("Invalid Mermaid syntax.");
        const result = await mermaid.render(`deepspace-${id}`, sanitizedSource);
        if (isMermaidErrorSvg(result.svg)) throw new Error("Invalid Mermaid syntax.");
        if (!cancelled) setSvg(result.svg);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id, sanitizedSource, theme]);

  const copySource = async () => {
    try {
      await navigator.clipboard.writeText(sanitizedSource);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  const downloadSource = () => {
    const url = URL.createObjectURL(
      new Blob([sanitizedSource], { type: "text/plain;charset=utf-8" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "diagram.mmd";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const exportDiagram = async (format: "svg" | "png" | "pdf") => {
    if (!svg) return;
    setExportError(null);
    try {
      if (format === "svg") {
        exportDiagramSvg(svg, "diagram.svg");
      } else {
        setExporting(format);
        if (format === "png") await exportDiagramPng(svg, "diagram.png");
        else await exportDiagramPdf(svg, "diagram.pdf");
      }
      setExportOpen(false);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : "Diagram export failed safely.");
    } finally {
      setExporting(null);
    }
  };

  return (
    <div className="group border-border bg-surface-1 relative my-4 overflow-visible rounded-xl border p-4">
      <div className="absolute top-3 right-3 z-10 h-8 w-36 opacity-0 transition group-focus-within:opacity-100 group-hover:opacity-100">
        <button
          type="button"
          onClick={() => void copySource()}
          className="visual-block-action absolute top-0 left-0 inline-flex h-8 w-8 items-center justify-center rounded-lg"
          aria-label="Copy Mermaid source"
          title={copied ? "Copied" : "Copy Mermaid source"}
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
        <div className="absolute top-0 right-0">
          <button
            type="button"
            onClick={() => setExportOpen((current) => !current)}
            className="visual-block-action inline-flex h-8 items-center gap-1 rounded-lg px-3 text-xs"
            aria-label="Export Mermaid diagram"
            aria-expanded={exportOpen}
          >
            <Download size={14} /> Export <ChevronDown size={13} />
          </button>
          {exportOpen ? (
            <div className="border-border bg-surface-1 absolute top-10 right-0 z-50 grid min-w-36 gap-1 rounded-xl border p-1 shadow-xl">
              <button type="button" onClick={downloadSource} className={MERMAID_EXPORT_ITEM_CLASS}>
                Mermaid (.mmd)
              </button>
              <button
                type="button"
                onClick={() => void exportDiagram("svg")}
                disabled={!svg}
                className={MERMAID_EXPORT_ITEM_CLASS}
              >
                SVG
              </button>
              <button
                type="button"
                onClick={() => void exportDiagram("png")}
                disabled={!svg || exporting !== null}
                className={MERMAID_EXPORT_ITEM_CLASS}
              >
                {exporting === "png" ? "PNG…" : "PNG"}
              </button>
              <button
                type="button"
                onClick={() => void exportDiagram("pdf")}
                disabled={!svg || exporting !== null}
                className={MERMAID_EXPORT_ITEM_CLASS}
              >
                {exporting === "pdf" ? "PDF…" : "PDF"}
              </button>
            </div>
          ) : null}
        </div>
      </div>
      <div className="overflow-x-auto">
        {svg ? (
          <div data-visual-export-source="diagram" dangerouslySetInnerHTML={{ __html: svg }} />
        ) : (
          <pre className="text-xs text-cyan-100">
            <code>{error ? sanitizedSource : "Rendering diagram…"}</code>
          </pre>
        )}
      </div>
      {exportError ? (
        <p
          className="mt-3 rounded-lg border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-xs text-amber-100"
          role="alert"
        >
          {exportError}
        </p>
      ) : null}
    </div>
  );
}

function isAsciiDiagram(source: string): boolean {
  const lines = source.split("\n").filter((line) => line.trim());
  if (lines.length < 3) return false;
  const structuralLines = lines.filter(
    (line) => /[│┌┐└┘├┤┬┴─]/.test(line) || /^\s*(?:\+[-=+]{2,}\+|\|[-=|]{2,}\|)\s*$/.test(line),
  ).length;
  const hasFlow = lines.some(
    (line) => /(?:↓|↑|←|→|-->|<-)/.test(line) || /^\s*(?:\||v|\^)\s*$/.test(line),
  );
  return structuralLines >= 2 && hasFlow;
}

function AsciiDiagramPreview({ source }: { source: string }) {
  const [copied, setCopied] = useState(false);

  const copySource = async () => {
    try {
      await navigator.clipboard.writeText(source);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className="group relative my-4 overflow-hidden rounded-xl border border-slate-300 bg-slate-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] dark:border-white/10 dark:bg-black/25 dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <div className="absolute top-3 right-3 z-10 opacity-0 transition group-focus-within:opacity-100 group-hover:opacity-100">
        <button
          type="button"
          onClick={() => void copySource()}
          className="visual-block-action inline-flex h-8 w-8 items-center justify-center rounded-lg"
          aria-label="Copy ASCII diagram"
          title={copied ? "Copied" : "Copy ASCII diagram"}
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </div>
      <div className="overflow-x-auto p-5 sm:p-6">
        <pre className="m-0 w-max min-w-full font-mono text-[11px] leading-6 whitespace-pre text-slate-800 [font-variant-ligatures:none] sm:text-xs dark:text-cyan-100">
          <code>{source}</code>
        </pre>
      </div>
    </section>
  );
}

type MarkdownVisualCallbacks = {
  messageId?: string;
  onVisualBlockChange?: (
    messageId: string,
    block: StructuredBlock,
  ) => void | boolean | Promise<void | boolean>;
  onSaveVisualArtifact?: (block: StructuredBlock) => void | Promise<void>;
  onImportGalleryAsset?: (
    messageId: string,
    url: string,
    retention: GalleryAssetRetention,
  ) => Promise<GalleryAssetRef>;
  onRetainGalleryAsset?: (messageId: string, fileId: string) => Promise<GalleryAssetRef>;
};

function ChartPreview({
  source,
  callbacks,
}: {
  source: string;
  callbacks: MarkdownVisualCallbacks;
}) {
  const parsed = parseVisualChart(source, "chart");
  if (!parsed || parsed.data.length < 2) {
    return (
      <pre className="my-4 overflow-x-auto rounded-xl border border-white/10 bg-black/30 p-4 text-xs leading-6 text-cyan-100">
        <code>{source}</code>
      </pre>
    );
  }

  const block: StreamChartBlock = {
    id: readPersistedBlockId(source) ?? stableBlockId("deepspace-chart", source),
    type: "chart",
    ...readPersistedBlockMetadata(source),
    title: parsed.title,
    chart_type: parsed.type,
    series: parsed.data.map((point) => ({
      ...point,
      label: String(point[parsed.xKey] ?? point.label ?? ""),
      value: Number(point[parsed.yKey] ?? point.value ?? 0),
      ...(parsed.zKey ? { z: Number(point[parsed.zKey]) } : {}),
    })),
    raw_payload: source,
    source_markdown: source,
    parser_source: parsed.metadata.source,
    confidence: parsed.metadata.confidence,
    fields: parsed.metadata.fields,
    x_key: parsed.xKey,
    y_key: parsed.yKey,
    z_key: parsed.zKey,
    x_label: parsed.xLabel,
    y_label: parsed.yLabel,
    equation: readChartEquation(source),
  };

  return (
    <VisualBlockExport block={block}>
      <ChartBlock
        block={block as never}
        onChange={(next) =>
          callbacks.messageId && callbacks.onVisualBlockChange
            ? callbacks.onVisualBlockChange(callbacks.messageId, {
                ...block,
                ...next,
              } as StructuredBlock)
            : undefined
        }
        onSaveArtifact={(next) =>
          void Promise.resolve(
            callbacks.onSaveVisualArtifact?.({ ...block, ...next } as StructuredBlock),
          ).catch(() => undefined)
        }
      />
    </VisualBlockExport>
  );
}

function CardPreview({
  source,
  callbacks,
}: {
  source: string;
  callbacks: MarkdownVisualCallbacks;
}) {
  const block = parseCardPayload(source);
  if (!block) {
    return (
      <pre className="my-4 overflow-x-auto rounded-xl border border-white/10 bg-black/30 p-4 text-xs leading-6 text-cyan-100">
        <code>{source}</code>
      </pre>
    );
  }
  return (
    <VisualBlockExport block={block}>
      <RichInfoCard
        block={block}
        onChange={(next) => {
          if (callbacks.messageId && callbacks.onVisualBlockChange) {
            void callbacks.onVisualBlockChange(callbacks.messageId, next);
          }
        }}
        onSaveArtifact={(next) =>
          void Promise.resolve(callbacks.onSaveVisualArtifact?.(next)).catch(() => undefined)
        }
      />
    </VisualBlockExport>
  );
}

function GraphPreview({
  source,
  callbacks,
}: {
  source: string;
  callbacks: MarkdownVisualCallbacks;
}) {
  const block = parseGraphBlock(source);
  if (!block) {
    return (
      <pre className="my-4 overflow-x-auto rounded-xl border border-white/10 bg-black/30 p-4 text-xs leading-6 text-cyan-100">
        <code>{source}</code>
      </pre>
    );
  }
  return (
    <VisualBlockExport block={block}>
      <GraphBlock
        block={block as never}
        onChange={(next) => {
          if (callbacks.messageId && callbacks.onVisualBlockChange) {
            void callbacks.onVisualBlockChange(callbacks.messageId, {
              ...block,
              ...next,
            } as StructuredBlock);
          }
        }}
      />
    </VisualBlockExport>
  );
}

function toGalleryBlock(
  payload: ReturnType<typeof parseGalleryPayload>,
): StreamGalleryBlock | null {
  if (!payload) return null;
  const id = payload.block_id ?? payload.id;
  if (!id) return null;
  return {
    id,
    block_id: id,
    type: "gallery",
    title: payload.title ?? "Gallery",
    items: payload.items,
    schema_version: payload.schema_version ?? 1,
    revision: payload.revision ?? 0,
    assets: payload.assets,
    history: payload.history,
    source_markdown: payload.source_markdown ?? null,
    undo: payload.undo,
  };
}

function parseGraphBlock(source: string): StreamDiagramBlock | null {
  try {
    const payload = JSON.parse(source) as Record<string, unknown>;
    const graph = (
      payload.graph && typeof payload.graph === "object" ? payload.graph : payload
    ) as StreamDiagramBlock["graph"];
    if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) return null;
    return {
      id: readPersistedBlockId(source) ?? stableBlockId("deepspace-graph", source),
      type: "diagram",
      ...readPersistedBlockMetadata(source),
      title: typeof payload.title === "string" ? payload.title : "Diagram canvas",
      diagram_type: "graph_canvas",
      source: "graph_json",
      syntax: source,
      graph,
      source_markdown: source,
    };
  } catch {
    return null;
  }
}

function parseCardPayload(source: string): StreamCardBlock | null {
  try {
    const payload = JSON.parse(source) as Record<string, unknown>;
    if (!payload || typeof payload !== "object" || Array.isArray(payload))
      throw new Error("Invalid card");
    const title =
      typeof payload.title === "string" && payload.title.trim()
        ? payload.title
        : "Information card";
    const content =
      typeof payload.content === "string" ? payload.content : String(payload.body ?? "");
    if (!content.trim()) throw new Error("Card content is empty");
    const block: StreamCardBlock = {
      id: readPersistedBlockId(source) ?? stableBlockId("deepspace-card", source),
      type: "card",
      ...readPersistedBlockMetadata(source),
      title,
      content,
      tone: normalizeCardTone(payload.tone),
      subtitle: typeof payload.subtitle === "string" ? payload.subtitle : null,
      image_url: typeof payload.image_url === "string" ? payload.image_url : null,
      href: typeof payload.href === "string" ? payload.href : null,
      metrics: Array.isArray(payload.metrics)
        ? payload.metrics.flatMap((item) => {
            if (!item || typeof item !== "object") return [];
            const metric = item as Record<string, unknown>;
            if (typeof metric.label !== "string") return [];
            return [
              {
                label: metric.label,
                value: String(metric.value ?? ""),
                detail: typeof metric.detail === "string" ? metric.detail : null,
              },
            ];
          })
        : [],
      actions: Array.isArray(payload.actions)
        ? payload.actions.flatMap((item) => {
            if (!item || typeof item !== "object") return [];
            const action = item as Record<string, unknown>;
            if (typeof action.label !== "string") return [];
            return [
              {
                label: action.label,
                href: typeof action.href === "string" ? action.href : null,
                action: isCardAction(action.action) ? action.action : "open",
                content: typeof action.content === "string" ? action.content : null,
              },
            ];
          })
        : [],
      source_markdown: source,
    };
    return block;
  } catch {
    return null;
  }
}

function DiffPreview({ source }: { source: string }) {
  return (
    <pre className="my-4 overflow-x-auto rounded-xl border border-white/10 bg-black/30 py-3 text-xs leading-6">
      <code className="block min-w-max font-mono">
        {source.split("\n").map((line, index) => {
          const tone =
            line.startsWith("+++") ||
            line.startsWith("---") ||
            line.startsWith("diff ") ||
            line.startsWith("index ")
              ? "text-violet-200"
              : line.startsWith("@@")
                ? "bg-cyan-300/10 text-cyan-100"
                : line.startsWith("+")
                  ? "bg-emerald-300/10 text-emerald-100"
                  : line.startsWith("-")
                    ? "bg-rose-300/10 text-rose-100"
                    : "text-cyan-100";
          return (
            <span key={`${index}-${line}`} className={`block min-h-6 px-4 ${tone}`}>
              {line || " "}
            </span>
          );
        })}
      </code>
    </pre>
  );
}

const DeepSpaceMarkdownRenderer = memo(function DeepSpaceMarkdownRenderer({
  content,
  streaming = false,
  compact = false,
  messageId,
  onVisualBlockChange,
  onSaveVisualArtifact,
  onImportGalleryAsset,
  onRetainGalleryAsset,
}: {
  content: string;
  streaming?: boolean;
  compact?: boolean;
  messageId?: string;
  onVisualBlockChange?: (
    messageId: string,
    block: StructuredBlock,
  ) => void | boolean | Promise<void | boolean>;
  onSaveVisualArtifact?: (block: StructuredBlock) => void | Promise<void>;
  onImportGalleryAsset?: (
    messageId: string,
    url: string,
    retention: GalleryAssetRetention,
  ) => Promise<GalleryAssetRef>;
  onRetainGalleryAsset?: (messageId: string, fileId: string) => Promise<GalleryAssetRef>;
}) {
  const callbacks = useMemo<MarkdownVisualCallbacks>(
    () => ({
      messageId,
      onVisualBlockChange,
      onSaveVisualArtifact,
      onImportGalleryAsset,
      onRetainGalleryAsset,
    }),
    [
      messageId,
      onImportGalleryAsset,
      onRetainGalleryAsset,
      onSaveVisualArtifact,
      onVisualBlockChange,
    ],
  );
  const components = useMemo<Components>(
    () => ({
      pre: ({ children }) => <>{children}</>,
      code: ({ children, className, ...props }) => {
        const language = className?.match(/language-([^\s]+)/i)?.[1]?.toLowerCase() ?? "";
        const value = String(children).replace(/\n$/, "");
        const inline = !className && !String(children).includes("\n");
        if (inline) {
          return (
            <code className={className} {...props}>
              {children}
            </code>
          );
        }
        const persistedFence = unwrapPersistedVisualFence(value);
        const visualKind = persistedFence?.kind ?? inferVisualFenceKind(language, value);
        const visualValue = persistedFence?.source ?? value;
        const visualLanguage = visualKind ?? language;
        // Do not repeatedly mount Mermaid/chart renderers for incomplete stream
        // fences. The plain code block is stable until the provider is done.
        if (!streaming && visualLanguage === "mermaid" && visualValue.trim()) {
          const diagramId =
            readPersistedBlockId(visualValue) ?? stableBlockId("deepspace-mermaid", visualValue);
          const diagram: StreamDiagramBlock = {
            id: diagramId,
            block_id: diagramId,
            type: "diagram",
            title: "Diagram",
            diagram_type: "mermaid_flowchart",
            source: "mermaid",
            syntax: visualValue,
            source_mermaid: visualValue,
            source_markdown: `\`\`\`mermaid\n${visualValue}\n\`\`\``,
            schema_version: 1,
            revision: 0,
          };
          return (
            <VisualBlockExport block={diagram} onSaveArtifact={callbacks.onSaveVisualArtifact}>
              <MermaidPreview source={visualValue} />
            </VisualBlockExport>
          );
        }
        if (!streaming && isAsciiDiagram(value)) return <AsciiDiagramPreview source={value} />;
        if (language === "diff" || language === "patch") return <DiffPreview source={value} />;
        if (!streaming && visualLanguage === "chart") {
          return <ChartPreview source={visualValue} callbacks={callbacks} />;
        }
        if (!streaming && visualLanguage === "card") {
          return <CardPreview source={visualValue} callbacks={callbacks} />;
        }
        if (!streaming && visualLanguage === "graph") {
          return <GraphPreview source={visualValue} callbacks={callbacks} />;
        }
        if (!streaming && visualLanguage === "gallery") {
          const gallery = parseGalleryPayload(visualValue);
          if (gallery) {
            const galleryBlock = toGalleryBlock(gallery) ?? {
              id: stableBlockId("deepspace-gallery", visualValue),
              block_id: stableBlockId("deepspace-gallery", visualValue),
              type: "gallery" as const,
              title: gallery.title ?? "Gallery",
              items: gallery.items,
            };
            const persistedGallery = {
              ...gallery,
              id: gallery.id ?? galleryBlock.id,
              block_id: gallery.block_id ?? galleryBlock.id,
            };
            return (
              <VisualBlockExport block={galleryBlock}>
                <GalleryBlock
                  payload={persistedGallery}
                  onChange={(next) => {
                    const nextBlock = toGalleryBlock(next);
                    if (!callbacks.messageId || !callbacks.onVisualBlockChange || !nextBlock) {
                      return undefined;
                    }
                    return Promise.resolve(
                      callbacks.onVisualBlockChange(callbacks.messageId, nextBlock),
                    ).then((saved) => {
                      if (saved === false) {
                        throw new Error("The gallery update could not be saved to this chat.");
                      }
                    });
                  }}
                  onImportAsset={
                    callbacks.messageId && callbacks.onImportGalleryAsset
                      ? (url, retention) =>
                          callbacks.onImportGalleryAsset!(callbacks.messageId!, url, retention)
                      : undefined
                  }
                  onRetainAsset={
                    callbacks.messageId && callbacks.onRetainGalleryAsset
                      ? (fileId) => callbacks.onRetainGalleryAsset!(callbacks.messageId!, fileId)
                      : undefined
                  }
                  onSaveArtifact={(next) => {
                    const nextBlock = toGalleryBlock(next);
                    return nextBlock ? callbacks.onSaveVisualArtifact?.(nextBlock) : undefined;
                  }}
                />
              </VisualBlockExport>
            );
          }
        }
        return (
          <pre className="my-4 overflow-x-auto rounded-xl border border-white/10 bg-black/30 p-4 text-xs leading-6 text-cyan-100">
            <code className={className} {...props}>
              {value || (streaming ? " " : "")}
            </code>
          </pre>
        );
      },
      table: ({ children }) => (
        <AdaptiveMarkdownTable
          onSaveToLibrary={
            callbacks.onSaveVisualArtifact
              ? (tableRows, tableId) => {
                  const [headers = [], ...rows] = tableRows;
                  const messagePart = (callbacks.messageId ?? "message").replace(
                    /[^a-zA-Z0-9_-]/g,
                    "-",
                  );
                  return callbacks.onSaveVisualArtifact?.({
                    id: `deepspace-table-${messagePart}-${tableId}`,
                    type: "table",
                    title: "Markdown table",
                    headers,
                    rows,
                  });
                }
              : undefined
          }
        >
          {children}
        </AdaptiveMarkdownTable>
      ),
      h1: ({ children }) => (
        <h1
          className={`${compact ? "mt-3 mb-2 pb-1 text-lg" : "mt-8 mb-4 pb-3 text-3xl"} border-b border-cyan-300/20 font-bold tracking-tight text-cyan-50`}
        >
          {children}
        </h1>
      ),
      h2: ({ children }) => (
        <h2
          className={`${compact ? "mt-3 mb-1 text-base" : "mt-7 mb-3 text-2xl"} font-semibold tracking-tight text-cyan-100`}
        >
          {children}
        </h2>
      ),
      h3: ({ children }) => (
        <h3
          className={`text-foreground ${compact ? "mt-2 mb-1 text-sm" : "mt-6 mb-2 text-xl"} font-semibold`}
        >
          {children}
        </h3>
      ),
      h4: ({ children }) => (
        <h4 className="text-foreground mt-5 mb-2 text-base font-semibold">{children}</h4>
      ),
      h5: ({ children }) => (
        <h5 className="text-foreground mt-4 mb-2 text-sm font-semibold">{children}</h5>
      ),
      h6: ({ children }) => (
        <h6 className="text-foreground/75 mt-4 mb-2 text-xs font-semibold tracking-wider uppercase">
          {children}
        </h6>
      ),
      th: DeepSpaceTableHeader,
      td: DeepSpaceTableCell,
      p: ({ children }) => (
        <p className={`text-foreground/90 ${compact ? "my-1 leading-5" : "my-3 leading-8"}`}>
          {children}
        </p>
      ),
      a: ({ href, children }) => (
        <a
          href={href}
          target="_blank"
          rel="noreferrer noopener"
          className="font-medium text-cyan-300 underline decoration-cyan-300/40 underline-offset-4 hover:text-cyan-100"
        >
          {children}
        </a>
      ),
      strong: ({ children }) => <strong className="font-semibold text-cyan-50">{children}</strong>,
      em: ({ children }) => <em className="text-foreground/90">{children}</em>,
      del: ({ children }) => <del className="text-foreground/50">{children}</del>,
      hr: () => <hr className="my-7 border-white/10" />,
      ul: ({ children }) => (
        <ul className={`${compact ? "my-1 space-y-0.5" : "my-2 space-y-2"} list-disc pl-5`}>
          {children}
        </ul>
      ),
      ol: ({ children }) => (
        <ol className={`${compact ? "my-1 space-y-0.5" : "my-2 space-y-2"} list-decimal pl-5`}>
          {children}
        </ol>
      ),
      li: ({ children }) => (
        <li
          className={`text-foreground/85 ${compact ? "leading-5" : ""} pl-1 marker:text-cyan-300`}
        >
          {children}
        </li>
      ),
      input: ({ checked, ...props }) =>
        typeof checked === "boolean" ? (
          <input
            {...props}
            type="checkbox"
            checked={checked}
            readOnly
            className="mr-2 accent-cyan-400"
          />
        ) : (
          <input {...props} />
        ),
      blockquote: ({ children }) => (
        <blockquote className="deepspace-markdown-blockquote my-3 border-l-2 border-cyan-400/50 bg-cyan-400/5 px-4 py-3">
          {children}
        </blockquote>
      ),
      img: ({ src, alt }) => (
        <span className="my-4 block max-w-full" data-markdown-image>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src}
            alt={alt || "Markdown image"}
            loading="lazy"
            className="max-h-[34rem] max-w-full rounded-xl border border-white/10 bg-black/20 object-contain"
            onError={(event) => {
              event.currentTarget.hidden = true;
              event.currentTarget.nextElementSibling?.removeAttribute("hidden");
            }}
          />
          <span
            hidden
            className="text-foreground/55 rounded-xl border border-dashed border-white/15 px-3 py-2 text-xs"
          >
            Image unavailable at this URL.
          </span>
        </span>
      ),
    }),
    [callbacks, compact, streaming],
  );
  // Stream events are already batched once per animation frame by
  // useDeepSpaceStream. Deferring a second time here caused each new delta to
  // cancel the renderer's pending frame, leaving paragraph-shaped stale text
  // onscreen until the provider paused or completed. Render the current live
  // value directly so Markdown structure appears as soon as its marker is
  // complete.
  const normalizedContent = useMemo(
    () =>
      normalizeMarkdown(
        normalizePersistedRichContent(compact ? normalizeThinkingDisplay(content) : content),
      ),
    [compact, content],
  );

  return (
    <div
      className={`text-foreground/90 prose prose-invert my-3 max-w-none break-words ${compact ? "text-xs leading-5" : "leading-8"} ${streaming ? "is-streaming" : ""}`}
      aria-live={streaming ? "polite" : undefined}
    >
      <ReactMarkdown
        // Model output is untrusted and routinely includes dollar prices,
        // shell syntax, and copied LaTeX fragments. Do not run a LaTeX parser
        // in the chat surface: it can turn ordinary text into pathological
        // parser input. Mathematical notation remains readable as Markdown
        // text rather than risking a page-wide rendering failure.
        remarkPlugins={[remarkGfm]}
        components={components}
      >
        {normalizedContent || (streaming ? "\u00a0" : "")}
      </ReactMarkdown>
    </div>
  );
});

export default DeepSpaceMarkdownRenderer;

function isCardTone(value: unknown): value is NonNullable<StreamCardBlock["tone"]> {
  return (
    value === "info" ||
    value === "success" ||
    value === "warning" ||
    value === "error" ||
    value === "neutral"
  );
}

function normalizeCardTone(value: unknown): NonNullable<StreamCardBlock["tone"]> {
  const normalized = typeof value === "string" ? value.trim().toLowerCase() : "";
  if (isCardTone(normalized)) return normalized;
  if (normalized === "positive") return "success";
  if (normalized === "caution") return "warning";
  if (normalized === "negative" || normalized === "critical") return "error";
  if (normalized === "informational") return "info";
  return "neutral";
}

function isCardAction(
  value: unknown,
): value is NonNullable<StreamCardBlock["actions"]>[number]["action"] {
  return value === "open" || value === "copy" || value === "download";
}

function readChartEquation(source: string): string | null {
  try {
    const payload = JSON.parse(source) as Record<string, unknown>;
    return typeof payload.equation === "string" && payload.equation.trim()
      ? payload.equation.trim()
      : null;
  } catch {
    return null;
  }
}

function readPersistedBlockId(source: string): string | null {
  try {
    const payload = JSON.parse(source) as Record<string, unknown>;
    return typeof payload.id === "string" && payload.id.trim() ? payload.id : null;
  } catch {
    return null;
  }
}

function readPersistedBlockMetadata(
  source: string,
): Pick<StreamChartBlock, "block_id" | "revision" | "schema_version"> {
  try {
    const payload = JSON.parse(source) as Record<string, unknown>;
    return {
      block_id:
        typeof payload.block_id === "string"
          ? payload.block_id
          : typeof payload.id === "string"
            ? payload.id
            : undefined,
      revision:
        typeof payload.revision === "number" && Number.isInteger(payload.revision)
          ? Math.max(0, payload.revision)
          : undefined,
      schema_version:
        typeof payload.schema_version === "number" && Number.isInteger(payload.schema_version)
          ? Math.max(1, payload.schema_version)
          : undefined,
    };
  } catch {
    return {};
  }
}

function stableBlockId(prefix: string, source: string): string {
  let hash = 0;
  for (let index = 0; index < source.length; index += 1) {
    hash = (hash * 31 + source.charCodeAt(index)) | 0;
  }
  return `${prefix}-${Math.abs(hash).toString(36)}`;
}
