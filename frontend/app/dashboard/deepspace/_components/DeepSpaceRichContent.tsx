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
import InfographicBlock from "../../query/_components/InfographicBlock";
import TableBlock from "../../query/_components/TableBlock";
import VisualIcon, {
  DetailVisualIcon,
  visualCardDetailSurfaceClasses,
  visualCardToneClasses,
  visualIconBadgeClasses,
} from "../../query/_components/VisualIcon";
import {
  CardLayoutAside,
  CardLayoutBody,
  CardSourceBadges,
} from "../../query/_components/CardLayoutContent";
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
  ) => void | boolean | StructuredBlock | Promise<void | boolean | StructuredBlock>;
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
                  onChange={async (next) => {
                    if (!messageId || !onVisualBlockChange) return undefined;
                    const saved = await onVisualBlockChange(
                      messageId,
                      fromQueryChartBlock(next, block),
                    );
                    return saved === false || typeof saved === "boolean" ? saved : undefined;
                  }}
                  onSaveArtifact={
                    onSaveVisualArtifact
                      ? (next) => onSaveVisualArtifact(fromQueryChartBlock(next, block))
                      : undefined
                  }
                />
              </VisualBlockExport>
            );
          case "card":
            return (
              <VisualBlockExport key={block.id} block={block}>
                <RichInfoCard
                  block={block}
                  onChange={
                    messageId && onVisualBlockChange
                      ? async (next) => {
                          const saved = await onVisualBlockChange(messageId, next);
                          if (
                            saved === false ||
                            saved === undefined ||
                            typeof saved === "boolean"
                          ) {
                            return saved;
                          }
                          return saved.type === "card" ? saved : next;
                        }
                      : undefined
                  }
                  onSaveArtifact={
                    onSaveVisualArtifact ? (next) => onSaveVisualArtifact(next) : undefined
                  }
                />
              </VisualBlockExport>
            );
          case "infographic":
            return (
              <VisualBlockExport key={block.id} block={block}>
                <InfographicBlock
                  block={block}
                  onChange={async (next) => {
                    if (!messageId || !onVisualBlockChange) return undefined;
                    const saved = await onVisualBlockChange(messageId, next);
                    if (saved === false || saved === undefined || typeof saved === "boolean") {
                      return saved;
                    }
                    return saved.type === "infographic" ? saved : next;
                  }}
                  onSaveArtifact={
                    onSaveVisualArtifact ? (next) => onSaveVisualArtifact(next) : undefined
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
                    if (!messageId || !onVisualBlockChange) return undefined;
                    return Promise.resolve(
                      onVisualBlockChange(messageId, fromQueryDiagramBlock(next, block)),
                    ).then((saved) => (saved === false ? false : undefined));
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
                  onSaveArtifact={
                    onSaveVisualArtifact
                      ? (next) => onSaveVisualArtifact({ ...block, ...next, type: "gallery" })
                      : undefined
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
  onChange?: (
    block: DeepSpaceCardBlock,
  ) => void | boolean | DeepSpaceCardBlock | Promise<void | boolean | DeepSpaceCardBlock>;
  onSaveArtifact?: (block: DeepSpaceCardBlock) => void | Promise<void>;
}) {
  const [copied, setCopied] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => JSON.stringify(block, null, 2));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const tone = block.tone ?? "neutral";
  const imageHref = safeExternalHref(block.image_url);
  const sourceHref = safeExternalHref(block.href);
  const layout = block.layout ?? "standard";

  const copyContent = async (value = block.content): Promise<boolean> => {
    setError(null);
    setStatus(null);
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
      return true;
    } catch (caught) {
      setCopied(false);
      setError(caught instanceof Error ? caught.message : "Card content could not be copied.");
      return false;
    }
  };

  const readDraft = (): DeepSpaceCardBlock => {
    let parsed: unknown;
    try {
      parsed = JSON.parse(draft);
    } catch {
      throw new Error("The card JSON is invalid. Fix it before saving.");
    }
    if (
      !parsed ||
      typeof parsed !== "object" ||
      (parsed as DeepSpaceCardBlock).id !== block.id ||
      (parsed as DeepSpaceCardBlock).type !== "card"
    ) {
      throw new Error("The card must keep its original ID and card type.");
    }
    return { ...(parsed as DeepSpaceCardBlock), revision: (block.revision ?? 0) + 1 };
  };

  const saveChanges = async () => {
    if (!onChange || saving) return;
    setError(null);
    setStatus(null);
    let next: DeepSpaceCardBlock;
    try {
      next = readDraft();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The card JSON is invalid.");
      return;
    }
    setSaving(true);
    try {
      const saved = await onChange(next);
      if (saved === false) {
        throw new Error(
          "This card changed in another session. Your draft is still open; retry after reviewing the latest version.",
        );
      }
      const persisted = saved && typeof saved === "object" && saved.type === "card" ? saved : next;
      setDraft(JSON.stringify(persisted, null, 2));
      setEditing(false);
      setStatus("Changes saved.");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The card changes could not be saved.");
    } finally {
      setSaving(false);
    }
  };

  const saveArtifact = async () => {
    if (!onSaveArtifact || saving) return;
    setError(null);
    setStatus(null);
    setSaving(true);
    try {
      let artifact = block;
      if (editing) {
        const next = readDraft();
        const saved = await onChange?.(next);
        if (saved === false) {
          throw new Error(
            "This card changed in another session. Your draft is still open; retry after reviewing the latest version.",
          );
        }
        artifact = saved && typeof saved === "object" && saved.type === "card" ? saved : next;
        setDraft(JSON.stringify(artifact, null, 2));
        setEditing(false);
      }
      await onSaveArtifact(artifact);
      setStatus("Saved to Library.");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "The card could not be saved to Library.",
      );
    } finally {
      setSaving(false);
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
      className={`deepspace-rich-card group relative overflow-hidden rounded-[1.5rem] border p-5 shadow-sm sm:p-6 ${visualCardToneClasses[tone]}`}
      data-card-layout={layout}
    >
      {!editing && layout === "feature" && imageHref ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={imageHref}
          alt={block.image_alt || block.title}
          loading="lazy"
          className="relative mb-5 max-h-72 w-full rounded-2xl border border-glass-border object-cover"
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
      ) : null}
      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          {imageHref && layout !== "feature" ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageHref}
              alt={block.image_alt || block.title}
              loading="lazy"
              className={`${layout === "place" ? "h-24 w-24 sm:h-32 sm:w-32" : "h-12 w-12"} shrink-0 rounded-xl border border-glass-border object-cover`}
              onError={(event) => {
                event.currentTarget.style.display = "none";
              }}
            />
          ) : (
            <div
              className={`${layout === "feature" ? "h-14 w-14" : "h-12 w-12"} flex shrink-0 items-center justify-center rounded-xl border shadow-sm ${visualIconBadgeClasses}`}
            >
              {block.icon ? (
                <VisualIcon name={block.icon} size={layout === "feature" ? 26 : 19} />
              ) : (
                <FileJson size={19} aria-hidden="true" />
              )}
            </div>
          )}
          <div className="min-w-0">
            <h3 className="text-foreground m-0 text-lg leading-tight font-semibold tracking-tight sm:text-xl">
              {block.title}
            </h3>
            {block.subtitle ? (
              <p className="text-foreground/75 dark:text-foreground/60 mt-1 max-w-xl text-sm leading-6 [text-wrap:pretty]">
                {block.subtitle}
              </p>
            ) : null}
          </div>
        </div>
        <div className="ml-auto flex min-w-0 max-w-full flex-wrap items-center justify-end gap-1 opacity-70 transition group-focus-within:opacity-100 group-hover:opacity-100">
          <CardLayoutAside block={block} onCopyCode={copyContent} />
          {onChange ? (
            <button
              type="button"
              onClick={() => {
                if (editing) void saveChanges();
                else {
                  setError(null);
                  setStatus(null);
                  setDraft(JSON.stringify(block, null, 2));
                  setEditing(true);
                }
              }}
              disabled={saving}
              aria-busy={saving}
              className="theme-chip inline-flex h-8 items-center gap-1 rounded-full px-2.5 text-[11px] disabled:opacity-50"
              aria-label={editing ? "Save card" : "Edit card"}
            >
              {editing ? <Save size={14} /> : <Pencil size={14} />}
              {editing && saving ? "Saving…" : null}
            </button>
          ) : null}
          {onSaveArtifact ? (
            <button
              type="button"
              onClick={() => void saveArtifact()}
              disabled={saving}
              aria-busy={saving}
              aria-label="Save card to Library"
              className="theme-chip inline-flex h-8 items-center rounded-full px-2.5 text-[11px] disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save"}
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
          disabled={saving}
          aria-label="Edit card fields as JSON"
          className="border-glass-border bg-background/60 text-foreground relative mt-4 min-h-52 w-full rounded-xl border p-3 font-mono text-xs leading-5"
        />
      ) : null}
      {error ? (
        <p className="relative mt-3 text-xs text-rose-600 dark:text-rose-300" role="alert">
          {error}
        </p>
      ) : null}
      {status ? (
        <p
          className="relative mt-3 text-xs text-emerald-700 dark:text-emerald-300"
          role="status"
          aria-live="polite"
        >
          {status}
        </p>
      ) : null}
      {!editing ? <CardLayoutBody block={block} /> : null}
      {!editing && block.content.trim() ? <div
        className={
          "relative mt-4 max-w-3xl text-sm leading-6 [text-wrap:pretty]"
        }
      >
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
      </div> : null}

      {!editing && layout !== "evaluation" && layout !== "referral" && block.details?.length ? (
        <dl className="relative mt-6 grid auto-rows-fr items-stretch gap-3 sm:grid-cols-2">
          {block.details.map((detail, index) => {
            const href = safeExternalHref(detail.href);
            return (
              <div
                key={`${detail.label}-${index}`}
                className={`flex h-full min-h-20 min-w-0 items-start gap-3 rounded-2xl border px-4 py-3 ${visualCardDetailSurfaceClasses}`}
              >
                <span
                  className={`mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-xl border shadow-sm ${visualIconBadgeClasses}`}
                  data-card-detail-icon
                >
                  <DetailVisualIcon name={detail.icon} label={detail.label} size={17} />
                </span>
                <div className="min-w-0">
                  <dt className="text-foreground/70 dark:text-foreground/65 text-[11px] leading-4 font-semibold tracking-[0.14em] uppercase">
                    {detail.label}
                  </dt>
                  <dd className="text-foreground/90 m-0 mt-1.5 text-sm leading-6 [text-wrap:pretty] [overflow-wrap:anywhere] break-words">
                    {href ? (
                      <a
                        href={href}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="underline underline-offset-2"
                      >
                        {detail.value}
                      </a>
                    ) : (
                      detail.value
                    )}
                  </dd>
                </div>
              </div>
            );
          })}
        </dl>
      ) : null}

      {!editing && layout !== "evaluation" && layout !== "referral" && block.metrics?.length ? (
        <div className="relative mt-6 grid items-stretch gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {block.metrics.map((metric) => (
            <div
              key={`${metric.label}-${String(metric.value)}`}
                className={`h-full rounded-2xl border px-4 py-3 ${visualCardDetailSurfaceClasses}`}
            >
              <div className="text-foreground/70 dark:text-foreground/65 text-[11px] leading-4 font-semibold tracking-[0.14em] uppercase">
                {metric.label}
              </div>
              <div className="text-foreground mt-1.5 text-xl leading-tight font-semibold tracking-tight tabular-nums">
                {String(metric.value)}
              </div>
              {metric.detail ? (
                <div className="text-foreground/75 dark:text-foreground/65 mt-1 text-sm leading-5 [text-wrap:pretty]">
                  {metric.detail}
                </div>
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
          className="text-primary decoration-primary/35 relative mt-5 inline-flex items-center gap-2 text-xs font-semibold tracking-[0.14em] uppercase underline underline-offset-4"
        >
          Open source <Link2 size={13} aria-hidden="true" />
        </a>
      ) : null}

      {!editing && (layout === "evaluation" || layout === "referral") ? (
        <CardSourceBadges block={block} />
      ) : !editing && block.sources?.length ? (
        <div className="border-glass-border relative mt-5 flex flex-wrap gap-x-4 gap-y-2 border-t pt-4 text-[11px]">
          {block.sources.map((source, index) => {
            const href = safeExternalHref(source.url);
            return href ? (
              <a
                key={`${source.url}-${index}`}
                href={href}
                target="_blank"
                rel="noreferrer noopener"
                className="text-primary underline decoration-primary/40 underline-offset-4 hover:text-primary/80"
              >
                {source.title}
              </a>
            ) : null;
          })}
        </div>
      ) : null}

      {block.actions?.length ? (
        <div className="border-glass-border relative mt-5 flex flex-wrap gap-2 border-t pt-4">
          {block.actions.map((action) => (
            <CardActionButton
              key={`${action.label}-${action.href ?? action.action ?? ""}`}
              action={action}
              onCopy={(value) => copyContent(value).then(() => undefined)}
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
  if (block.type === "infographic") return /```infographic\b/i.test(source);
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
