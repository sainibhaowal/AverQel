import type { ReasoningTraceData } from "@/app/components/query/ReasoningTrace";
import {
  extractVisualChartCandidate,
  normalizeVisualChartValue,
  type VisualChartType,
} from "./chart-parser";

const VISUAL_CHART_TYPES = new Set<VisualChartType>(["line", "bar", "pie", "area", "scatter"]);

export function estimateTokens(text: string): number {
  const trimmed = text.trim();
  if (!trimmed) return 0;
  return trimmed.split(/\s+/).length;
}

export interface MessageMetrics {
  tokensPerSec?: number;
  totalTokens?: number;
  ttftMs?: number;
  modelName?: string;
  providerType?: string;
  activeTools?: string[];
  startedAt?: string;
  firstTokenAt?: string;
  contextLimit?: number;
  contextLimitSource?: string | null;
  contextUsedTokens?: number;
  contextRemainingTokens?: number;
  contextUsage?: number;
  phase?: string;
  latencyTimeline?: Array<{
    label: string;
    atMs: number;
    detail?: string;
  }>;
}

export interface CitationItem {
  document_id: string;
  chunk_id: string;
  filename: string;
  snippet: string;
  similarity_score: number;
  source_type?: string;
  section_header?: string | null;
  page_number?: number | null;
}

export interface StructuredAnswerShape {
  key_findings: string[];
  detailed_analysis: string;
  limitations: string;
  conclusion: string;
  confidence_score: number;
  follow_up_suggestions: string[];
  comparison_table?: {
    title: string;
    headers: string[];
    rows: string[][];
  } | null;
  chart?: {
    title: string;
    chart_type: VisualChartType;
    series: StreamChartPoint[];
    raw_payload?: string | null;
    parser_source?: "json" | "pattern" | "structured";
    confidence?: number;
    fields?: string[];
    is_streaming?: boolean;
    x_key?: string;
    y_key?: string;
    z_key?: string;
  } | null;
  diagram?: Omit<StreamDiagramBlock, "id" | "type"> | null;
}

export interface StreamTableBlock {
  id: string;
  type: "table";
  title?: string | null;
  headers: string[];
  rows: string[][];
}

export interface StreamChartPoint {
  label: string;
  value: number;
  z?: number;
  [key: string]: string | number | null | undefined;
}

export interface StreamChartBlock {
  id: string;
  type: "chart";
  title?: string | null;
  chart_type: VisualChartType;
  series: StreamChartPoint[];
  raw_payload?: string | null;
  parser_source?: "json" | "pattern" | "structured";
  confidence?: number;
  fields?: string[];
  is_streaming?: boolean;
  x_key?: string;
  y_key?: string;
  z_key?: string;
}

export interface StreamCardBlock {
  id: string;
  type: "card";
  title: string;
  content: string;
  tone: "info" | "success" | "warning" | "error" | "neutral";
  incomplete?: boolean;
}

export interface StreamDiagramBlock {
  id: string;
  type: "diagram";
  title?: string | null;
  diagram_type:
    | "mermaid_flowchart"
    | "mermaid_sequence"
    | "mermaid_state"
    | "mermaid_class"
    | "mermaid_er"
    | "mermaid_journey"
    | "mermaid_timeline"
    | "mermaid_gantt"
    | "mermaid_mindmap"
    | "mermaid_pie"
    | "mermaid_gitgraph"
    | "mermaid_quadrant"
    | "mermaid_requirement"
    | "mermaid_block"
    | "mermaid_xychart"
    | "mermaid_c4"
    | "mermaid_architecture"
    | "mermaid_sankey"
    | "mermaid_packet"
    | "mermaid_kanban"
    | "graph_canvas";
  source: "mermaid" | "graph_json";
  syntax: string;
  description?: string;
  incomplete?: boolean;
  graph?: {
    nodes: Array<{ id: string; label: string; category?: string | null }>;
    edges: Array<{ source: string; target: string; label?: string | null }>;
    layout: "horizontal" | "vertical" | "radial";
  } | null;
}

export interface MessageArtifact {
  id: string;
  type: "html" | "svg";
  language: string;
  title: string;
  content: string;
}

export type StructuredBlock =
  | StreamTableBlock
  | StreamChartBlock
  | StreamCardBlock
  | StreamDiagramBlock;

export interface QueryStatusEntry {
  code?: string;
  label: string;
  state: "pending" | "running" | "completed" | "error";
  detail?: string;
  timestamp?: string;
  durationMs?: number;
}

export type QueryStreamEvent =
  | {
      event: "meta";
      data: {
        conversation_id: string;
        message_id?: string | null;
        version_id?: string | null;
        version_index?: number | null;
        trace_id: string;
        confidence: number;
        cached: boolean;
        query_type?: string;
        source_count?: number;
        model_name?: string;
        provider_type?: string;
      };
    }
  | {
      event: "metrics";
      data: MessageMetrics;
    }
  | {
      event: "start";
      data: {
        message_id: string;
        conversation_id: string;
        started_at: string;
        version_id?: string | null;
        version_index?: number | null;
        operation?: "new_turn" | "regenerate" | "edit_regenerate";
      };
    }
  | { event: "thinking"; data: { text: string } }
  | { event: "delta"; data: { text: string } }
  | {
      event: "replace";
      data: {
        content: string;
        format: "markdown" | "structured";
        structured?: StructuredAnswerShape | null;
      };
    }
  | { event: "citation"; data: { item: CitationItem } }
  | {
      event: "status";
      data: {
        code?: string;
        label: string;
        state?: "pending" | "running" | "completed" | "error";
        detail?: string;
        timestamp?: string;
        duration_ms?: number;
      };
    }
  | {
      event: "files";
      data: { items: Array<{ name: string; url: string; type?: string }> };
    }
  | { event: "output"; data: { items: Array<Record<string, unknown>> } }
  | { event: "table"; data: Omit<StreamTableBlock, "type"> }
  | { event: "chart"; data: Omit<StreamChartBlock, "type"> }
  | { event: "card"; data: Omit<StreamCardBlock, "type"> }
  | { event: "diagram"; data: Omit<StreamDiagramBlock, "type"> }
  | { event: "trace"; data: { trace: ReasoningTraceData } }
  | { event: "followups"; data: { items: string[] } }
  | { event: "done"; data: { completed?: boolean } }
  | {
      event: "error";
      data: {
        code: string;
        message: string;
        details?: Record<string, unknown>;
      };
    };

export interface QueryHistoryVersion {
  id: string;
  version_index: number;
  content: string;
  metadata_json?: Record<string, unknown>;
  source_type: "initial" | "regenerate" | "user_edit" | string;
  created_at: string;
}

export interface QueryHistoryMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  metadata_json?: Record<string, unknown>;
  created_at: string;
  active_version_id?: string | null;
  active_version_index?: number;
  version_count?: number;
  versions?: QueryHistoryVersion[];
}

export interface QueryThreadMessageVersion {
  id: string;
  versionIndex: number;
  sourceType: string;
  createdAt: string;
  content: string;
  rawContent: string;
  citations: CitationItem[];
  blocks: StructuredBlock[];
  artifacts: MessageArtifact[];
  trace: ReasoningTraceData | null;
  followups: string[];
  /** Persisted stream lifecycle entries such as search, answer, and follow-up stages. */
  statusHistory: QueryStatusEntry[];
  /** Explicit generated file outputs emitted by the backend stream or restored from history. */
  output: Array<Record<string, unknown>>;
  /** Explicit generated file links emitted by the backend stream or restored from history. */
  files: Array<{ name: string; url: string; type?: string }>;
  thinkingContent?: string;
  confidence?: number;
  traceId?: string;
  cached?: boolean;
  structured?: StructuredAnswerShape | null;
  error?: { code: string; message: string } | null;
  status: "ready" | "streaming" | "error";
  streamPhase?: "searching" | "grounding" | "answering";
  metrics?: MessageMetrics;
}

export interface QueryThreadMessage {
  id: string;
  role: "user" | "assistant";
  /**
   * Normalized (display-ready) content. Always derived from rawContent via
   * normalizeMarkdown. Never used as an accumulation base — that is
   * what rawContent is for.
   */
  content: string;
  /**
   * The unmodified accumulated raw text from delta tokens, or the original
   * replace/history content before normalization. Used as the single source
   * of truth for content accumulation so normalizeMarkdown is never
   * applied to its own output.
   */
  rawContent?: string;
  createdAt: string;
  status: "ready" | "streaming" | "error";
  streamPhase?: "searching" | "grounding" | "answering";
  citations: CitationItem[];
  blocks: StructuredBlock[];
  artifacts: MessageArtifact[];
  trace: ReasoningTraceData | null;
  followups: string[];
  /** Persisted stream lifecycle entries such as search, answer, and follow-up stages. */
  statusHistory: QueryStatusEntry[];
  /** Explicit generated output metadata emitted by the backend stream or restored from history. */
  output: Array<Record<string, unknown>>;
  /** Explicit generated file links emitted by the backend stream or restored from history. */
  files: Array<{ name: string; url: string; type?: string }>;
  thinkingContent?: string;
  confidence?: number;
  traceId?: string;
  cached?: boolean;
  structured?: StructuredAnswerShape | null;
  error?: { code: string; message: string } | null;
  metrics?: MessageMetrics;
  activeVersionId?: string | null;
  activeVersionIndex: number;
  versionCount: number;
  versions: QueryThreadMessageVersion[];
  isEditing?: boolean;
  draftContent?: string;
}

export function createClientMessageId(prefix: "user" | "assistant"): string {
  const randomPart = Math.random().toString(36).slice(2, 10);
  return `${prefix}_${Date.now()}_${randomPart}`;
}

function unwrapStructuredJsonCandidate(raw: string): string {
  const candidate = raw.trim();
  const fenced = candidate.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  if (fenced) {
    return fenced[1]?.trim() ?? "";
  }
  const prefixed = candidate.match(/^(?:json|copy)\s*```(?:json)?\s*([\s\S]*?)\s*```$/i);
  if (prefixed) {
    return prefixed[1]?.trim() ?? "";
  }
  return candidate;
}

function normalizeLooseStructuredChart(
  chart: unknown,
  confidenceScore: number,
): StructuredAnswerShape["chart"] {
  if (!chart || typeof chart !== "object") {
    return null;
  }

  const record = chart as Record<string, unknown>;
  const rawType =
    typeof record.chart_type === "string" ? record.chart_type.trim().toLowerCase() : "";
  const chartType = VISUAL_CHART_TYPES.has(rawType as VisualChartType)
    ? (rawType as VisualChartType)
    : "bar";

  const extracted: StreamChartPoint[] = [];
  const pushPoint = (point: Record<string, unknown>) => {
    const rawLabel = point.label ?? point.name ?? point.x;
    const rawValue = point.value ?? point.y ?? point.val;
    const numericValue =
      typeof rawValue === "number"
        ? rawValue
        : typeof rawValue === "string" && rawValue.trim()
          ? Number(rawValue.replace(/,/g, "").replace(/%$/, ""))
          : NaN;
    if (
      (typeof rawLabel !== "string" && typeof rawLabel !== "number") ||
      !Number.isFinite(numericValue)
    ) {
      return;
    }
    extracted.push({
      label: String(rawLabel),
      value: numericValue,
      ...(typeof point.z === "number" ? { z: point.z } : {}),
    });
  };

  const series = Array.isArray(record.series) ? record.series : [];
  for (const item of series) {
    if (!item || typeof item !== "object") {
      continue;
    }
    const seriesRecord = item as Record<string, unknown>;
    if (Array.isArray(seriesRecord.data)) {
      for (const nested of seriesRecord.data) {
        if (nested && typeof nested === "object") {
          pushPoint(nested as Record<string, unknown>);
        }
      }
      continue;
    }
    pushPoint(seriesRecord);
  }

  if (extracted.length < 2 && Array.isArray(record.data)) {
    for (const item of record.data) {
      if (item && typeof item === "object") {
        pushPoint(item as Record<string, unknown>);
      }
    }
  }

  if (extracted.length < 2) {
    return null;
  }

  return {
    title: typeof record.title === "string" && record.title.trim() ? record.title : "Chart Data",
    chart_type: chartType,
    series: extracted,
    raw_payload: JSON.stringify(chart),
    parser_source: "structured",
    confidence: confidenceScore > 0 ? confidenceScore : undefined,
    fields: ["label", "value"],
    x_key: "label",
    y_key: "value",
  };
}

export function extractStreamingStructuredChart(raw: string): StructuredAnswerShape["chart"] {
  const parsed = parseStructuredAnswer(raw);
  if (parsed?.chart) {
    return {
      ...parsed.chart,
      is_streaming: true,
    };
  }

  const candidate = unwrapStructuredJsonCandidate(raw);
  const rawTypeMatch = candidate.match(/"chart_type"\s*:\s*"(line|bar|pie|area|scatter)"/i);
  const titleMatch = candidate.match(/"title"\s*:\s*"([^"]+)"/i);
  const rawType = rawTypeMatch?.[1]?.toLowerCase() ?? "";
  const chartType = VISUAL_CHART_TYPES.has(rawType as VisualChartType)
    ? (rawType as VisualChartType)
    : "bar";
  const series: StreamChartPoint[] = [];
  const pointRegex =
    /"(?:label|name|x)"\s*:\s*"([^"]+)"[\s\S]{0,120}?"(?:value|y|val)"\s*:\s*("?)(-?\d+(?:\.\d+)?)(?:%?)\1/g;
  for (const match of candidate.matchAll(pointRegex)) {
    const label = match[1]?.trim();
    const value = Number(match[3]);
    if (!label || !Number.isFinite(value)) {
      continue;
    }
    if (series.some((point) => point.label === label && point.value === value)) {
      continue;
    }
    series.push({ label, value });
  }

  if (!rawTypeMatch && series.length === 0) {
    return null;
  }

  return {
    title: titleMatch?.[1]?.trim() || "Chart Data",
    chart_type: chartType,
    series,
    raw_payload: candidate,
    parser_source: "structured",
    confidence: undefined,
    fields: series.length > 0 ? ["label", "value"] : [],
    is_streaming: true,
    x_key: "label",
    y_key: "value",
  };
}

export function parseStructuredAnswer(raw: string): StructuredAnswerShape | null {
  const candidate = unwrapStructuredJsonCandidate(raw);
  if (!candidate.startsWith("{")) {
    return null;
  }
  try {
    const parsed = JSON.parse(candidate) as Partial<StructuredAnswerShape>;
    if (typeof parsed.detailed_analysis !== "string") {
      return null;
    }
    return {
      key_findings: Array.isArray(parsed.key_findings) ? parsed.key_findings.map(String) : [],
      detailed_analysis: parsed.detailed_analysis,
      limitations: typeof parsed.limitations === "string" ? parsed.limitations : "",
      conclusion: typeof parsed.conclusion === "string" ? parsed.conclusion : "",
      confidence_score: typeof parsed.confidence_score === "number" ? parsed.confidence_score : 0,
      follow_up_suggestions: Array.isArray(parsed.follow_up_suggestions)
        ? parsed.follow_up_suggestions.map(String)
        : [],
      comparison_table:
        parsed.comparison_table &&
        typeof parsed.comparison_table === "object" &&
        Array.isArray((parsed.comparison_table as { headers?: unknown }).headers) &&
        Array.isArray((parsed.comparison_table as { rows?: unknown }).rows)
          ? {
              title:
                typeof (parsed.comparison_table as { title?: unknown }).title === "string"
                  ? (parsed.comparison_table as { title: string }).title
                  : "Comparison",
              headers: (parsed.comparison_table as { headers: unknown[] }).headers.map(String),
              rows: (parsed.comparison_table as { rows: unknown[] }).rows.map((row) =>
                Array.isArray(row) ? row.map(String) : [],
              ),
            }
          : null,
      chart: normalizeStructuredChart(parsed),
      diagram:
        parsed.diagram &&
        typeof parsed.diagram === "object" &&
        (typeof (parsed.diagram as { syntax?: unknown }).syntax === "string" ||
          ((parsed.diagram as { graph?: unknown }).graph &&
            typeof (parsed.diagram as { graph?: unknown }).graph === "object"))
          ? {
              title:
                typeof (parsed.diagram as { title?: unknown }).title === "string"
                  ? (parsed.diagram as { title: string }).title
                  : null,
              diagram_type:
                (
                  parsed.diagram as {
                    diagram_type?: StreamDiagramBlock["diagram_type"];
                  }
                ).diagram_type ?? "mermaid_flowchart",
              source:
                (
                  parsed.diagram as {
                    source?: StreamDiagramBlock["source"];
                  }
                ).source ?? "mermaid",
              syntax:
                typeof (parsed.diagram as { syntax?: unknown }).syntax === "string"
                  ? (parsed.diagram as { syntax: string }).syntax
                  : "",
              description:
                typeof (parsed.diagram as { description?: unknown }).description === "string"
                  ? (parsed.diagram as { description: string }).description
                  : "",
              graph:
                (parsed.diagram as { graph?: unknown }).graph &&
                typeof (parsed.diagram as { graph?: unknown }).graph === "object" &&
                Array.isArray((parsed.diagram as { graph: { nodes?: unknown } }).graph.nodes) &&
                Array.isArray((parsed.diagram as { graph: { edges?: unknown } }).graph.edges)
                  ? {
                      nodes: (
                        parsed.diagram as { graph: { nodes: unknown[] } }
                      ).graph.nodes.flatMap((node) =>
                        node &&
                        typeof node === "object" &&
                        typeof (node as { id?: unknown }).id === "string" &&
                        typeof (node as { label?: unknown }).label === "string"
                          ? [
                              {
                                id: (node as { id: string }).id,
                                label: (node as { label: string }).label,
                                category:
                                  typeof (node as { category?: unknown }).category === "string"
                                    ? (node as { category: string }).category
                                    : null,
                              },
                            ]
                          : [],
                      ),
                      edges: (
                        parsed.diagram as { graph: { edges: unknown[] } }
                      ).graph.edges.flatMap((edge) =>
                        edge &&
                        typeof edge === "object" &&
                        typeof (edge as { source?: unknown }).source === "string" &&
                        typeof (edge as { target?: unknown }).target === "string"
                          ? [
                              {
                                source: (edge as { source: string }).source,
                                target: (edge as { target: string }).target,
                                label:
                                  typeof (edge as { label?: unknown }).label === "string"
                                    ? (edge as { label: string }).label
                                    : null,
                              },
                            ]
                          : [],
                      ),
                      layout:
                        (
                          parsed.diagram as {
                            graph?: {
                              layout?: "horizontal" | "vertical" | "radial";
                            };
                          }
                        ).graph?.layout === "vertical" ||
                        (
                          parsed.diagram as {
                            graph?: {
                              layout?: "horizontal" | "vertical" | "radial";
                            };
                          }
                        ).graph?.layout === "radial"
                          ? (
                              parsed.diagram as {
                                graph: {
                                  layout: "vertical" | "radial";
                                };
                              }
                            ).graph.layout
                          : "horizontal",
                    }
                  : null,
            }
          : null,
    };
  } catch {
    return null;
  }
}

function normalizeStructuredChart(
  parsed: Partial<StructuredAnswerShape>,
): StructuredAnswerShape["chart"] {
  const explicitChart =
    parsed.chart && typeof parsed.chart === "object"
      ? normalizeVisualChartValue(parsed.chart, "chart")
      : null;
  if (explicitChart) {
    return {
      title: explicitChart.title || "Chart Data",
      chart_type: explicitChart.type,
      series: explicitChart.data.map((point) => ({
        ...Object.fromEntries(
          Object.entries(point).flatMap(([key, value]) =>
            key === "label" || key === "value" || key === "z"
              ? []
              : typeof value === "string" || typeof value === "number" || value == null
                ? [[key, value]]
                : [],
          ),
        ),
        label: String(point[explicitChart.xKey] ?? point.label ?? ""),
        value: Number(point[explicitChart.yKey] ?? point.value ?? 0),
        ...(explicitChart.zKey && typeof point[explicitChart.zKey] === "number"
          ? { z: Number(point[explicitChart.zKey]) }
          : typeof point.z === "number"
            ? { z: point.z }
            : {}),
      })),
      raw_payload: JSON.stringify(parsed.chart),
      parser_source: "structured",
      confidence: explicitChart.metadata.confidence,
      fields: explicitChart.metadata.fields,
      is_streaming: explicitChart.metadata.isStreaming,
      x_key: explicitChart.xKey,
      y_key: explicitChart.yKey,
      z_key: explicitChart.zKey,
    };
  }

  const looseChart = normalizeLooseStructuredChart(parsed.chart, parsed.confidence_score ?? 0);
  if (looseChart) {
    return looseChart;
  }

  const salvageCandidate =
    parsed && typeof parsed === "object"
      ? extractVisualChartCandidate(parsed as Record<string, unknown>)
      : null;
  const salvagedChart =
    salvageCandidate && salvageCandidate !== parsed.chart
      ? normalizeVisualChartValue(salvageCandidate, "chart")
      : null;
  if (!salvagedChart) {
    return null;
  }

  return {
    title: salvagedChart.title || "Chart Data",
    chart_type: salvagedChart.type,
    series: salvagedChart.data.map((point) => ({
      ...Object.fromEntries(
        Object.entries(point).flatMap(([key, value]) =>
          key === "label" || key === "value" || key === "z"
            ? []
            : typeof value === "string" || typeof value === "number" || value == null
              ? [[key, value]]
              : [],
        ),
      ),
      label: String(point[salvagedChart.xKey] ?? point.label ?? ""),
      value: Number(point[salvagedChart.yKey] ?? point.value ?? 0),
      ...(salvagedChart.zKey && typeof point[salvagedChart.zKey] === "number"
        ? { z: Number(point[salvagedChart.zKey]) }
        : typeof point.z === "number"
          ? { z: point.z }
          : {}),
    })),
    raw_payload: JSON.stringify(salvageCandidate),
    parser_source: salvagedChart.metadata.source,
    confidence: salvagedChart.metadata.confidence,
    fields: salvagedChart.metadata.fields,
    is_streaming: salvagedChart.metadata.isStreaming,
    x_key: salvagedChart.xKey,
    y_key: salvagedChart.yKey,
    z_key: salvagedChart.zKey,
  };
}

export function structuredAnswerToMarkdown(answer: StructuredAnswerShape): string {
  const sections: string[] = [];
  let detailedAnalysis = answer.detailed_analysis.trim();

  if (answer.diagram?.source === "mermaid" && answer.diagram.syntax.trim()) {
    const syntax = answer.diagram.syntax.trim();
    const title = answer.diagram.title?.trim() || "Generated Diagram";

    // Always prepend diagram at the absolute top
    sections.push(`### ${title}\n\n\`\`\`mermaid\n${syntax}\n\`\`\``);

    // Fuzzy stripping of inline duplicates
    const getSignature = (text: string) => text.replace(/\s+/g, "").replace(/['"]/g, "");
    const syntaxSig = getSignature(syntax);

    // Use regex to remove inline mermaid blocks that match the syntax signature
    const mermaidBlockRegex = /```mermaid\s*([\s\S]*?)```/g;
    detailedAnalysis = detailedAnalysis.replace(mermaidBlockRegex, (match, blockContent) => {
      if (getSignature(blockContent.trim()) === syntaxSig) {
        return ""; // Strip the matching inline block
      }
      return match; // Keep non-matching blocks
    });
  }

  if (answer.key_findings.length > 0) {
    sections.push(`### Key Findings\n${answer.key_findings.map((item) => `- ${item}`).join("\n")}`);
  }

  if (detailedAnalysis.length > 0) {
    sections.push(detailedAnalysis);
  }
  if (answer.limitations.trim()) {
    sections.push(`### Limitations\n${answer.limitations.trim()}`);
  }
  if (answer.conclusion.trim()) {
    sections.push(`### Conclusion\n${answer.conclusion.trim()}`);
  }
  return sections.join("\n\n").trim();
}

export function extractArtifactsFromContent(content: string): MessageArtifact[] {
  if (!content.trim()) {
    return [];
  }

  const matches = content.matchAll(/```([a-zA-Z0-9_-]+)\n([\s\S]*?)```/g);
  const artifacts: MessageArtifact[] = [];
  let index = 0;

  for (const match of matches) {
    const language = (match[1] ?? "").trim().toLowerCase();
    const body = (match[2] ?? "").trim();
    if (!body) {
      continue;
    }

    if (language === "html") {
      artifacts.push({
        id: `artifact-html-${index}`,
        type: "html",
        language,
        title: `HTML artifact ${index + 1}`,
        content: body,
      });
      index += 1;
      continue;
    }

    if (language === "svg" || (language === "xml" && /<svg[\s>]/i.test(body))) {
      artifacts.push({
        id: `artifact-svg-${index}`,
        type: "svg",
        language,
        title: `SVG artifact ${index + 1}`,
        content: body,
      });
      index += 1;
    }
  }

  return artifacts;
}

export function parseSseFrames(buffer: string): {
  events: QueryStreamEvent[];
  remainder: string;
} {
  const frames = buffer.split(/\n\n/);
  const remainder = frames.pop() ?? "";
  const events: QueryStreamEvent[] = [];

  for (const frame of frames) {
    const trimmed = frame.trim();
    if (!trimmed) {
      continue;
    }

    let eventName = "message";
    const dataLines: string[] = [];

    for (const line of trimmed.split(/\n/)) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }

    if (dataLines.length === 0) {
      continue;
    }

    try {
      const data = JSON.parse(dataLines.join("\n")) as QueryStreamEvent["data"];
      events.push({
        event: eventName as QueryStreamEvent["event"],
        data,
      } as QueryStreamEvent);
    } catch {
      events.push({
        event: "error",
        data: {
          code: "STREAM_PARSE_ERROR",
          message: "Failed to parse stream frame.",
        },
      });
    }
  }

  return { events, remainder };
}
