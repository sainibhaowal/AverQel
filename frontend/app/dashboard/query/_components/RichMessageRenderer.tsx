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
  const suppressStreamingJson = isStreaming && looksLikeStructuredJson(displayContent);
  const hasRenderableContent = !suppressStreamingJson && displayContent.trim().length > 0;

  return (
    <div className="min-w-0 space-y-8 overflow-hidden sm:space-y-9">
      {hasRenderableContent ? (
        <MarkdownRenderer content={displayContent} streaming={isStreaming} messageId={message.id} />
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
