export type VisualChartType = "line" | "bar" | "pie" | "area" | "scatter";

export interface VisualChartPoint {
  label: string | number;
  value: number;
  z?: number;
  [key: string]: string | number | boolean | null | undefined;
}

export interface VisualChartContext {
  type: VisualChartType;
  title: string;
  data: VisualChartPoint[];
  xKey: string;
  yKey: string;
  zKey?: string;
  metadata: {
    confidence: number;
    source: "json" | "pattern";
    fields: string[];
    isStreaming?: boolean;
  };
}

const KEYWORDS_TYPE: Record<string, VisualChartType> = {
  pie: "pie",
  circle: "pie",
  donut: "pie",
  scatter: "scatter",
  correlation: "scatter",
  distribution: "scatter",
  bubble: "scatter",
  bar: "bar",
  column: "bar",
  histogram: "bar",
  area: "area",
  stack: "area",
  line: "line",
  trend: "line",
  timeline: "line",
};

const CHART_HINT_KEYS = [
  "chart",
  "chart_data",
  "chartData",
  "visualization",
  "graph_data",
  "graphData",
  "plot",
] as const;

export function parseVisualChart(content: string, contextHint = ""): VisualChartContext | null {
  if (!content || content.length < 5) {
    return null;
  }
  if (isMermaidLikely(content)) {
    return null;
  }

  const sanitized = sanitize(content);
  const structured = extractStructuredData(sanitized, contextHint);
  if (structured) {
    return structured;
  }

  const markdownTable = extractFromMarkdownTable(sanitized, contextHint);
  if (markdownTable) {
    return markdownTable;
  }

  return extractFromPatterns(sanitized, contextHint);
}

export function normalizeVisualChartValue(
  raw: unknown,
  contextHint = "",
): VisualChartContext | null {
  if (!raw || typeof raw !== "object") {
    return null;
  }

  return normalizeModel(raw as Record<string, unknown>, contextHint);
}

export function extractVisualChartCandidate(
  raw: Record<string, unknown>,
): Record<string, unknown> | null {
  for (const key of CHART_HINT_KEYS) {
    const candidate = raw[key];
    if (candidate && typeof candidate === "object") {
      return candidate as Record<string, unknown>;
    }
  }

  if (
    Array.isArray(raw.series) ||
    Array.isArray(raw.points) ||
    Array.isArray(raw.data) ||
    typeof raw.chart_type === "string" ||
    typeof raw.type === "string"
  ) {
    return raw;
  }

  return null;
}

function isMermaidLikely(text: string): boolean {
  const trimmed = text.trim().toLowerCase();
  const mermaidRoots = [
    "graph",
    "flowchart",
    "sequencediagram",
    "statediagram",
    "erdiagram",
    "journey",
    "gantt",
    "classdiagram",
    "gitgraph",
    "c4context",
    "c4container",
    "c4component",
    "c4dynamic",
    "c4deployment",
    "mindmap",
    "timeline",
    "pie",
    "quadrantchart",
    "requirementdiagram",
    "block-beta",
    "xychart-beta",
    "architecture-beta",
    "sankey",
    "packet",
    "kanban",
  ];
  const hasRoot = mermaidRoots.some(
    (root) => trimmed.startsWith(`${root} `) || trimmed.startsWith(`${root}\n`),
  );
  const hasArrows =
    trimmed.includes("-->") ||
    trimmed.includes("==>") ||
    /[A-Za-z0-9)\]"}]\s*---\s*[A-Za-z0-9(\[{"]/.test(trimmed);
  return hasRoot || (hasArrows && !trimmed.startsWith("{") && !trimmed.startsWith("["));
}

function sanitize(text: string): string {
  return text
    .replace(/```[a-z]*\n?/gi, "")
    .replace(/```/g, "")
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .trim();
}

function extractStructuredData(content: string, hint: string): VisualChartContext | null {
  if (content.trimStart().startsWith("{") || content.trimStart().startsWith("[")) {
    try {
      const parsed = JSON.parse(content);
      const normalized = normalizeModel(parsed, hint);
      if (normalized) {
        return normalized;
      }
    } catch {
      // Fall through to block scanning.
    }
  }

  const blocks = findJsonBlocks(content);
  for (const block of blocks) {
    try {
      let cleanBlock = block;
      let isStreaming = false;
      if (block.endsWith(",") || (!block.endsWith("}") && !block.endsWith("]"))) {
        cleanBlock = autoFixPartialJson(block);
        isStreaming = true;
      }
      const parsed = JSON.parse(cleanBlock);
      const normalized = normalizeModel(parsed, hint);
      if (normalized) {
        if (isStreaming) {
          normalized.metadata.isStreaming = true;
        }
        return normalized;
      }
    } catch {
      continue;
    }
  }

  return null;
}

function extractFromPatterns(content: string, hint: string): VisualChartContext | null {
  const dslRegex =
    /(?:^|\n)[*-\s]*["']?([\w\s./%-]{1,48})["']?\s*(?:[:|=]|=>|-+>)\s*([+-]?\d+(?:\.\d+)?)/g;
  const points: VisualChartPoint[] = [];
  let match: RegExpExecArray | null;

  while ((match = dslRegex.exec(content)) !== null) {
    const value = Number.parseFloat(match[2]);
    if (!Number.isNaN(value)) {
      points.push({ label: match[1].trim(), value });
    }
  }

  if (points.length < 2) {
    return null;
  }

  return {
    type: inferType(content, hint),
    title: inferTitle(content, hint),
    data: points,
    xKey: "label",
    yKey: "value",
    metadata: {
      confidence: 0.42,
      source: "pattern",
      fields: ["label", "value"],
    },
  };
}

function extractFromMarkdownTable(content: string, hint: string): VisualChartContext | null {
  if (!hasExplicitChartIntent(content, hint)) {
    return null;
  }

  const tables = findMarkdownTables(content);
  for (const table of tables) {
    const chart = parseMarkdownTable(table, content, hint);
    if (chart) {
      return chart;
    }
  }

  return null;
}

function hasExplicitChartIntent(content: string, hint: string): boolean {
  const combined = `${hint}\n${content}`.toLowerCase();
  return /\b(line|bar|pie|area|scatter|chart|graph|plot|trend|distribution|histogram|series)\b/.test(
    combined,
  );
}

type MarkdownTable = {
  headers: string[];
  rows: string[][];
};

function findMarkdownTables(content: string): MarkdownTable[] {
  const lines = content.split("\n");
  const tables: MarkdownTable[] = [];

  for (let index = 0; index < lines.length - 1; index += 1) {
    const headerLine = lines[index]?.trim() ?? "";
    const separatorLine = lines[index + 1]?.trim() ?? "";
    if (!headerLine.includes("|")) {
      continue;
    }
    if (!/^\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?$/.test(separatorLine)) {
      continue;
    }

    const headers = parseMarkdownTableCells(headerLine);
    const rows: string[][] = [];
    let rowIndex = index + 2;
    while (rowIndex < lines.length) {
      const line = lines[rowIndex]?.trim() ?? "";
      if (!line || !line.includes("|")) {
        break;
      }
      const cells = parseMarkdownTableCells(line);
      if (cells.length !== headers.length) {
        break;
      }
      rows.push(cells);
      rowIndex += 1;
    }

    if (headers.length >= 2 && rows.length >= 2) {
      tables.push({ headers, rows });
    }
    index = rowIndex - 1;
  }

  return tables;
}

function parseMarkdownTableCells(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function parseMarkdownTable(
  table: MarkdownTable,
  content: string,
  hint: string,
): VisualChartContext | null {
  const numericColumnIndexes = table.headers.flatMap((_, index) =>
    table.rows.every((row) => toFiniteNumber(row[index]) != null) ? [index] : [],
  );
  if (numericColumnIndexes.length === 0) {
    return null;
  }

  const valueIndex = numericColumnIndexes[0] ?? 1;
  const candidateLabelIndex = table.headers.findIndex(
    (_, index) => index !== valueIndex && table.rows.some((row) => row[index]),
  );
  const labelIndex = candidateLabelIndex >= 0 ? candidateLabelIndex : 0;
  if (labelIndex < 0 || labelIndex === valueIndex) {
    return null;
  }

  const points = table.rows.flatMap((row) => {
    const label = row[labelIndex];
    const value = toFiniteNumber(row[valueIndex]);
    if (!label || value == null) {
      return [];
    }
    return [{ label, value }];
  });

  if (points.length < 2) {
    return null;
  }

  const title = inferTitle(content, hint);

  return {
    type: inferType(content, hint),
    title,
    data: points,
    xKey: "label",
    yKey: "value",
    metadata: {
      confidence: 0.72,
      source: "pattern",
      fields: table.headers,
    },
  };
}

function autoFixPartialJson(json: string): string {
  let fixed = json
    .trim()
    .replace(/[,:]\s*$/, "")
    .replace(/["']\w*$/, "");
  const stack: string[] = [];

  for (const char of fixed) {
    if (char === "{") {
      stack.push("}");
    } else if (char === "[") {
      stack.push("]");
    } else if ((char === "}" || char === "]") && stack.length > 0) {
      stack.pop();
    }
  }

  while (stack.length > 0) {
    fixed += stack.pop();
  }

  return fixed;
}

function findJsonBlocks(text: string): string[] {
  const blocks: string[] = [];
  const stack: Array<{ index: number; token: "{" | "[" }> = [];

  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === "{" || char === "[") {
      stack.push({ index, token: char });
      continue;
    }
    if (char !== "}" && char !== "]") {
      continue;
    }
    const start = stack.pop();
    if (!start) {
      continue;
    }
    const matchingClose = start.token === "{" ? "}" : "]";
    if (char === matchingClose) {
      blocks.push(text.slice(start.index, index + 1));
    }
  }

  if (stack.length > 0) {
    blocks.push(text.slice(stack[0].index));
  }

  return blocks.sort((left, right) => right.length - left.length);
}

function normalizeModel(raw: Record<string, unknown>, hint: string): VisualChartContext | null {
  const rootCandidate = extractVisualChartCandidate(raw) ?? raw;
  const target = resolveTargetSource(rootCandidate);
  if (!target || target.length === 0) {
    return null;
  }

  const points = target.flatMap((item) => {
    const point = normalizePoint(item);
    return point ? [point] : [];
  });
  if (points.length < 2) {
    return null;
  }

  const chartTypeHint =
    readString(rootCandidate.chart_type) ??
    readString(rootCandidate.type) ??
    readString(raw.chart_type) ??
    readString(raw.type) ??
    hint;
  const title = readString(rootCandidate.title) ?? readString(raw.title) ?? inferTitle("", hint);
  const xKey = inferKey(points[0], ["label", "name", "x"], "label");
  const yKey = inferKey(points[0], ["value", "y", "val"], "value");
  const zKey = Object.prototype.hasOwnProperty.call(points[0], "z") ? "z" : undefined;
  const isExplicit =
    Array.isArray(rootCandidate.series) ||
    Array.isArray(rootCandidate.points) ||
    Array.isArray(rootCandidate.data) ||
    typeof rootCandidate.chart_type === "string" ||
    typeof raw.chart !== "undefined";

  return {
    type: inferType(JSON.stringify(rootCandidate), chartTypeHint),
    title,
    data: points,
    xKey,
    yKey,
    zKey,
    metadata: {
      confidence: isExplicit ? 0.96 : 0.78,
      source: "json",
      fields: Object.keys(points[0]),
    },
  };
}

function resolveTargetSource(raw: Record<string, unknown>): unknown[] | null {
  if (Array.isArray(raw.series)) {
    return raw.series;
  }
  if (Array.isArray(raw.points)) {
    return raw.points;
  }
  if (Array.isArray(raw.data)) {
    return raw.data;
  }
  if (Array.isArray(raw.value)) {
    return raw.value;
  }

  const arrayValue = Object.values(raw).find((value) => Array.isArray(value) && value.length > 0);
  return Array.isArray(arrayValue) ? arrayValue : null;
}

function normalizePoint(item: unknown): VisualChartPoint | null {
  if (typeof item === "number") {
    return { label: "", value: item };
  }

  if (!item || typeof item !== "object") {
    return null;
  }

  const record = item as Record<string, unknown>;
  const keys = Object.keys(record).filter((key) => key !== "type" && key !== "chart_type");
  if (keys.length === 0) {
    return null;
  }

  const xField = keys.find((key) => key === "x" || key === "label" || key === "name");
  const yField = keys.find((key) => key === "y" || key === "value" || key === "val");
  const zField = keys.find((key) => key === "z" || key === "size" || key === "weight");

  const labelValue = xField ? record[xField] : undefined;
  const numericValue = yField ? toFiniteNumber(record[yField]) : undefined;

  if ((typeof labelValue === "string" || typeof labelValue === "number") && numericValue != null) {
    return {
      ...copyScalarFields(record),
      label: labelValue,
      value: numericValue,
      ...(zField ? { z: toFiniteNumber(record[zField]) } : {}),
    };
  }

  const numericKeys = keys.filter((key) => toFiniteNumber(record[key]) != null);
  if (numericKeys.length === 0) {
    return null;
  }

  const valueKey = numericKeys[0];
  const fallbackLabelKey = keys.find((key) => key !== valueKey && isLabelLike(record[key]));
  const value = toFiniteNumber(record[valueKey]);
  if (value == null) {
    return null;
  }

  return {
    ...copyScalarFields(record),
    label: fallbackLabelKey ? String(record[fallbackLabelKey]) : "",
    value,
    ...(zField ? { z: toFiniteNumber(record[zField]) } : {}),
  };
}

function copyScalarFields(record: Record<string, unknown>): VisualChartPoint {
  const next: VisualChartPoint = { label: "", value: 0 };
  for (const [key, value] of Object.entries(record)) {
    if (
      typeof value === "string" ||
      typeof value === "number" ||
      typeof value === "boolean" ||
      value == null
    ) {
      next[key] = value;
    }
  }
  return next;
}

function inferTitle(text: string, hint: string): string {
  const explicitTitle = text
    .split("\n")
    .map((line) => line.trim())
    .find((line) => /^title(?:\s+|:)/i.test(line));
  if (explicitTitle) {
    const normalizedTitle = explicitTitle.replace(/^title(?:\s+|:)\s*/i, "").trim();
    if (normalizedTitle) {
      return normalizedTitle;
    }
  }

  const firstLine = text
    .split("\n")
    .map((line) => line.trim().replace(/^#{1,6}\s+/, ""))
    .find((line) => line.length > 0 && !line.startsWith("{") && !line.startsWith("["));
  return hint.trim() || firstLine || "Chart Data";
}

function inferType(text: string, hint = ""): VisualChartType {
  const combined = `${String(text)} ${String(hint)}`.toLowerCase();
  for (const [keyword, type] of Object.entries(KEYWORDS_TYPE)) {
    if (combined.includes(keyword)) {
      return type;
    }
  }
  return "line";
}

function inferKey(
  point: VisualChartPoint,
  candidates: string[],
  fallback: "label" | "value",
): string {
  return (
    candidates.find((candidate) => Object.prototype.hasOwnProperty.call(point, candidate)) ??
    fallback
  );
}

function readString(value: unknown): string | null {
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function toFiniteNumber(value: unknown): number | undefined {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) {
      return undefined;
    }
    const normalized = trimmed
      .replace(/^\((.*)\)$/, "-$1")
      .replace(/^[€£$¥₹]/, "")
      .replace(/,/g, "")
      .replace(/%$/, "");
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  return undefined;
}

function isLabelLike(value: unknown): boolean {
  return typeof value === "string" || typeof value === "number";
}
