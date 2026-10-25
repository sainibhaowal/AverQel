export const VISUAL_FENCE_KINDS = [
  "chart",
  "card",
  "graph",
  "gallery",
  "infographic",
  "mermaid",
] as const;
export type VisualFenceKind = (typeof VISUAL_FENCE_KINDS)[number];

export const STREAMING_VISUAL_FENCE_PREFIX = "averqel-visual-";

const MERMAID_FENCE_ALIASES = new Set([
  "mermaid",
  "gantt",
  "mmd",
  "mermaid-gantt",
  "mermaid_gantt",
]);

const MERMAID_DIAGRAM_HEADERS = new Set([
  "flowchart",
  "graph",
  "sequencediagram",
  "classdiagram",
  "statediagram",
  "statediagram-v2",
  "erdiagram",
  "journey",
  "gantt",
  "pie",
  "gitgraph",
  "mindmap",
  "timeline",
  "quadrantchart",
  "sankey-beta",
  "xychart-beta",
  "block-beta",
  "architecture-beta",
  "requirementdiagram",
  "zenuml",
  "packet-beta",
  "kanban",
]);

function normalizeVisualFenceKind(language: string): VisualFenceKind | null {
  const normalizedLanguage = language.trim().toLowerCase();
  if (MERMAID_FENCE_ALIASES.has(normalizedLanguage)) return "mermaid";
  return (VISUAL_FENCE_KINDS as readonly string[]).includes(normalizedLanguage)
    ? (normalizedLanguage as VisualFenceKind)
    : null;
}

function hasRecognizableMermaidHeader(source: string): boolean {
  const firstContentLine = source
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find((line) => line && !line.startsWith("%%"));
  if (!firstContentLine) return false;
  const header = firstContentLine.split(/\s+/, 1)[0]!.toLowerCase();
  return MERMAID_DIAGRAM_HEADERS.has(header) || /^c4[a-z]+$/.test(header);
}

/**
 * Mark only complete visual fences so streaming renderers can preview each
 * block as soon as its closing fence arrives, without remounting code blocks
 * for every later text delta.
 */
export function markCompletedVisualFences(
  content: string,
  options: { markMermaidWhileStreaming?: boolean } = {},
): string {
  const lines = content.replace(/\r\n/g, "\n").split("\n");
  const output: string[] = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]!;
    const opening = line.match(/^( {0,3})(`{3,}|~{3,})(.*)$/);
    if (!opening) {
      output.push(line);
      continue;
    }

    const indent = opening[1]!;
    const marker = opening[2]!;
    const info = opening[3]!;
    if (marker[0] === "`" && info.includes("`")) {
      output.push(line);
      continue;
    }

    let closingIndex = index + 1;
    for (; closingIndex < lines.length; closingIndex += 1) {
      const closing = lines[closingIndex]!.match(/^ {0,3}(`{3,}|~{3,})[ \t]*$/)?.[1];
      if (closing && closing[0] === marker[0] && closing.length >= marker.length) break;
    }

    if (closingIndex >= lines.length) {
      output.push(...lines.slice(index));
      break;
    }

    const body = lines.slice(index + 1, closingIndex).join("\n");
    const language = info.trim().split(/\s+/, 1)[0]?.toLowerCase() ?? "";
    const visualKind = inferVisualFenceKind(language, body);
    const markAsVisual =
      visualKind && (visualKind !== "mermaid" || options.markMermaidWhileStreaming !== false);
    output.push(
      markAsVisual ? `${indent}${marker}${STREAMING_VISUAL_FENCE_PREFIX}${visualKind}` : line,
      ...lines.slice(index + 1, closingIndex + 1),
    );
    index = closingIndex;
  }

  return output.join("\n");
}

/**
 * Recover visual blocks when a model closes a longer Markdown fence with a
 * shorter one. JSON recovery stays limited to unambiguous visual payloads;
 * Mermaid recovery requires a recognized diagram header. This keeps following
 * prose outside the code block without reclassifying ordinary fenced code.
 */
export function repairMismatchedVisualFences(content: string): string {
  const source = content.replace(/\r\n?/g, "\n");
  const lines = unwrapOuterMarkdownFence(source).split("\n");
  const output: string[] = [];

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]!;
    const opening = line.match(/^([ \t]*)(`{3,}|~{3,})(.*)$/);
    if (!opening) {
      output.push(line);
      continue;
    }

    const marker = opening[2]!;
    const info = opening[3]!;
    if (marker[0] === "`" && info.includes("`")) {
      output.push(line);
      continue;
    }

    const language = info.trim().split(/\s+/, 1)[0]?.toLowerCase() ?? "";
    const jsonLikeLanguages = new Set(["", "json", "markdown", "md", "text", "txt", "plaintext"]);
    if (!jsonLikeLanguages.has(language) && !normalizeVisualFenceKind(language)) {
      output.push(line);
      continue;
    }

    let properClose = -1;
    for (let closeIndex = index + 1; closeIndex < lines.length; closeIndex += 1) {
      const closing = lines[closeIndex]!.match(/^([ \t]*)(`{3,}|~{3,})[ \t]*$/);
      if (!closing) continue;

      const indent = closing[1]!.length;
      const closeMarker = closing[2]!;
      if (closeMarker[0] === marker[0] && indent <= 3 && closeMarker.length >= marker.length) {
        properClose = closeIndex;
        break;
      }
    }

    const bodyEnd = properClose >= 0 ? properClose : lines.length;
    const body = lines.slice(index + 1, bodyEnd).join("\n");

    if (MERMAID_FENCE_ALIASES.has(language)) {
      let repairedMermaid = false;
      for (let closeIndex = index + 1; closeIndex < bodyEnd; closeIndex += 1) {
        const closing = lines[closeIndex]!.match(/^([ \t]*)(`+|~+)[ \t]*$/);
        if (
          !closing ||
          closing[1]!.length > 3 ||
          closing[2]![0] !== marker[0] ||
          closing[2]!.length >= marker.length
        ) {
          continue;
        }

        const mermaidSource = lines.slice(index + 1, closeIndex).join("\n");
        if (!hasRecognizableMermaidHeader(mermaidSource)) continue;

        output.push(
          line,
          ...lines.slice(index + 1, closeIndex),
          `${closing[1]!}${marker}`,
        );
        index = closeIndex;
        repairedMermaid = true;
        break;
      }
      if (repairedMermaid) continue;
    }

    const visualJson = extractLeadingVisualJson(body);
    const hasTrailingContent = visualJson ? Boolean(body.slice(visualJson.end).trim()) : false;
    if (visualJson && (properClose >= 0 || hasTrailingContent)) {
      const tail = body.slice(visualJson.end);
      const tailLines = tail.split("\n");
      if (tailLines[0] === "") tailLines.shift();
      const firstContentLine = tailLines.findIndex((part) => part.trim());
      if (firstContentLine >= 0 && /^[`~]{3,}$/.test(tailLines[firstContentLine]!.trim())) {
        tailLines.splice(firstContentLine, 1);
      }
      if (properClose < 0) {
        let lastContentLine = tailLines.length - 1;
        while (lastContentLine >= 0 && !tailLines[lastContentLine]!.trim()) lastContentLine -= 1;
        if (lastContentLine >= 0 && /^[`~]{3,}$/.test(tailLines[lastContentLine]!.trim())) {
          tailLines.splice(lastContentLine, 1);
        }
      }
      output.push(
        `\`\`\`${visualJson.kind}`,
        ...visualJson.source.split("\n"),
        "\`\`\`",
        ...tailLines,
        ...(properClose >= 0 ? lines.slice(properClose + 1) : []),
      );
      index = lines.length;
      continue;
    }

    if (properClose >= 0) {
      output.push(...lines.slice(index, properClose + 1));
      index = properClose;
      continue;
    }

    output.push(...lines.slice(index));
    break;
  }

  return output.join("\n");
}

function unwrapOuterMarkdownFence(content: string): string {
  const lines = content.split("\n");
  let first = 0;
  let last = lines.length - 1;
  while (first < lines.length && !lines[first]!.trim()) first += 1;
  while (last > first && !lines[last]!.trim()) last -= 1;
  const opening = lines[first]?.match(/^\s*(`{3,}|~{3,})\s*(?:markdown|md)\s*$/i);
  const closing = lines[last]?.match(/^\s*(`{3,}|~{3,})\s*$/);
  if (!opening || !closing || opening[1]![0] !== closing[1]![0] || closing[1]!.length < 3) {
    return content;
  }
  return [...lines.slice(0, first), ...lines.slice(first + 1, last), ...lines.slice(last + 1)].join(
    "\n",
  );
}

function extractLeadingVisualJson(
  value: string,
): { source: string; end: number; kind: VisualFenceKind } | null {
  const start = value.search(/\S/);
  if (start < 0 || value[start] !== "{") return null;

  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let index = start; index < value.length; index += 1) {
    const character = value[index]!;
    if (inString) {
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === '"') inString = false;
      continue;
    }
    if (character === '"') inString = true;
    else if (character === "{") depth += 1;
    else if (character === "}") {
      depth -= 1;
      if (depth === 0) {
        const source = value.slice(start, index + 1);
        const kind = inferVisualFenceKind("json", source);
        return kind ? { source, end: index + 1, kind } : null;
      }
    }
  }
  return null;
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
      typeof payload.title === "string" &&
      ["steps", "timeline", "comparison", "feature_grid", "stats"].includes(
        String(payload.layout),
      ) &&
      Array.isArray(payload.items) &&
      payload.items.length >= 2 &&
      payload.items.every(
        (item) =>
          item &&
          typeof item === "object" &&
          typeof (item as Record<string, unknown>).title === "string",
      )
    ) {
      return "infographic";
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
      /^```(chart|card|graph|gallery|infographic|mermaid|gantt|mmd|mermaid[-_]gantt)\s*\n([\s\S]*?)\n?```$/i,
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
      /data-rich-content-kind\s*=\s*["'](chart|card|graph|gallery|infographic|mermaid|gantt|mmd|mermaid[-_]gantt)["']/i,
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
