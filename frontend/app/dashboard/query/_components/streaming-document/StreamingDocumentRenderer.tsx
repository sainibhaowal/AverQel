"use client";

import { FileJson } from "lucide-react";

import type {
  StreamingChartNode,
  StreamingFootnoteNode,
  StreamingDocumentNode,
  StreamingImageNode,
  StreamingListItem,
  StreamingListNode,
  StreamingTableNode,
} from "@/app/dashboard/query/_lib/streaming-document-types";

import ChartBlock from "../ChartBlock";
import CodeBlock from "../CodeBlock";
import TableBlock from "../TableBlock";
import { InlineMarkdown } from "../InlineMarkdown";
import MathMessageBlock from "../MathMessageBlock";

interface StreamingDocumentRendererProps {
  nodes: StreamingDocumentNode[];
  isStreaming?: boolean;
  enableRichPreview?: boolean;
}

export default function StreamingDocumentRenderer({
  nodes,
  isStreaming = false,
  enableRichPreview = true,
}: StreamingDocumentRendererProps) {
  // ── Stable key computation ─────────────────────────────────────────────
  // Tables: keyed by header fingerprint (stable once headers arrive).
  // Charts: keyed by ordinal position among chart nodes only (chart-0,
  //   chart-1…). This is always stable — charts only append, never insert,
  //   so chart-0 is always the first chart regardless of how many text nodes
  //   appear above it. A payload-fingerprint key was tried first but it
  //   changes character-by-character during skeleton phase → key instability.
  // All other nodes: type + global index (stable because nodes only append).

  // Pre-compute chart ordinals in a single pass (O(n), done before render).
  const chartOrdinals = (() => {
    const ordinals = new Map<number, number>();
    let count = 0;
    nodes.forEach((n, i) => {
      if (n.type === "chart") ordinals.set(i, count++);
    });
    return ordinals;
  })();

  const stableKey = (node: StreamingDocumentNode, index: number): string => {
    if (node.type === "table") {
      const headerFingerprint = node.headers.join("\x00");
      return headerFingerprint.length > 0 ? `table-${headerFingerprint}` : `table-${index}`;
    }
    if (node.type === "chart") {
      const ordinal = chartOrdinals.get(index) ?? index;
      return `chart-${ordinal}`;
    }
    return `${node.type}-${index}`;
  };

  const renderList = (node: StreamingListNode, key: string, depth = 0, streamingKey?: string) => {
    const listClass = node.ordered
      ? "text-foreground/84 list-decimal space-y-2.5 pl-6 text-[15px] leading-8 sm:text-[15.5px] sm:leading-[2rem]"
      : "text-foreground/84 list-disc space-y-2.5 pl-6 text-[15px] leading-8 sm:text-[15.5px] sm:leading-[2rem]";

    const ListTag = node.ordered ? "ol" : "ul";
    return (
      <ListTag key={key} className={`${listClass} ${streamingKey ?? ""}`}>
        {node.items.map((item, itemIndex) => renderListItem(item, `${key}-${itemIndex}`, depth))}
      </ListTag>
    );
  };

  const renderListItem = (item: StreamingListItem, key: string, depth: number) => {
    const isTask = Boolean(item.task);
    return (
      <li key={key} className={`pl-1 ${isTask ? "list-none pl-0" : ""}`}>
        {isTask ? (
          <span className="flex items-start gap-3">
            <input
              type="checkbox"
              checked={Boolean(item.checked)}
              readOnly
              tabIndex={-1}
              aria-hidden="true"
              className="mt-1 h-4 w-4 shrink-0 rounded border border-cyan-400/35 bg-slate-950/90 text-cyan-400 accent-cyan-400"
            />
            <span className="min-w-0 flex-1">
              <InlineMarkdown content={item.content} />
            </span>
          </span>
        ) : (
          <InlineMarkdown content={item.content} />
        )}

        {item.children?.length ? (
          <div className={`mt-2 space-y-2 ${depth >= 1 ? "pl-5" : "pl-4"}`}>
            {item.children.map((child, childIndex) =>
              renderList(child, `${key}-child-${childIndex}`, depth + 1, ""),
            )}
          </div>
        ) : null}
      </li>
    );
  };

  return (
    <div className="space-y-5">
      {nodes.map((node, index) => {
        const key = stableKey(node, index);
        const isLastNode = index === nodes.length - 1;
        const streamingClass = isStreaming && isLastNode ? "is-streaming-text" : "";

        switch (node.type) {
          case "heading": {
            if (node.depth === 1) {
              return (
                <h1
                  key={key}
                  className={`text-foreground text-[1.92rem] font-semibold tracking-[-0.04em] sm:text-[2.1rem] ${streamingClass}`}
                >
                  <InlineMarkdown content={node.content} />
                </h1>
              );
            }
            if (node.depth === 2) {
              return (
                <h2
                  key={key}
                  className={`text-foreground text-[1.45rem] font-semibold tracking-[-0.032em] sm:text-[1.6rem] ${streamingClass}`}
                >
                  <InlineMarkdown content={node.content} />
                </h2>
              );
            }
            if (node.depth === 3) {
              return (
                <h3
                  key={key}
                  className={`text-foreground text-[1.08rem] font-semibold tracking-[-0.025em] sm:text-[1.16rem] ${streamingClass}`}
                >
                  <InlineMarkdown content={node.content} />
                </h3>
              );
            }
            if (node.depth === 4) {
              return (
                <h4
                  key={key}
                  className={`text-foreground text-[1rem] font-semibold tracking-[-0.02em] ${streamingClass}`}
                >
                  <InlineMarkdown content={node.content} />
                </h4>
              );
            }
            if (node.depth === 5) {
              return (
                <h5
                  key={key}
                  className={`text-primary text-[0.94rem] font-semibold tracking-[0.04em] uppercase ${streamingClass}`}
                >
                  <InlineMarkdown content={node.content} />
                </h5>
              );
            }
            return (
              <h6
                key={key}
                className={`text-foreground/82 text-[0.9rem] font-semibold tracking-tight ${streamingClass}`}
              >
                <InlineMarkdown content={node.content} />
              </h6>
            );
          }

          case "paragraph": {
            return (
              <div
                key={key}
                className={`text-foreground/86 text-[15px] leading-8 sm:text-[15.5px] sm:leading-[2rem] ${
                  isStreaming && isLastNode ? "is-streaming-text" : ""
                }`}
              >
                <InlineMarkdown content={node.content} />
              </div>
            );
          }

          case "blockquote": {
            return (
              <blockquote
                key={key}
                className={`border-primary/45 bg-primary/5 text-foreground/88 rounded-r-2xl border-l-2 px-4 py-3 text-[15px] leading-8 sm:px-5 sm:text-[15.5px] sm:leading-[2rem] ${
                  isStreaming && isLastNode ? "is-streaming-text" : ""
                }`}
              >
                <InlineMarkdown content={node.content} />
              </blockquote>
            );
          }

          case "image": {
            const imageNode = node as StreamingImageNode;
            return (
              <figure
                key={key}
                className={`not-prose my-4 overflow-hidden rounded-2xl border border-white/10 bg-black/20 ${
                  isStreaming && isLastNode ? "is-streaming-text" : ""
                }`}
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={imageNode.src}
                  alt={imageNode.alt ?? ""}
                  title={imageNode.title}
                  loading="lazy"
                  decoding="async"
                  className="block h-auto w-full max-w-full"
                />
                {imageNode.alt || imageNode.title ? (
                  <figcaption className="text-foreground/58 border-t border-white/10 px-4 py-3 text-[12px] leading-6">
                    {imageNode.alt ?? imageNode.title ?? ""}
                  </figcaption>
                ) : null}
              </figure>
            );
          }

          case "footnote": {
            const footnoteNode = node as StreamingFootnoteNode;
            return (
              <section
                key={key}
                className={`border-primary/20 bg-primary/5 text-foreground/86 rounded-2xl border px-4 py-4 text-[14px] leading-7 sm:px-5 ${
                  isStreaming && isLastNode ? "is-streaming-text" : ""
                }`}
              >
                <div className="text-primary/75 mb-2 text-[10px] font-semibold tracking-[0.18em] uppercase">
                  {`Footnote [^${footnoteNode.identifier}]`}
                </div>
                <InlineMarkdown content={footnoteNode.content} />
              </section>
            );
          }

          case "list":
            return renderList(node, key, 0, isStreaming && isLastNode ? "is-streaming-text" : "");

          case "table":
            return (
              <TableBlock key={key} isStreaming={isStreaming} block={node as StreamingTableNode} />
            );

          case "code":
            return (
              <CodeBlock
                key={key}
                language={node.language}
                value={node.value}
                incomplete={node.incomplete}
                enableRichPreview={enableRichPreview && node.language?.toLowerCase() === "mermaid"}
                answerStreaming={isStreaming}
                defaultPreviewOpen={enableRichPreview && node.language?.toLowerCase() === "mermaid"}
              />
            );

          case "chart": {
            if (!enableRichPreview) {
              return (
                <CodeBlock
                  key={key}
                  language="json"
                  value={node.raw_payload ?? ""}
                  incomplete={node.incomplete}
                  enableRichPreview={false}
                  answerStreaming={isStreaming}
                  defaultPreviewOpen={false}
                />
              );
            }
            // ── Inline chart ───────────────────────────────────────────────
            // Mermaid-style: raw payload text while streaming, full visual
            // after the fence closes. Stabilized with fixed height to prevent
            // "jumping" layout shifts.
            if (node.incomplete) {
              return (
                <div
                  key={key}
                  className="theme-panel w-full overflow-hidden rounded-[1.8rem] shadow-[0_24px_70px_-44px_rgba(8,47,73,0.16)] dark:shadow-[0_24px_70px_-44px_rgba(8,47,73,0.82)]"
                >
                  <div className="border-b border-black/5 px-5 py-4 sm:px-6 dark:border-white/8">
                    <div className="flex items-center gap-3">
                      <div className="bg-primary/10 border-primary/15 text-primary flex h-10 w-10 items-center justify-center rounded-2xl border">
                        <FileJson className="h-5 w-5 animate-pulse" />
                      </div>
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <h4 className="text-foreground text-[15px] font-semibold tracking-[-0.015em]">
                            Generating Chart...
                          </h4>
                          <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-[10px] font-semibold tracking-[0.16em] text-amber-700 uppercase dark:text-amber-200">
                            live
                          </span>
                        </div>
                        <div className="text-foreground/40 text-[10px] tracking-tight">
                          Analyzing structural data stream...
                        </div>
                      </div>
                    </div>
                  </div>
                  <div className="flex max-h-[420px] min-h-[380px] flex-col overflow-hidden bg-black/[0.02] p-4 sm:p-6 dark:bg-white/[0.01]">
                    <div className="bg-background/40 relative flex-1 overflow-hidden rounded-[1.3rem] border border-black/8 dark:border-white/10">
                      <pre className="scrollbar-thin scrollbar-thumb-white/10 text-primary absolute inset-0 overflow-y-auto px-4 py-4 font-mono text-[12px] leading-[1.8] opacity-90">
                        {node.raw_payload ?? ""}
                      </pre>
                    </div>
                  </div>
                  <div className="border-t border-black/5 px-5 py-3 dark:border-white/8">
                    <div className="text-foreground/40 flex items-center gap-2 text-[10px] tracking-widest uppercase">
                      <div className="h-1.5 w-1.5 animate-ping rounded-full bg-amber-500" />
                      Processing tokens
                    </div>
                  </div>
                </div>
              );
            }

            // Fence closed — render the fully-interactive chart HUD inline.
            const chartBlock = node as StreamingChartNode;
            return (
              <ChartBlock
                key={key}
                block={{
                  id: key,
                  type: "chart",
                  title: chartBlock.title ?? null,
                  chart_type: chartBlock.chart_type,
                  series: chartBlock.series,
                  raw_payload: chartBlock.raw_payload ?? null,
                  parser_source: chartBlock.parser_source,
                  confidence: chartBlock.confidence,
                  fields: chartBlock.fields,
                  x_key: chartBlock.x_key,
                  y_key: chartBlock.y_key,
                  z_key: chartBlock.z_key,
                  is_streaming: false,
                }}
              />
            );
          }

          case "math":
            return <MathMessageBlock key={key} value={node.value} incomplete={node.incomplete} />;

          case "rule":
            return <hr key={key} className="border-glass-border/25" />;

          default:
            return null;
        }
      })}
    </div>
  );
}
