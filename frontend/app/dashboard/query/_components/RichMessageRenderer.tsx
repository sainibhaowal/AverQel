"use client";

import { memo } from "react";

import FeedbackActions from "@/app/components/query/FeedbackActions";
import FollowUpSuggestions from "@/app/components/query/FollowUpSuggestions";
import ReasoningTrace from "@/app/components/query/ReasoningTrace";
import ReferenceTiles from "@/app/components/query/ReferenceTiles";

import { normalizeMarkdown } from "../_lib/markdown";
import type { QueryThreadMessage, StructuredBlock } from "../_lib/stream-protocol";

import ArtifactsPanel from "./ArtifactsPanel";
import MarkdownRenderer from "./MarkdownRenderer";
import StatusHistoryPanel from "./StatusHistoryPanel";
import StructuredBlockRenderer from "./StructuredBlockRenderer";

interface RichMessageRendererProps {
  mode?: "query" | "deepspace";
  message: QueryThreadMessage;
  isStreaming: boolean;
  onPreviewDocument: (payload: { id: string; name: string; page?: number }) => void;
  onFollowupSelect: (query: string) => void;
}

/**
 * Composes message metadata around the one Markdown renderer.
 *
 * Structured blocks are retained as a transport fallback for responses where
 * the backend sends a chart/table/diagram separately. If the same content is
 * already present as Markdown, the Markdown version is the only one rendered.
 */
function RichMessageRenderer({
  mode = "query",
  message,
  isStreaming,
  onPreviewDocument,
  onFollowupSelect,
}: RichMessageRendererProps) {
  const showWorkflowMeta = mode !== "deepspace";
  const displayBlocks = resolveDisplayBlocks(message);
  const displayContent = stripTransportContent(message.content, displayBlocks);
  const legacySummary = parseLegacySummary(displayContent);
  const readableContent = legacySummary ? "" : displayContent;
  const suppressStreamingJson = isStreaming && looksLikeStructuredJson(displayContent);
  const hasMarkdownContent = !suppressStreamingJson && readableContent.trim().length > 0;
  const hasRenderableContent = hasMarkdownContent || Boolean(legacySummary);

  return (
    <div className="min-w-0 space-y-8 overflow-hidden sm:space-y-9">
      {legacySummary ? <LegacySummaryPanel summary={legacySummary} /> : null}
      {hasMarkdownContent ? (
        <MarkdownRenderer
          content={readableContent}
          streaming={isStreaming}
          messageId={message.id}
        />
      ) : null}

      {message.artifacts.length > 0 || message.files.length > 0 ? (
        <ArtifactsPanel artifacts={message.artifacts} files={message.files} />
      ) : null}

      <StructuredBlockRenderer blocks={displayBlocks} isStreaming={isStreaming} />

      {showWorkflowMeta && !isStreaming && message.statusHistory.length > 0 ? (
        <StatusHistoryPanel entries={message.statusHistory} isStreaming={isStreaming} />
      ) : null}

      {showWorkflowMeta && !isStreaming && message.citations.length > 0 ? (
        <div className="border-glass-border border-t pt-6">
          <ReferenceTiles
            citations={message.citations.map((citation) => ({
              document_id: citation.document_id,
              filename: citation.filename,
              page_number: citation.page_number ?? undefined,
            }))}
            onTileClick={(citation) =>
              onPreviewDocument({
                id: citation.document_id,
                name: citation.filename || "Document",
                page: citation.page_number,
              })
            }
          />
        </div>
      ) : null}

      {showWorkflowMeta && !isStreaming && message.trace ? (
        <div className="border-glass-border border-t pt-6">
          <ReasoningTrace trace={message.trace} confidence={message.confidence} />
        </div>
      ) : null}

      {showWorkflowMeta && !isStreaming && message.followups.length > 0 ? (
        <div className="border-glass-border border-t pt-6">
          <FollowUpSuggestions suggestions={message.followups} onSelect={onFollowupSelect} />
        </div>
      ) : null}

      {!isStreaming && hasRenderableContent && mode !== "deepspace" ? (
        <div className="border-glass-border border-t pt-4">
          <FeedbackActions messageId={message.id} content={message.content} />
        </div>
      ) : null}
    </div>
  );
}

export default memo(RichMessageRenderer);

type LegacySummary =
  | {
      kind: "comparison";
      heading: string;
      highlights: string[];
      documents: Array<{ name: string; summary: string; details: string[] }>;
    }
  | {
      kind: "evidence";
      heading: string;
      document: string;
      status: string;
      evidence: string[];
    }
  | {
      kind: "collection";
      collection: string;
      metrics: string[];
      documents: string[];
    };

/**
 * Older provider responses sometimes contain the same structured summaries
 * as plain text instead of the structured transport envelope. Keep those
 * responses useful by promoting only the three distinctive, server-generated
 * formats to the same visual panel used by structured results. Ordinary
 * Markdown is left completely unchanged.
 */
function parseLegacySummary(content: string): LegacySummary | null {
  const lines = content.split("\n");
  const first = lines[0]?.trim() ?? "";

  if (/^Compared \d+ documents across\b/i.test(first)) {
    const documents: Array<{ name: string; summary: string; details: string[] }> = [];
    const highlights: string[] = [];
    let current: (typeof documents)[number] | null = null;
    for (const line of lines.slice(1)) {
      const document = line.match(/^\s*-\s+([^:]+):\s*(.+)$/);
      if (document) {
        current = { name: document[1]!.trim(), summary: document[2]!.trim(), details: [] };
        documents.push(current);
        continue;
      }
      if (!current && line.trim()) {
        highlights.push(line.trim());
        continue;
      }
      const detail = line.match(/^\s{2,}(.+?)\s*$/);
      if (detail && current) current.details.push(detail[1]!.trim());
    }
    if (documents.length > 0) return { kind: "comparison", heading: first, highlights, documents };
  }

  const evidenceHeading = first.match(
    /^Documents matching\s+(.+?)\s+in the filtered workspace slice/i,
  );
  if (evidenceHeading) {
    const document = lines
      .slice(1)
      .map((line) => line.match(/^\s*-\s+(.+?)\s+\(([^)]+)\)\s*$/))
      .find(Boolean);
    if (document) {
      const evidence = lines
        .slice(1)
        .map((line) => line.match(/^\s+Evidence\s+(.+?)\s*$/i)?.[1]?.trim())
        .filter((value): value is string => Boolean(value));
      return {
        kind: "evidence",
        heading: first,
        document: document[1]!.trim(),
        status: document[2]!.trim(),
        evidence,
      };
    }
  }

  const collectionHeading = first.match(/^Collection summary for\s+(.+?):\s*$/i);
  if (collectionHeading) {
    const documentsIndex = lines.findIndex((line) => /^Documents:\s*$/i.test(line.trim()));
    const metricLines = (documentsIndex === -1 ? lines.slice(1) : lines.slice(1, documentsIndex))
      .map((line) => line.match(/^\s*-\s+(.+)$/)?.[1]?.trim())
      .filter((value): value is string => Boolean(value));
    const documents = (documentsIndex === -1 ? [] : lines.slice(documentsIndex + 1))
      .map((line) => line.match(/^\s*-\s+(.+)$/)?.[1]?.trim())
      .filter((value): value is string => Boolean(value));
    return {
      kind: "collection",
      collection: collectionHeading[1]!.trim(),
      metrics: metricLines,
      documents,
    };
  }

  return null;
}

function LegacySummaryPanel({ summary }: { summary: LegacySummary }) {
  if (summary.kind === "comparison") {
    return (
      <section className="border-glass-border/60 bg-glass-bg/30 rounded-2xl border p-4 shadow-sm sm:p-5">
        <div className="text-primary mb-4 text-xs font-semibold tracking-[0.16em] uppercase">
          Comparison
        </div>
        <p className="text-foreground/90 text-sm leading-7">{summary.heading}</p>
        {summary.highlights.length > 0 ? (
          <ul className="text-foreground/75 mt-2 space-y-1 text-sm leading-6">
            {summary.highlights.map((highlight) => (
              <li key={highlight}>{highlight}</li>
            ))}
          </ul>
        ) : null}
        <div className="grid gap-3 md:grid-cols-2">
          {summary.documents.map((document) => (
            <article
              key={document.name}
              className="border-glass-border/50 bg-surface-1/30 rounded-xl border p-3"
            >
              <h3 className="text-foreground text-sm font-semibold">{document.name}</h3>
              <p className="text-foreground/75 mt-1 text-xs leading-6">{document.summary}</p>
              {document.details.length > 0 ? (
                <ul className="text-foreground/65 mt-2 space-y-1 text-xs leading-5">
                  {document.details.map((detail) => (
                    <li key={detail}>{detail}</li>
                  ))}
                </ul>
              ) : null}
            </article>
          ))}
        </div>
      </section>
    );
  }

  if (summary.kind === "evidence") {
    return (
      <section className="border-glass-border/60 bg-glass-bg/30 rounded-2xl border p-4 shadow-sm sm:p-5">
        <div className="text-primary mb-3 text-xs font-semibold tracking-[0.16em] uppercase">
          Investigation Evidence
        </div>
        <p className="text-foreground/90 text-sm leading-7">{summary.heading}</p>
        <div className="border-glass-border/50 bg-surface-1/30 mt-4 rounded-xl border p-3">
          <div className="text-foreground text-sm font-semibold">{summary.document}</div>
          <div className="text-foreground/55 mt-1 text-xs uppercase">{summary.status}</div>
          <ul className="text-foreground/75 mt-3 space-y-2 text-sm leading-6">
            {summary.evidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </section>
    );
  }

  return (
    <section className="border-glass-border/60 bg-glass-bg/30 rounded-2xl border p-4 shadow-sm sm:p-5">
      <div className="text-primary text-xs font-semibold tracking-[0.16em] uppercase">
        Collection Summary
      </div>
      <div className="text-foreground mt-2 text-sm font-semibold">{summary.collection}</div>
      {summary.metrics.length > 0 ? (
        <ul className="text-foreground/75 mt-3 grid gap-2 text-sm leading-6 sm:grid-cols-2">
          {summary.metrics.map((metric) => {
            const separator = metric.indexOf(":");
            if (separator === -1) return <li key={metric}>{metric}</li>;
            return (
              <li key={metric}>
                <span>{metric.slice(0, separator + 1)}</span>{" "}
                <span>{metric.slice(separator + 1).trim()}</span>
              </li>
            );
          })}
        </ul>
      ) : null}
      {summary.documents.length > 0 ? (
        <div className="border-glass-border/50 mt-4 border-t pt-3">
          <div className="text-foreground/55 mb-2 text-xs tracking-[0.14em] uppercase">
            Documents
          </div>
          <ul className="text-foreground/75 space-y-1 text-sm leading-6">
            {summary.documents.map((document) => (
              <li key={document}>{document}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function resolveDisplayBlocks(message: QueryThreadMessage): StructuredBlock[] {
  const content = message.content;
  const hasTable = containsMarkdownTable(content);
  const hasChartFence = containsChartFence(content);
  const hasMermaidFence = /```[ \t]*mermaid\b/i.test(content);

  const blocks = message.blocks.filter((block) => {
    if (block.type === "card") return false;
    if (block.type === "table" && hasTable) return false;
    if (block.type === "chart" && hasChartFence) return false;
    if (block.type === "diagram" && block.source === "mermaid" && hasMermaidFence) return false;
    return true;
  });

  const structured = message.structured;
  if (
    !hasTable &&
    !blocks.some((block) => block.type === "table") &&
    structured?.comparison_table
  ) {
    blocks.push({
      id: "comparison-table",
      type: "table",
      title: structured.comparison_table.title,
      headers: structured.comparison_table.headers,
      rows: structured.comparison_table.rows,
    });
  }

  if (!hasChartFence && !blocks.some((block) => block.type === "chart") && structured?.chart) {
    blocks.push({
      id: "structured-chart",
      type: "chart",
      title: structured.chart.title,
      chart_type: structured.chart.chart_type,
      series: structured.chart.series,
      raw_payload: structured.chart.raw_payload,
      parser_source: structured.chart.parser_source,
      confidence: structured.chart.confidence,
      fields: structured.chart.fields,
      is_streaming: structured.chart.is_streaming,
      x_key: structured.chart.x_key,
      y_key: structured.chart.y_key,
      z_key: structured.chart.z_key,
    });
  }

  if (
    !hasMermaidFence &&
    !blocks.some((block) => block.type === "diagram") &&
    structured?.diagram
  ) {
    blocks.push({ id: "structured-diagram", type: "diagram", ...structured.diagram });
  }

  return blocks;
}

function looksLikeStructuredJson(content: string): boolean {
  const trimmed = content.trimStart();
  const keys = /"(?:key_findings|detailed_analysis|comparison_table|chart|diagram)"\s*:/;
  return (trimmed.startsWith("{") || /^```[ \t]*json\b/i.test(trimmed)) && keys.test(trimmed);
}

function stripTransportContent(content: string, blocks: StructuredBlock[]): string {
  let next = content.replace(/(?:\n|^)\s*[*#>`-]*\s*suggestions\s*[-:*`>]*\s*[\s\S]*$/i, "");

  if (blocks.some((block) => block.type === "chart") && !containsChartFence(next)) {
    next = stripChartSection(next);
  }

  return normalizeMarkdown(next);
}

function containsChartFence(content: string): boolean {
  return (
    /```[ \t]*chart\b/i.test(content) ||
    (/```[ \t]*json\b/i.test(content) &&
      /"(?:chart_type|series|chart_data|chartData)"\s*:/.test(content))
  );
}

function containsMarkdownTable(content: string): boolean {
  const lines = content.split("\n");
  let fenced = false;
  for (let index = 0; index < lines.length - 1; index += 1) {
    const line = lines[index]!.trim();
    if (line.startsWith("```")) {
      fenced = !fenced;
      continue;
    }
    if (!fenced && line.includes("|") && isTableSeparator(lines[index + 1]!.trim())) {
      return true;
    }
  }
  return false;
}

function isTableSeparator(line: string): boolean {
  return /^\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?$/.test(line);
}

function stripChartSection(content: string): string {
  const lines = content.split("\n");
  const result: string[] = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    const normalized = line
      .replace(/^#{1,6}\s+/, "")
      .replace(/^[-*]\s+/, "")
      .trim();
    if (!/^chart data$/i.test(normalized)) {
      result.push(line);
      continue;
    }

    let cursor = index + 1;
    let foundData = false;
    while (cursor < lines.length) {
      const candidate = lines[cursor]!.trim();
      if (!candidate) {
        cursor += 1;
        continue;
      }
      if (!/^(?:[-*]|\d+\.)\s+.+[:=]\s*[+-]?\d+(?:\.\d+)?(?:[%kmbKMB])?$/.test(candidate)) {
        break;
      }
      foundData = true;
      cursor += 1;
    }

    if (foundData) {
      index = cursor - 1;
    } else {
      result.push(line);
    }
  }

  return result.join("\n");
}
