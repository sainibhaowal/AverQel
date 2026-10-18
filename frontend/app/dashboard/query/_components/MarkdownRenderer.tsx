"use client";

import { useMemo, type ReactNode } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import InlineCitation from "@/app/components/query/InlineCitation";

import { parseVisualChart } from "../_lib/chart-parser";
import type {
  StreamCardBlock,
  StreamChartBlock,
  StreamChartPoint,
  StreamDiagramBlock,
} from "../_lib/stream-protocol";
import { normalizeMarkdown } from "../_lib/markdown";
import AdaptiveMarkdownTable from "../../_components/AdaptiveMarkdownTable";

import ChartBlock from "./ChartBlock";
import CodeBlock from "./CodeBlock";
import CardBlock from "./CardBlock";
import GraphBlock from "./GraphBlock";
import GalleryBlock, { parseGalleryPayload } from "./GalleryBlock";
import {
  inferVisualFenceKind,
  normalizePersistedRichContent,
  unwrapPersistedVisualFence,
} from "../_lib/visual-fences";

function QueryTableHeader({ children }: { children?: ReactNode }) {
  return <th className="px-5 py-3.5">{children}</th>;
}
QueryTableHeader.displayName = "th";

function QueryTableCell({ children }: { children?: ReactNode }) {
  return (
    <td className="border-glass-border/10 text-foreground/80 border-b px-5 py-3.5 text-sm">
      {children}
    </td>
  );
}
QueryTableCell.displayName = "td";

interface MarkdownRendererProps {
  content: string;
  streaming?: boolean;
  messageId?: string;
  enableRichPreview?: boolean;
}

/**
 * The single answer-content renderer.
 *
 * Markdown owns text, tables, lists, images, and fenced code. The only
 * custom fence is `chart`, which is promoted to the existing chart component.
 * Mermaid remains a normal fenced code block and is previewed by CodeBlock.
 */
export default function MarkdownRenderer({
  content,
  streaming = false,
  messageId = "message",
  enableRichPreview = true,
}: MarkdownRendererProps) {
  const normalizedContent = useMemo(
    () => normalizeMarkdown(normalizePersistedRichContent(content)),
    [content],
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

        if (!streaming && visualLanguage === "mermaid" && visualValue.trim()) {
          return (
            <CodeBlock
              language="mermaid"
              value={visualValue}
              enableRichPreview={enableRichPreview}
              defaultPreviewOpen={enableRichPreview}
            />
          );
        }

        const chartBlock =
          enableRichPreview && isChartFence(visualLanguage, visualValue)
            ? createChartBlock(visualValue, `${messageId}-chart`)
            : null;

        if (chartBlock) {
          return <ChartBlock block={chartBlock} />;
        }

        if (!streaming && visualLanguage === "card") {
          const card = createCardBlock(visualValue, `${messageId}-card`);
          if (card) return <CardBlock block={card} />;
        }
        if (!streaming && visualLanguage === "graph") {
          const graph = createGraphBlock(visualValue, `${messageId}-graph`);
          if (graph) return <GraphBlock block={graph as never} />;
        }
        if (!streaming && visualLanguage === "gallery") {
          const gallery = parseGalleryPayload(visualValue);
          if (gallery) return <GalleryBlock payload={gallery} />;
        }

        return (
          <CodeBlock
            language={language || undefined}
            value={value}
            incomplete={streaming}
            enableRichPreview={enableRichPreview}
            answerStreaming={streaming}
            defaultPreviewOpen={enableRichPreview && language === "mermaid"}
          />
        );
      },
      table: ({ children }) => <AdaptiveMarkdownTable>{children}</AdaptiveMarkdownTable>,
      thead: ({ children }) => (
        <thead className="border-glass-border/30 bg-primary/5 text-primary border-b text-[11px] font-bold tracking-widest uppercase">
          {children}
        </thead>
      ),
      th: QueryTableHeader,
      td: QueryTableCell,
      h1: ({ children }) => <h1 className="text-foreground text-3xl font-semibold">{children}</h1>,
      h2: ({ children }) => <h2 className="text-foreground text-2xl font-semibold">{children}</h2>,
      h3: ({ children }) => <h3 className="text-foreground text-xl font-semibold">{children}</h3>,
      h4: ({ children }) => <h4 className="text-foreground text-lg font-semibold">{children}</h4>,
      h5: ({ children }) => <h5 className="text-foreground text-base font-semibold">{children}</h5>,
      h6: ({ children }) => <h6 className="text-foreground text-sm font-semibold">{children}</h6>,
      p: ({ children }) => <p className="text-foreground/90 leading-8">{children}</p>,
      blockquote: ({ children }) => (
        <blockquote className="border-primary/45 bg-primary/5 rounded-r-2xl border-l-2 px-4 py-3">
          {children}
        </blockquote>
      ),
      ul: ({ children }) => <ul className="my-2 list-disc space-y-2 pl-5">{children}</ul>,
      ol: ({ children }) => <ol className="my-2 list-decimal space-y-2 pl-5">{children}</ol>,
      li: ({ children, className }) => (
        <li
          className={`${className?.includes("task-list-item") ? "list-none pl-0" : ""} leading-7`}
        >
          {children}
        </li>
      ),
      input: ({ type, checked, ...props }) =>
        type === "checkbox" ? (
          <input
            type="checkbox"
            checked={Boolean(checked)}
            readOnly
            tabIndex={-1}
            aria-hidden="true"
            className="mr-2 h-4 w-4 translate-y-[1px] rounded border border-cyan-400/35 bg-slate-950/90 align-middle text-cyan-400 accent-cyan-400"
            {...props}
          />
        ) : (
          <input type={type} {...props} />
        ),
      a: ({ href, children, ...props }) => {
        if (href?.startsWith("#citation-")) {
          const index = Number.parseInt(href.replace("#citation-", ""), 10);
          if (!Number.isNaN(index)) return <InlineCitation index={index} />;
        }
        const external = typeof href === "string" && !href.startsWith("#");
        return (
          <a
            href={href}
            target={external ? "_blank" : undefined}
            rel={external ? "noreferrer noopener" : undefined}
            className="text-primary decoration-primary/30 underline underline-offset-4"
            {...props}
          >
            {children}
          </a>
        );
      },
      img: ({ src, alt, ...props }) => (
        <span
          className="my-3 block overflow-hidden rounded-2xl border border-white/10 bg-black/20"
          data-markdown-image
        >
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={src ?? ""}
            alt={alt ?? ""}
            loading="lazy"
            decoding="async"
            {...props}
            onError={(event) => {
              event.currentTarget.hidden = true;
              event.currentTarget.nextElementSibling?.removeAttribute("hidden");
            }}
          />
          <span hidden className="text-foreground/55 block px-3 py-2 text-xs">
            Image unavailable at this URL.
          </span>
        </span>
      ),
      strong: ({ children }) => (
        <strong className="text-foreground font-semibold">{children}</strong>
      ),
      em: ({ children }) => <em className="italic">{children}</em>,
      del: ({ children }) => (
        <del className="text-muted-foreground/80 line-through">{children}</del>
      ),
      hr: () => <hr className="border-glass-border/25" />,
    }),
    [enableRichPreview, messageId, streaming],
  );

  return (
    <div
      className={`chat-message-container ${streaming ? "is-streaming" : ""} prose dark:prose-invert max-w-none text-[15px] leading-8`}
    >
      <ReactMarkdown
        // Do not run KaTeX against untrusted model output. Prices and copied
        // LaTeX frequently share the same delimiters and must never be able
        // to crash the complete chat surface.
        remarkPlugins={[[remarkGfm, { autoLinkLiterals: false }]]}
        components={components}
      >
        {normalizedContent}
      </ReactMarkdown>
      {streaming ? (
        <div className="text-foreground/35 mt-4 animate-pulse text-[11px] tracking-[0.18em] uppercase">
          Intelligence Streaming...
        </div>
      ) : null}
    </div>
  );
}

function createCardBlock(value: string, id: string): StreamCardBlock | null {
  try {
    const payload = JSON.parse(value) as Record<string, unknown>;
    if (!payload || Array.isArray(payload)) return null;
    const title =
      typeof payload.title === "string" && payload.title.trim()
        ? payload.title
        : "Information card";
    const content =
      typeof payload.content === "string" ? payload.content : String(payload.body ?? "");
    if (!content.trim()) return null;
    const tone = payload.tone;
    return {
      id,
      type: "card",
      title,
      content,
      tone:
        tone === "info" ||
        tone === "success" ||
        tone === "warning" ||
        tone === "error" ||
        tone === "neutral"
          ? tone
          : "neutral",
      subtitle: typeof payload.subtitle === "string" ? payload.subtitle : null,
      image_url: typeof payload.image_url === "string" ? payload.image_url : null,
      href: typeof payload.href === "string" ? payload.href : null,
      metrics: Array.isArray(payload.metrics)
        ? payload.metrics
            .filter(
              (
                metric,
              ): metric is { label: string; value: string | number; detail?: string | null } =>
                Boolean(
                  metric &&
                  typeof metric === "object" &&
                  typeof (metric as Record<string, unknown>).label === "string",
                ),
            )
            .map((metric) => ({
              label: metric.label,
              value: metric.value ?? "",
              detail: metric.detail ?? null,
            }))
        : [],
      actions: Array.isArray(payload.actions)
        ? payload.actions
            .filter(
              (
                action,
              ): action is {
                label: string;
                href?: string | null;
                action?: "open" | "copy" | "download";
                content?: string | null;
              } =>
                Boolean(
                  action &&
                  typeof action === "object" &&
                  typeof (action as Record<string, unknown>).label === "string",
                ),
            )
            .map((action) => ({
              label: action.label,
              href: action.href ?? null,
              action: action.action ?? "open",
              content: action.content ?? null,
            }))
        : [],
    };
  } catch {
    return null;
  }
}

function createGraphBlock(value: string, id: string): StreamDiagramBlock | null {
  try {
    const payload = JSON.parse(value) as Record<string, unknown>;
    const graph = (
      payload.graph && typeof payload.graph === "object" ? payload.graph : payload
    ) as StreamDiagramBlock["graph"];
    if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) return null;
    return {
      id,
      type: "diagram",
      title: typeof payload.title === "string" ? payload.title : "Diagram canvas",
      diagram_type: "graph_canvas",
      source: "graph_json",
      syntax: value,
      graph,
    };
  } catch {
    return null;
  }
}

function isChartFence(language: string, value: string): boolean {
  if (language === "chart") return true;
  return language === "json" && /"(?:chart_type|series|chart_data|chartData)"\s*:/.test(value);
}

function createChartBlock(value: string, id: string): StreamChartBlock | null {
  const parsed = parseVisualChart(value, "chart");
  if (!parsed || parsed.data.length < 2) return null;

  return {
    id,
    type: "chart",
    title: parsed.title,
    chart_type: parsed.type,
    series: parsed.data.map(
      (point): StreamChartPoint => ({
        ...point,
        label: String(point[parsed.xKey] ?? point.label ?? ""),
        value: Number(point[parsed.yKey] ?? point.value ?? 0),
        ...(parsed.zKey ? { z: Number(point[parsed.zKey]) } : {}),
      }),
    ),
    raw_payload: value,
    parser_source: parsed.metadata.source,
    confidence: parsed.metadata.confidence,
    fields: parsed.metadata.fields,
    is_streaming: false,
    x_key: parsed.xKey,
    y_key: parsed.yKey,
    z_key: parsed.zKey,
    x_label: parsed.xLabel,
    y_label: parsed.yLabel,
  };
}
