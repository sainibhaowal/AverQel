export const VISUAL_FENCE_KINDS = ["chart", "card", "graph", "gallery", "mermaid"] as const;
export type VisualFenceKind = (typeof VISUAL_FENCE_KINDS)[number];

const MERMAID_FENCE_ALIASES = new Set([
  "mermaid",
  "gantt",
  "mmd",
  "mermaid-gantt",
  "mermaid_gantt",
]);

function normalizeVisualFenceKind(language: string): VisualFenceKind | null {
  const normalizedLanguage = language.trim().toLowerCase();
  if (MERMAID_FENCE_ALIASES.has(normalizedLanguage)) return "mermaid";
  return (VISUAL_FENCE_KINDS as readonly string[]).includes(normalizedLanguage)
    ? (normalizedLanguage as VisualFenceKind)
    : null;
}

function hasGanttHeader(source: string): boolean {
  const firstContentLine = source
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line && !line.startsWith("%%"));
  return firstContentLine?.toLowerCase() === "gantt";
}

/**
 * Providers sometimes wrap a visual block in a generic `json` fence. Infer
 * only the unambiguous visual payloads so ordinary JSON remains a code block.
 */
export function inferVisualFenceKind(language: string, value: string): VisualFenceKind | null {
  const normalizedLanguage = language.trim().toLowerCase();
  const normalizedKind = normalizeVisualFenceKind(normalizedLanguage);
  if (normalizedKind) return normalizedKind;

  if (["", "text", "txt", "plaintext"].includes(normalizedLanguage) && hasGanttHeader(value)) {
    return "mermaid";
  }
  if (normalizedLanguage && normalizedLanguage !== "json") return null;

  try {
    const payload = JSON.parse(value) as Record<string, unknown>;
    if (!payload || Array.isArray(payload)) return null;
    const graph = payload.graph;
    if (
      (graph &&
        typeof graph === "object" &&
        Array.isArray((graph as Record<string, unknown>).nodes) &&
        Array.isArray((graph as Record<string, unknown>).edges)) ||
      (Array.isArray(payload.nodes) && Array.isArray(payload.edges))
    ) {
      return "graph";
    }
    if (
      Array.isArray(payload.items) &&
      payload.items.some(
        (item) =>
          item &&
          typeof item === "object" &&
          typeof (item as Record<string, unknown>).src === "string",
      )
    ) {
      return "gallery";
    }
    if (
      typeof payload.chart_type === "string" ||
      Array.isArray(payload.series) ||
      Array.isArray(payload.chart_data) ||
      Array.isArray(payload.chartData)
    ) {
      return "chart";
    }
    if (
      typeof payload.title === "string" &&
      (typeof payload.content === "string" || typeof payload.body === "string")
    ) {
      return "card";
    }
  } catch {
    return null;
  }
  return null;
}

/** Convert BlockNote's persisted rich-content HTML wrapper back to a fence. */
export function unwrapPersistedVisualFence(value: string): {
  kind: VisualFenceKind;
  source: string;
} | null {
  const match = value
    .trim()
    .match(
      /^```(chart|card|graph|gallery|mermaid|gantt|mmd|mermaid[-_]gantt)\s*\n([\s\S]*?)\n?```$/i,
    );
  if (!match) return null;
  const kind = normalizeVisualFenceKind(match[1]!);
  return kind ? { kind, source: match[2]!.trim() } : null;
}

/** Replace BlockNote's serialized rich-content wrapper before Markdown parsing. */
export function normalizePersistedRichContent(value: string): string {
  if (!/<pre\b/i.test(value) || !/data-rich-content-(?:kind|source)/i.test(value)) return value;
  return value.replace(/<pre\b([^>]*)>[\s\S]*?<\/pre>/gi, (whole, attributes: string) => {
    const kindMatch = attributes.match(
      /data-rich-content-kind\s*=\s*["'](chart|card|graph|gallery|mermaid|gantt|mmd|mermaid[-_]gantt)["']/i,
    );
    const sourceMatch = attributes.match(/data-rich-content-source\s*=\s*["']([\s\S]*?)["']/i);
    if (!kindMatch || !sourceMatch) return whole;
    const kind = normalizeVisualFenceKind(kindMatch[1]!);
    if (!kind) return whole;
    return `${String.fromCharCode(96).repeat(3)}${kind}\n${decodeHtmlEntities(sourceMatch[1]!)}\n${String.fromCharCode(96).repeat(3)}`;
  });
}

function decodeHtmlEntities(value: string): string {
  if (typeof document === "undefined") {
    return value
      .replace(/&quot;/g, '"')
      .replace(/&#x27;|&#39;/g, "'")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">")
      .replace(/&amp;/g, "&");
  }
  const textarea = document.createElement("textarea");
  textarea.innerHTML = value;
  return textarea.value;
}
