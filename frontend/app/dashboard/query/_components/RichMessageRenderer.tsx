"use client";

import { memo } from "react";

import FeedbackActions from "@/app/components/query/FeedbackActions";
import FollowUpSuggestions from "@/app/components/query/FollowUpSuggestions";
import ReasoningTrace from "@/app/components/query/ReasoningTrace";
import ReferenceTiles from "@/app/components/query/ReferenceTiles";

import { extractStreamingStructuredChart, type QueryThreadMessage } from "../_lib/stream-protocol";
import { parseVisualChart } from "../_lib/chart-parser";

import { renderInvestigationPanels } from "./InvestigationPanels";
import ArtifactsPanel from "./ArtifactsPanel";
import MarkdownRenderer from "./MarkdownRenderer";
import StatusHistoryPanel from "./StatusHistoryPanel";
import StructuredBlockRenderer from "./StructuredBlockRenderer";
import { parseStreamingDocument } from "../_lib/streaming-document-parser";

interface RichMessageRendererProps {
  mode?: "query" | "deepspace";
  message: QueryThreadMessage;
  isStreaming: boolean;
  onPreviewDocument: (payload: { id: string; name: string; page?: number }) => void;
  onFollowupSelect: (query: string) => void;
}

function RichMessageRenderer({
  mode = "query",
  message,
  isStreaming,
  onPreviewDocument,
  onFollowupSelect,
}: RichMessageRendererProps) {
  const showWorkflowMeta = mode !== "deepspace";
  const transportStrippedContent = stripStructuredArtifacts(
    message.content,
    message.blocks,
    isStreaming,
  );
  const investigationPanels = renderInvestigationPanels({ content: transportStrippedContent });
  const investigationContent = investigationPanels?.remainingContent ?? transportStrippedContent;
  const displayBlocks = resolveDisplayBlocks(message, investigationContent, isStreaming);
  const displayContent = stripBlockTransportArtifacts(
    investigationContent,
    displayBlocks,
    isStreaming,
  );
  const suppressStreamingJson = isStreaming && looksLikeStructuredJson(displayContent);
  const hasRenderableContent = !suppressStreamingJson && displayContent.trim().length > 0;

  // ── Inline-chart deduplication ────────────────────────────────────────────
  // If the LLM emitted a ```chart or chart-shaped ```json fence, the streaming
  // parser already rendered the chart inline at the correct position.
  // Suppress the StructuredBlockRenderer's bottom-appended chart blocks so
  // the user doesn't see the same chart twice (once inline, once below).
  const rawForInlineCheck1 = message.rawContent || "";
  const rawForInlineCheck2 = message.content || "";
  const hasInlineChartFence =
    containsInlineChartFence(rawForInlineCheck1) || containsInlineChartFence(rawForInlineCheck2);
  const hasInlineMermaidFence =
    containsInlineMermaidFence(rawForInlineCheck1) ||
    containsInlineMermaidFence(rawForInlineCheck2);

  const bottomBlocks = displayBlocks.filter((block) => {
    if (block.type === "chart" && hasInlineChartFence) return false;
    if (block.type === "diagram" && isStreaming && hasInlineMermaidFence) return false;
    return true;
  });

  return (
    <div className="min-w-0 space-y-8 overflow-hidden sm:space-y-9">
      {investigationPanels.panels.length > 0 ? investigationPanels.panels : null}
      {hasRenderableContent ? (
        // FIX: Pass message.id as messageId so MarkdownRenderer resets its
        // NormCache whenever a new message mounts. Without this the cache
        // from message N bleeds into message N+1.
        <MarkdownRenderer content={displayContent} streaming={isStreaming} messageId={message.id} />
      ) : null}
      {message.artifacts.length > 0 || message.files.length > 0 ? (
        <ArtifactsPanel artifacts={message.artifacts} files={message.files} />
      ) : null}
      <StructuredBlockRenderer blocks={bottomBlocks} isStreaming={isStreaming} />
      {showWorkflowMeta && !isStreaming && message.statusHistory.length > 0 ? (
        <StatusHistoryPanel entries={message.statusHistory} isStreaming={isStreaming} />
      ) : null}

      {mode !== "deepspace" && !isStreaming && message.citations.length > 0 ? (
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

/**
 * Returns true when rawContent contains a ```chart fence or a ```json fence
 * whose body looks like chart data (has "chart_type" or "series" key).
 *
 * When true the streaming document parser has already rendered the chart in-
 * line, so StructuredBlockRenderer must NOT append another one at the bottom.
 */
function containsInlineChartFence(content: string): boolean {
  // Explicit ```chart fence (any content is chart intent)
  if (/```chart\b/i.test(content)) return true;

  // ```json fence that contains chart-shaped JSON
  for (const match of content.matchAll(/```json\s*([\s\S]*?)(?:```|$)/gi)) {
    const body = (match[1] ?? "").trim();
    if (/["']?(chart_type|series|chart_data|chartData)["']?\s*[:{]/.test(body)) {
      return true;
    }
  }
  return false;
}

/**
 * Detects if the markdown contains a mermaid code fence.
 */
function containsInlineMermaidFence(content: string): boolean {
  return /```\s*(mermaid|graph|diagram|timeline|sequence|gantt|mindmap|classdiagram|erdiagram|statediagram|flowchart|journey|pie)\b/i.test(
    content,
  );
}

function looksLikeStructuredJson(content: string): boolean {
  const trimmed = content.trimStart();
  if (
    trimmed.startsWith("{") &&
    /"(key_findings|detailed_analysis|diagram|comparison_table|chart)"/.test(trimmed)
  ) {
    return true;
  }
  if (
    /^```json\s*/i.test(trimmed) &&
    /"(key_findings|detailed_analysis|diagram|comparison_table|chart)"/.test(trimmed)
  ) {
    return true;
  }
  if (
    /^(json|copy)\s*```json\s*/i.test(trimmed) &&
    /"(key_findings|detailed_analysis|diagram|comparison_table|chart)"/.test(trimmed)
  ) {
    return true;
  }
  return false;
}

function stripStructuredArtifacts(
  content: string,
  blocks: QueryThreadMessage["blocks"],
  isStreaming: boolean,
): string {
  const next = stripFollowupTransport(content);

  if (looksLikeStructuredJson(next) && (isStreaming || blocks.length > 0)) {
    return "";
  }

  return next.replace(/\n{3,}/g, "\n\n").trim();
}

function stripBlockTransportArtifacts(
  content: string,
  blocks: QueryThreadMessage["blocks"],
  isStreaming: boolean,
): string {
  let next = content;

  if (
    !isStreaming &&
    blocks.some((block) => block.type === "diagram" && block.source === "mermaid")
  ) {
    next = stripMermaidCodeFences(next);
  }

  const chartBlocks = blocks.filter((block) => block.type === "chart");
  if (chartBlocks.length > 0) {
    next = stripChartTransport(
      next,
      chartBlocks.map((block) => block.title ?? "Chart Data"),
    );
    next = stripPseudoMermaidChartFences(next);
    next = stripMarkdownChartArtifacts(next);
  }

  return next.replace(/\n{3,}/g, "\n\n").trim();
}

function stripFollowupTransport(content: string): string {
  return content.replace(FOLLOWUP_TRANSPORT_RE, "").trim();
}

const FOLLOWUP_TRANSPORT_RE = /(?:\n|^)\s*[*#>`-]*\s*suggestions\s*[-:*`>]*\s*[\s\S]*$/i;

function stripMermaidCodeFences(content: string): string {
  return content
    .replace(/```mermaid\s*[\s\S]*?```/gi, "")
    .replace(/```mermaid\s*[\s\S]*$/gi, "")
    .trim();
}

function stripChartTransport(content: string, titles: string[]): string {
  const normalizedTitles = Array.from(
    new Set(
      titles
        .map((title) => title.trim().toLowerCase())
        .filter((title) => title.length > 0)
        .concat("chart data"),
    ),
  );
  const lines = content.split("\n");
  const kept: string[] = [];

  for (let index = 0; index < lines.length; index += 1) {
    const current = lines[index] ?? "";
    if (!isChartSectionHeader(current, normalizedTitles)) {
      kept.push(current);
      continue;
    }

    const nextIndex = collectChartSectionEnd(lines, index + 1);
    if (nextIndex === index + 1) {
      kept.push(current);
      continue;
    }

    index = nextIndex - 1;
  }

  return kept.join("\n");
}

function isChartSectionHeader(line: string, normalizedTitles: string[]): boolean {
  const normalized = line
    .replace(/^#{1,6}\s+/, "")
    .replace(/^[-*]\s+/, "")
    .trim()
    .toLowerCase();
  return normalizedTitles.includes(normalized);
}

function collectChartSectionEnd(lines: string[], startIndex: number): number {
  let index = startIndex;
  let consumedChartLine = false;

  while (index < lines.length) {
    const current = lines[index] ?? "";
    if (!current.trim()) {
      index += 1;
      continue;
    }
    if (looksLikeChartDatum(current)) {
      consumedChartLine = true;
      index += 1;
      continue;
    }
    break;
  }

  return consumedChartLine ? index : startIndex;
}

function looksLikeChartDatum(line: string): boolean {
  const trimmed = line.trim();
  return /^(?:[-*]|\d+\.)\s+.+[:=]\s*[+-]?\d+(?:\.\d+)?(?:[%kmbKMB])?$/.test(trimmed);
}

function resolveDisplayBlocks(
  message: QueryThreadMessage,
  displayContent: string,
  isStreaming: boolean,
): QueryThreadMessage["blocks"] {
  const hasMarkdownTable = containsMarkdownTable(displayContent);
  const blocks = (
    hasMarkdownTable
      ? message.blocks.filter((block) => block.type !== "table")
      : [...message.blocks]
  ).filter((block) => block.type !== "card");

  const hasStructuredTable = blocks.some((block) => block.type === "table");
  const comparisonTable = message.structured?.comparison_table;

  if (!hasMarkdownTable && !hasStructuredTable && comparisonTable) {
    blocks.push({
      id: "comparison-table",
      type: "table",
      title: comparisonTable.title,
      headers: comparisonTable.headers,
      rows: comparisonTable.rows,
    });
  }

  const hasStructuredChart = blocks.some((block) => block.type === "chart");
  const structuredChart = message.structured?.chart;

  if (!hasStructuredChart && structuredChart && structuredChart.series.length > 1) {
    blocks.push({
      id: "structured-chart",
      type: "chart",
      title: structuredChart.title,
      chart_type: structuredChart.chart_type,
      series: structuredChart.series,
      raw_payload: structuredChart.raw_payload,
      parser_source: structuredChart.parser_source,
      confidence: structuredChart.confidence,
      fields: structuredChart.fields,
      is_streaming: structuredChart.is_streaming,
      x_key: structuredChart.x_key,
      y_key: structuredChart.y_key,
      z_key: structuredChart.z_key,
    });
  }

  if (isStreaming && !blocks.some((block) => block.type === "chart")) {
    const progressiveChart = extractStreamingStructuredChart(message.rawContent ?? message.content);
    if (progressiveChart) {
      blocks.push({
        id: "streaming-chart",
        type: "chart",
        title: progressiveChart.title,
        chart_type: progressiveChart.chart_type,
        series: progressiveChart.series,
        raw_payload: progressiveChart.raw_payload,
        parser_source: progressiveChart.parser_source,
        confidence: progressiveChart.confidence,
        fields: progressiveChart.fields,
        is_streaming: true,
        x_key: progressiveChart.x_key,
        y_key: progressiveChart.y_key,
        z_key: progressiveChart.z_key,
      });
      return blocks;
    }
  }

  if (!isStreaming && !blocks.some((block) => block.type === "chart")) {
    const fallbackSource = message.rawContent ?? displayContent;
    const markdownSectionCharts = extractMarkdownSectionCharts(fallbackSource);
    if (markdownSectionCharts.length > 0) {
      markdownSectionCharts.forEach((sectionChart, index) => {
        const normalizedTitle = normalizeChartBlockTitle(sectionChart);
        blocks.push({
          id: `parsed-chart-${index}`,
          type: "chart",
          title: normalizedTitle,
          chart_type: sectionChart.chart.type,
          series: sectionChart.chart.data.map((point) => ({
            ...Object.fromEntries(
              Object.entries(point).flatMap(([key, value]) =>
                key === "label" || key === "value" || key === "z"
                  ? []
                  : typeof value === "string" || typeof value === "number" || value == null
                    ? [[key, value]]
                    : [],
              ),
            ),
            label: String(point[sectionChart.chart.xKey] ?? point.label ?? ""),
            value: Number(point[sectionChart.chart.yKey] ?? point.value ?? 0),
            ...(sectionChart.chart.zKey && typeof point[sectionChart.chart.zKey] === "number"
              ? { z: Number(point[sectionChart.chart.zKey]) }
              : typeof point.z === "number"
                ? { z: point.z }
                : {}),
          })),
          raw_payload: sectionChart.rawPayload,
          parser_source: sectionChart.chart.metadata.source,
          confidence: sectionChart.chart.metadata.confidence,
          fields: sectionChart.chart.metadata.fields,
          is_streaming: sectionChart.chart.metadata.isStreaming,
          x_key: sectionChart.chart.xKey,
          y_key: sectionChart.chart.yKey,
          z_key: sectionChart.chart.zKey,
        });
      });
      return blocks;
    }

    const fallbackChart = parseVisualChart(fallbackSource, "chart");
    const pseudoMermaidChart = extractPseudoMermaidChart(fallbackSource);
    const hasExplicitChartTransport = containsExplicitChartTransport(fallbackSource);
    const explicitChartTitle = hasExplicitChartTransport
      ? extractChartTransportTitle(fallbackSource)
      : null;
    const shouldPromoteFallbackChart =
      (fallbackChart &&
        fallbackChart.data.length > 1 &&
        (fallbackChart.metadata.source === "json" || hasExplicitChartTransport)) ||
      (pseudoMermaidChart && pseudoMermaidChart.data.length > 1);

    const promotedChart = pseudoMermaidChart ?? fallbackChart;

    if (shouldPromoteFallbackChart && promotedChart) {
      blocks.push({
        id: "parsed-chart",
        type: "chart",
        title:
          explicitChartTitle ??
          (promotedChart.title.trim().toLowerCase() === "chart"
            ? "Chart Data"
            : promotedChart.title),
        chart_type: promotedChart.type,
        series: promotedChart.data.map((point) => ({
          ...Object.fromEntries(
            Object.entries(point).flatMap(([key, value]) =>
              key === "label" || key === "value" || key === "z"
                ? []
                : typeof value === "string" || typeof value === "number" || value == null
                  ? [[key, value]]
                  : [],
            ),
          ),
          label: String(point[promotedChart.xKey] ?? point.label ?? ""),
          value: Number(point[promotedChart.yKey] ?? point.value ?? 0),
          ...(promotedChart.zKey && typeof point[promotedChart.zKey] === "number"
            ? { z: Number(point[promotedChart.zKey]) }
            : typeof point.z === "number"
              ? { z: point.z }
              : {}),
        })),
        raw_payload: pseudoMermaidChart
          ? pseudoMermaidChart.rawPayload
          : (message.rawContent ?? displayContent),
        parser_source: promotedChart.metadata.source,
        confidence: promotedChart.metadata.confidence,
        fields: promotedChart.metadata.fields,
        is_streaming: promotedChart.metadata.isStreaming,
        x_key: promotedChart.xKey,
        y_key: promotedChart.yKey,
        z_key: promotedChart.zKey,
      });
    }
  }

  return blocks;
}

function containsMarkdownTable(content: string): boolean {
  return parseStreamingDocument(content, false).some((node) => node.type === "table");
}

function containsExplicitChartTransport(content: string): boolean {
  const lines = content.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    if (!isChartSectionHeader(lines[index] ?? "", ["chart data"])) {
      continue;
    }
    return collectChartSectionEnd(lines, index + 1) > index + 1;
  }
  return false;
}

function extractChartTransportTitle(content: string): string | null {
  const lines = content.split("\n");
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    if (!isChartSectionHeader(line, ["chart data"])) {
      continue;
    }
    if (collectChartSectionEnd(lines, index + 1) > index + 1) {
      return "Chart Data";
    }
  }
  return null;
}

function stripPseudoMermaidChartFences(content: string): string {
  return content
    .replace(/```mermaid\s+([\s\S]*?)```/gi, (match, body) =>
      extractPseudoMermaidChart(match) ||
      extractPseudoMermaidChart(`\`\`\`mermaid\n${body}\n\`\`\``)
        ? ""
        : match,
    )
    .trim();
}

function stripMarkdownChartArtifacts(content: string): string {
  let next = content;
  for (const sectionChart of extractMarkdownSectionCharts(content)) {
    for (const segment of sectionChart.transportSegments) {
      if (!segment.trim()) {
        continue;
      }
      next = next.replace(segment, "");
    }
  }
  return next.replace(/\n{3,}/g, "\n\n").trim();
}

function extractPseudoMermaidChart(content: string):
  | (ReturnType<typeof parseVisualChart> & {
      rawPayload: string;
    })
  | null {
  for (const match of content.matchAll(/```mermaid\s+([\s\S]*?)```/gi)) {
    const syntax = (match[1] ?? "").trim();
    if (!syntax) {
      continue;
    }
    const parsed = parseVisualChart(syntax, "chart");
    if (!parsed || parsed.data.length < 2) {
      continue;
    }
    return {
      ...parsed,
      rawPayload: syntax,
    };
  }
  return null;
}

type MarkdownChartSection = {
  title: string;
  chart: NonNullable<ReturnType<typeof parseVisualChart>>;
  rawPayload: string;
  transportSegments: string[];
};

function extractMarkdownSectionCharts(content: string): MarkdownChartSection[] {
  return splitMarkdownSections(content).flatMap((section) => {
    const title = normalizeSectionTitle(section.heading);
    const sectionHasIntent =
      hasSectionChartIntent(title, section.body) || containsExplicitChartTransport(section.body);
    if (!sectionHasIntent) {
      return [];
    }

    const chart = parseVisualChart(section.body, title || "chart");
    if (!chart || chart.data.length < 2) {
      return [];
    }

    const transportSegments = [
      ...findMarkdownTableSegments(section.body),
      ...findChartTransportSegments(section.body),
    ];
    if (transportSegments.length === 0) {
      return [];
    }

    return [
      {
        title: title || extractChartTransportTitle(section.body) || chart.title,
        chart,
        rawPayload: section.body,
        transportSegments,
      },
    ];
  });
}

function splitMarkdownSections(content: string): Array<{ heading: string; body: string }> {
  const lines = content.split("\n");
  const sections: Array<{ heading: string; body: string }> = [];
  let currentHeading = "";
  let currentLines: string[] = [];

  const flushSection = () => {
    const body = currentLines.join("\n").trim();
    if (!body) {
      return;
    }
    sections.push({ heading: currentHeading, body });
  };

  for (const line of lines) {
    if (/^#{1,6}\s+/.test(line.trim())) {
      flushSection();
      currentHeading = line.trim();
      currentLines = [];
      continue;
    }
    currentLines.push(line);
  }

  flushSection();

  if (sections.length === 0 && content.trim()) {
    sections.push({ heading: "", body: content.trim() });
  }

  return sections;
}

function normalizeSectionTitle(heading: string): string {
  return heading
    .trim()
    .replace(/^#{1,6}\s+/, "")
    .trim();
}

function hasSectionChartIntent(title: string, body: string): boolean {
  return /\b(line|bar|pie|area|scatter|chart|graph|plot|trend|distribution|histogram|series)\b/i.test(
    `${title}\n${body}`,
  );
}

function findMarkdownTableSegments(content: string): string[] {
  const lines = content.split("\n");
  const segments: string[] = [];

  for (let index = 0; index < lines.length - 1; index += 1) {
    const headerLine = lines[index] ?? "";
    const separatorLine = lines[index + 1] ?? "";
    if (!headerLine.includes("|")) {
      continue;
    }
    if (!/^\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?$/.test(separatorLine.trim())) {
      continue;
    }

    const collected = [headerLine, separatorLine];
    let rowIndex = index + 2;
    while (rowIndex < lines.length) {
      const line = lines[rowIndex] ?? "";
      if (!line.trim() || !line.includes("|")) {
        break;
      }
      collected.push(line);
      rowIndex += 1;
    }

    if (collected.length >= 4) {
      segments.push(collected.join("\n"));
    }
    index = rowIndex - 1;
  }

  return segments;
}

function findChartTransportSegments(content: string): string[] {
  const lines = content.split("\n");
  const segments: string[] = [];

  for (let index = 0; index < lines.length; index += 1) {
    if (!isChartSectionHeader(lines[index] ?? "", ["chart data"])) {
      continue;
    }

    const endIndex = collectChartSectionEnd(lines, index + 1);
    if (endIndex > index + 1) {
      segments.push(lines.slice(index, endIndex).join("\n"));
      index = endIndex - 1;
    }
  }

  return segments;
}

function normalizeChartBlockTitle(sectionChart: MarkdownChartSection): string {
  const normalizedChartTitle = sectionChart.chart.title.trim().toLowerCase();
  if (normalizedChartTitle === "chart" || normalizedChartTitle === "chart data") {
    return sectionChart.title || "Chart Data";
  }
  return sectionChart.chart.title;
}
