"use client";

import {
  Download,
  ExternalLink,
  FileJson,
  Link2,
  Play,
  Copy,
  Check,
  Pencil,
  Save,
} from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import ChartBlock from "../../query/_components/ChartBlock";
import DiagramBlock from "../../query/_components/DiagramBlock";
import GalleryBlock, {
  type GalleryAssetRef,
  type GalleryAssetRetention,
} from "../../query/_components/GalleryBlock";
import TableBlock from "../../query/_components/TableBlock";
import VisualBlockExport from "./VisualBlockExport";
import type {
  StreamChartBlock as QueryChartBlock,
  StreamDiagramBlock as QueryDiagramBlock,
  StreamTableBlock as QueryTableBlock,
} from "../../query/_lib/stream-protocol";

import type {
  StreamCardBlock as DeepSpaceCardBlock,
  StructuredBlock,
} from "../_lib/deepspace-stream";

type DeepSpaceRichContentProps = {
  blocks?: StructuredBlock[];
  content?: string;
  isStreaming?: boolean;
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

/**
 * DeepSpace and Query share the same visual language for structured output.
 * This adapter keeps the DeepSpace transport backward compatible while using
 * the tested SVG chart, Mermaid/graph, and table renderers from Query.
 */
export default function DeepSpaceRichContent({
  blocks = [],
  content = "",
  isStreaming = false,
  messageId,
  onVisualBlockChange,
  onSaveVisualArtifact,
  onImportGalleryAsset,
  onRetainGalleryAsset,
}: DeepSpaceRichContentProps) {
  const displayBlocks = blocks.filter((block) => !isDuplicatedInMarkdown(block, content));
  if (displayBlocks.length === 0) return null;

  return (
    <div className="deepspace-rich-content mt-5 space-y-5 sm:space-y-6">
      {displayBlocks.map((block) => {
        switch (block.type) {
          case "table":
            return (
              <VisualBlockExport key={block.id} block={block}>
                <TableBlock
                  block={toQueryTableBlock(block)}
                  isStreaming={isStreaming}
                  onSaveToLibrary={
                    onSaveVisualArtifact ? () => onSaveVisualArtifact(block) : undefined
                  }
                />
              </VisualBlockExport>
            );
          case "chart":
            return (
              <VisualBlockExport key={block.id} block={block}>
                <ChartBlock
                  block={toQueryChartBlock(block)}
                  onChange={(next) =>
                    messageId && onVisualBlockChange
                      ? onVisualBlockChange(messageId, fromQueryChartBlock(next, block))
                      : undefined
                  }
                  onSaveArtifact={(next) =>
                    void Promise.resolve(
                      onSaveVisualArtifact?.(fromQueryChartBlock(next, block)),
                    ).catch(() => undefined)
                  }
                />
              </VisualBlockExport>
            );
          case "card":
            return (
              <VisualBlockExport key={block.id} block={block}>
                <RichInfoCard
                  block={block}
                  onChange={(next) => {
                    if (messageId && onVisualBlockChange) {
                      void onVisualBlockChange(messageId, next);
                    }
                  }}
                  onSaveArtifact={(next) =>
                    void Promise.resolve(onSaveVisualArtifact?.(next)).catch(() => undefined)
                  }
                />
              </VisualBlockExport>
            );
          case "diagram":
            return (
              <VisualBlockExport
                key={block.id}
                block={block}
                onSaveArtifact={
                  onSaveVisualArtifact
                    ? (next) =>
                        onSaveVisualArtifact(
                          fromQueryDiagramBlock(next as QueryDiagramBlock, block),
                        )
                    : undefined
                }
              >
                <DiagramBlock
                  block={toQueryDiagramBlock(block)}
                  isStreaming={isStreaming}
                  onChange={(next) => {
                    if (messageId && onVisualBlockChange) {
                      void onVisualBlockChange(messageId, fromQueryDiagramBlock(next, block));
                    }
                  }}
                />
              </VisualBlockExport>
            );
          case "gallery":
            return (
              <VisualBlockExport key={block.id} block={block}>
                <GalleryBlock
                  payload={block}
                  onChange={(next) => {
                    if (!messageId || !onVisualBlockChange) return undefined;
                    return Promise.resolve(
                      onVisualBlockChange(messageId, { ...block, ...next, type: "gallery" }),
                    ).then((saved) => {
                      if (saved === false) {
                        throw new Error("The gallery update could not be saved to this chat.");
                      }
                    });
                  }}
                  onImportAsset={
                    messageId && onImportGalleryAsset
                      ? (url, retention) => onImportGalleryAsset(messageId, url, retention)
                      : undefined
                  }
                  onRetainAsset={
                    messageId && onRetainGalleryAsset
                      ? (fileId) => onRetainGalleryAsset(messageId, fileId)
                      : undefined
                  }
                  onSaveArtifact={(next) =>
                    void Promise.resolve(
                      onSaveVisualArtifact?.({ ...block, ...next, type: "gallery" }),
                    ).catch(() => undefined)
                  }
                />
              </VisualBlockExport>
            );
          default:
            return null;
        }
      })}
    </div>
  );
}

function fromQueryChartBlock(
  block: QueryChartBlock,
  previous: Extract<StructuredBlock, { type: "chart" }>,
): Extract<StructuredBlock, { type: "chart" }> {
  return { ...previous, ...block } as Extract<StructuredBlock, { type: "chart" }>;
}

function fromQueryDiagramBlock(
  block: QueryDiagramBlock,
  previous: Extract<StructuredBlock, { type: "diagram" }>,
): Extract<StructuredBlock, { type: "diagram" }> {
  return { ...previous, ...block } as Extract<StructuredBlock, { type: "diagram" }>;
}

export function RichInfoCard({
  block,
  onChange,
  onSaveArtifact,
}: {
  block: DeepSpaceCardBlock;
  onChange?: (block: DeepSpaceCardBlock) => void | Promise<void>;
  onSaveArtifact?: (block: DeepSpaceCardBlock) => void | Promise<void>;
}) {
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => JSON.stringify(block, null, 2));
  const tone = block.tone ?? "neutral";
  const imageHref = safeExternalHref(block.image_url);
  const sourceHref = safeExternalHref(block.href);
  const toneClasses = {
    info: "border-cyan-400/25 bg-cyan-400/[0.07]",
    success: "border-emerald-400/25 bg-emerald-400/[0.07]",
    warning: "border-amber-400/25 bg-amber-400/[0.07]",
    error: "border-rose-400/25 bg-rose-400/[0.07]",
    neutral: "border-white/10 bg-white/[0.035]",
  } as const;

  const copyContent = async (value = block.content) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };

  const downloadCard = () => {
    const payload = JSON.stringify(block, null, 2);
    const url = URL.createObjectURL(new Blob([payload], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${slugify(block.title) || "information-card"}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <article
      className={`deepspace-rich-card group relative overflow-hidden rounded-[1.5rem] border p-5 shadow-[0_20px_60px_-44px_rgba(34,211,238,0.65)] sm:p-6 ${toneClasses[tone]}`}
    >
      <div className="pointer-events-none absolute -top-16 -right-12 h-36 w-36 rounded-full bg-white/[0.06] blur-3xl" />
      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          {imageHref ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageHref}
              alt=""
              loading="lazy"
              className="h-12 w-12 shrink-0 rounded-xl border border-white/15 object-cover"
              onError={(event) => {
                event.currentTarget.style.display = "none";
              }}
            />
          ) : (
            <div className="text-primary flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-black/15">
              <FileJson size={19} aria-hidden="true" />
            </div>
          )}
          <div className="min-w-0">
            <h3 className="text-foreground text-base font-semibold tracking-tight">
              {block.title}
            </h3>
            {block.subtitle ? (
              <p className="text-foreground/60 mt-1 text-xs">{block.subtitle}</p>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1 opacity-70 transition group-focus-within:opacity-100 group-hover:opacity-100">
          {onChange ? (
            <button
              type="button"
              onClick={() => {
                if (editing) {
                  try {
                    const next = JSON.parse(draft) as DeepSpaceCardBlock;
                    if (next.id === block.id && next.type === "card") {
                      void onChange({ ...next, revision: (block.revision ?? 0) + 1 });
                      setEditing(false);
                    }
                  } catch {
                    // Keep the editor open until the JSON is valid.
                  }
                } else {
                  setDraft(JSON.stringify(block, null, 2));
                  setEditing(true);
                }
              }}
              className="theme-chip inline-flex h-8 items-center gap-1 rounded-full px-2.5 text-[11px]"
              aria-label={editing ? "Save card" : "Edit card"}
            >
              {editing ? <Save size={14} /> : <Pencil size={14} />}
            </button>
          ) : null}
          {onSaveArtifact ? (
            <button
              type="button"
              onClick={() => void onSaveArtifact(block)}
              className="theme-chip inline-flex h-8 items-center rounded-full px-2.5 text-[11px]"
            >
              Save
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => void copyContent()}
            className="theme-chip inline-flex h-8 w-8 items-center justify-center rounded-full"
            aria-label={copied ? "Card content copied" : "Copy card content"}
            title={copied ? "Copied" : "Copy card content"}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
          <button
            type="button"
            onClick={downloadCard}
            className="theme-chip inline-flex h-8 w-8 items-center justify-center rounded-full"
            aria-label="Download information card"
            title="Download card JSON"
          >
            <Download size={14} />
          </button>
        </div>
      </div>

      {editing ? (
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          aria-label="Edit card fields as JSON"
          className="border-glass-border bg-background/60 text-foreground relative mt-4 min-h-52 w-full rounded-xl border p-3 font-mono text-xs leading-5"
        />
      ) : null}
      <div className={editing ? "hidden" : "relative mt-4 text-sm leading-7"}>
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children }) => {
              const safeHref = safeExternalHref(href);
              return safeHref ? (
                <a
                  href={safeHref}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-primary inline-flex items-center gap-1 underline underline-offset-4"
                >
                  {children} <ExternalLink size={12} aria-hidden="true" />
                </a>
              ) : (
                <>{children}</>
              );
            },
            p: ({ children }) => <p className="text-foreground/85 my-2">{children}</p>,
            ul: ({ children }) => (
              <ul className="text-foreground/80 my-2 list-disc space-y-1 pl-5">{children}</ul>
            ),
            ol: ({ children }) => (
              <ol className="text-foreground/80 my-2 list-decimal space-y-1 pl-5">{children}</ol>
            ),
            strong: ({ children }) => (
              <strong className="text-foreground font-semibold">{children}</strong>
            ),
          }}
        >
          {block.content}
        </ReactMarkdown>
      </div>

      {block.metrics?.length ? (
        <div className="relative mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {block.metrics.map((metric) => (
            <div
              key={`${metric.label}-${String(metric.value)}`}
              className="rounded-xl border border-white/10 bg-black/10 px-3 py-2.5"
            >
              <div className="text-foreground/55 text-[10px] font-semibold tracking-[0.14em] uppercase">
                {metric.label}
              </div>
              <div className="text-foreground mt-1 text-lg font-semibold tabular-nums">
                {String(metric.value)}
              </div>
              {metric.detail ? (
                <div className="text-foreground/55 mt-0.5 text-[11px]">{metric.detail}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}

      {sourceHref ? (
        <a
          href={sourceHref}
          target="_blank"
          rel="noreferrer noopener"
          className="text-primary relative mt-5 inline-flex items-center gap-2 text-xs font-semibold tracking-[0.14em] uppercase"
        >
          Open source <Link2 size={13} aria-hidden="true" />
        </a>
      ) : null}

      {block.actions?.length ? (
        <div className="relative mt-5 flex flex-wrap gap-2 border-t border-white/10 pt-4">
          {block.actions.map((action) => (
            <CardActionButton
              key={`${action.label}-${action.href ?? action.action ?? ""}`}
              action={action}
              onCopy={copyContent}
            />
          ))}
        </div>
      ) : null}
    </article>
  );
}

function CardActionButton({
  action,
  onCopy,
}: {
  action: NonNullable<DeepSpaceCardBlock["actions"]>[number];
  onCopy: (content?: string) => Promise<void>;
}) {
  const href = safeExternalHref(action.href);
  if (action.action === "copy") {
    return (
      <button
        type="button"
        onClick={() => void onCopy(action.content ?? action.label)}
        className="theme-chip inline-flex items-center gap-2 rounded-full px-3 py-2 text-xs"
      >
        <Copy size={13} aria-hidden="true" /> {action.label}
      </button>
    );
  }
  if (action.action === "download") {
    return (
      <button
        type="button"
        onClick={() => downloadTextFile(action.content ?? action.label, action.label)}
        className="theme-chip inline-flex items-center gap-2 rounded-full px-3 py-2 text-xs"
      >
        <Download size={13} aria-hidden="true" /> {action.label}
      </button>
    );
  }
  return href ? (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="theme-chip inline-flex items-center gap-2 rounded-full px-3 py-2 text-xs"
    >
      <Play size={13} aria-hidden="true" /> {action.label}
    </a>
  ) : null;
}

function toQueryTableBlock(block: Extract<StructuredBlock, { type: "table" }>): QueryTableBlock {
  return { ...block, title: block.title ?? undefined };
}

function toQueryChartBlock(block: Extract<StructuredBlock, { type: "chart" }>): QueryChartBlock {
  return {
    ...block,
    series: block.series,
    is_streaming: false,
  } as unknown as QueryChartBlock;
}

function toQueryDiagramBlock(
  block: Extract<StructuredBlock, { type: "diagram" }>,
): QueryDiagramBlock {
  return {
    ...block,
    diagram_type: (block.diagram_type || "mermaid_flowchart") as QueryDiagramBlock["diagram_type"],
    description: block.description ?? undefined,
    incomplete: false,
    graph: block.graph ?? null,
  } as QueryDiagramBlock;
}

function isDuplicatedInMarkdown(block: StructuredBlock, content: string): boolean {
  const source = content.trim();
  if (!source) return false;
  if (block.type === "chart") return /```(?:chart|json)\b/i.test(source);
  if (block.type === "diagram")
    return Boolean(block.syntax && source.includes(block.syntax.trim()));
  if (block.type === "table")
    return block.headers.length > 0 && source.includes(block.headers[0] ?? "\u0000");
  if (block.type === "card") {
    const cardContent = block.content.trim();
    return cardContent.length > 0 && source.includes(cardContent);
  }
  return false;
}

function safeExternalHref(value?: string | null): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    if (url.protocol !== "http:" && url.protocol !== "https:") return undefined;
    return url.href;
  } catch {
    return undefined;
  }
}

function downloadTextFile(content: string, label: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${slugify(label) || "download"}.txt`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80);
}
