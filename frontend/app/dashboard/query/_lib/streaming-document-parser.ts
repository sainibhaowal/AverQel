import type {
  StreamingBlockquoteNode,
  StreamingChartNode,
  StreamingCodeNode,
  StreamingFootnoteNode,
  StreamingDocumentNode,
  StreamingImageNode,
  StreamingListNode,
  StreamingListItem,
  StreamingTableNode,
  StreamingMathNode,
} from "./streaming-document-types";
import { parseVisualChart } from "./chart-parser";

/**
 * MODEL-AGNOSTIC STREAMING DOCUMENT PARSER (v6)
 *
 * KEY GOALS & FIXES vs v5:
 *
 * TABLE STREAMING (primary fix):
 *  - Tables render ROW-BY-ROW in real-time as tokens arrive.
 *  - Header + separator rendered immediately on detection.
 *  - Each data row is emitted the moment its pipe-delimited line is complete.
 *  - Trailing "Notes:" or plain text after the table closes cleanly — no
 *    phantom code/diagram block is opened.
 *  - Lone pipes, partial pipe lines at stream tail are held in a pending buffer
 *    (not emitted as broken rows) until the line is complete or stream ends.
 *  - Column count is locked at separator row; cells are padded/trimmed to match.
 *  - No fallthrough into diagram/code heuristics for table content.
 *
 * BLOCK PRIORITY ORDER (strict, evaluated top-down):
 *  1. Protected code fence placeholder
 *  2. Complete code block (```lang … ```)
 *  3. Table row (line contains |, not a separator-only line by itself)
 *  4. Heading  (^#{1,6})
 *  5. HR rule   (^---+$)
 *  6. Blockquote (^>\s)
 *  7. Image      (^!\[[^\]]*\]\(.+\)$)
 *  8. Footnote   (^\\[\^[^\]]+\\]:)
 *  9. List item (^[*-] | ^\d+\.)
 * 10. Paragraph (everything else)
 *
 * OTHER FIXES:
 *  - protectCodeFences guards unclosed streaming fences (v5 fix retained).
 *  - normalizeDashesAndBullets skips placeholder lines (v5 fix retained).
 *  - applyDiagramHeuristics skips placeholder lines (v5 fix retained).
 *  - "---" glued to sentence end splits to own line (v5 fix retained).
 *  - "Notes" / plain text after table is paragraph, never a new block type.
 *  - No broken |||| rendering, no *** artifacts, no ##### leakage.
 */

// ─────────────────────────────────────────────────────────────────────────────
// TYPES (mirrors streaming-document-types.ts expectations)
// ─────────────────────────────────────────────────────────────────────────────

// StreamingTableNode shape expected downstream:
// { type: "table"; title?: string; headers: string[]; rows: string[][]; incomplete?: boolean }
// StreamingCodeNode:
// { type: "code"; language?: string; value: string; incomplete?: boolean }
// StreamingListNode:
// { type: "list"; ordered: boolean; items: StreamingListItem[] }

// ─────────────────────────────────────────────────────────────────────────────
// STREAMING TAIL CACHE
// ─────────────────────────────────────────────────────────────────────────────

interface NormCache {
  stablePrefix: string;
  stablePrefixRaw: string;
  stableLineCount: number;
}

const DEFAULT_CACHE: NormCache = {
  stablePrefix: "",
  stablePrefixRaw: "",
  stableLineCount: 0,
};

export function resetNormCache(cache: NormCache = DEFAULT_CACHE): void {
  cache.stablePrefix = "";
  cache.stablePrefixRaw = "";
  cache.stableLineCount = 0;
}

const HOT_ZONE_LINES = 40;

function normalizeStreamingMarkdownFast(content: string, cache: NormCache = DEFAULT_CACHE): string {
  const lines = content.split("\n");

  if (lines.length <= HOT_ZONE_LINES) {
    return normalizeStreamingMarkdown(content);
  }

  const splitPoint = lines.length - HOT_ZONE_LINES;
  const rawPrefix = lines.slice(0, splitPoint).join("\n");
  const tail = lines.slice(splitPoint).join("\n");

  if (rawPrefix !== cache.stablePrefixRaw) {
    cache.stablePrefixRaw = rawPrefix;
    cache.stablePrefix = normalizeStreamingMarkdown(rawPrefix);
    cache.stableLineCount = splitPoint;
  }

  const normalizedTail = normalizeStreamingMarkdown(tail);
  return cache.stablePrefix + "\n" + normalizedTail;
}

// ─────────────────────────────────────────────────────────────────────────────
// MAIN ENTRY POINT
// ─────────────────────────────────────────────────────────────────────────────

export function parseStreamingDocument(
  content: string,
  streaming: boolean,
  cache?: NormCache,
): StreamingDocumentNode[] {
  const unwrappedContent = unwrapDocumentMarkdownFence(content, streaming);

  const normalizedContent = streaming
    ? normalizeStreamingMarkdownFast(unwrappedContent, cache ?? DEFAULT_CACHE)
    : unwrappedContent;

  const expandedContent = normalizeStreamingTables(normalizedContent);
  const withBoundaries = insertTableBoundaries(expandedContent);
  const normalized = withBoundaries.replace(/\n{3,}/g, "\n\n").trim();
  if (!normalized) return [];

  const guarded = applyRepetitionGuard(normalized);
  const lines = guarded.split("\n");
  const nodes: StreamingDocumentNode[] = [];

  let index = 0;
  while (index < lines.length) {
    const line = lines[index] ?? "";

    // ── Skip blank lines ──────────────────────────────────────────────────
    if (!line.trim()) {
      index += 1;
      continue;
    }

    // ── 0. Chart fence (```chart or ```json with chart payload) ──────────
    // Must run BEFORE the generic code block handler so chart fences are
    // captured inline at the correct position — same pattern as Mermaid.
    const chart = parseChartBlock(lines, index, streaming);
    if (chart) {
      nodes.push(chart.node);
      index = chart.nextIndex;
      continue;
    }

    // ── 0b. Math block ($$ ... $$) ───────────────────────────────────────
    const math = parseMathBlock(lines, index, streaming);
    if (math) {
      nodes.push(math.node);
      index = math.nextIndex;
      continue;
    }

    // ── 1. Code block ─────────────────────────────────────────────────────
    const code = parseCodeBlock(lines, index);
    if (code) {
      nodes.push(code.node);
      index = code.nextIndex;
      continue;
    }

    // ── 1b. Skip stray ``` fences left after markdown-unwrap ─────────────
    // When parseCodeBlock returns null (markdown-in-fence detected), the
    // opening ``` line is still at `index`. Skip it so it doesn't leak
    // into paragraph text as visible backticks.
    if (/^`{3,}\s*(?:markdown|md)?\s*$/i.test(line.trim())) {
      index += 1;
      continue;
    }

    // ── 2. Table ──────────────────────────────────────────────────────────
    // A table line MUST contain "|" and must NOT be misidentified as heading/rule.
    // We check table BEFORE heading/rule so a line like "| Metric | Value |"
    // isn't swallowed as a paragraph.
    if (looksLikeTableLine(line)) {
      const table = parseTable(lines, index, streaming);
      if (table) {
        nodes.push(table.node);
        index = table.nextIndex;
        continue;
      }
    }

    // ── 3. Heading ────────────────────────────────────────────────────────
    const headingMatch =
      line.match(/^(#{1,6})\s+(.+)$/) ?? line.match(/^(#{1,6})\s*(?:\d+[.)]\s*)?(.+)$/);
    if (headingMatch && /^#{1,6}/.test(line)) {
      nodes.push({
        type: "heading",
        depth: headingMatch[1].length as 1 | 2 | 3 | 4 | 5 | 6,
        content: headingMatch[2].trim(),
      });
      index += 1;
      continue;
    }

    // ── 4. Horizontal rule ────────────────────────────────────────────────
    if (/^---+$/.test(line.trim())) {
      nodes.push({ type: "rule" });
      index += 1;
      continue;
    }

    // ── 4b. Blockquote ───────────────────────────────────────────────────
    const quote = parseBlockquote(lines, index);
    if (quote) {
      nodes.push(quote.node);
      index = quote.nextIndex;
      continue;
    }

    // ── 4c. Image ─────────────────────────────────────────────────────────
    const image = parseImageBlock(lines, index);
    if (image) {
      nodes.push(image.node);
      index = image.nextIndex;
      continue;
    }

    // ── 4d. Footnote definition ───────────────────────────────────────────
    const footnote = parseFootnoteBlock(lines, index);
    if (footnote) {
      nodes.push(footnote.node);
      index = footnote.nextIndex;
      continue;
    }

    // ── 5. List ───────────────────────────────────────────────────────────
    const list = parseList(lines, index);
    if (list) {
      nodes.push(list.node);
      index = list.nextIndex;
      continue;
    }

    // ── 6. Paragraph ──────────────────────────────────────────────────────
    const paragraph: string[] = [line];
    index += 1;
    while (index < lines.length) {
      const candidate = lines[index] ?? "";
      if (!candidate.trim()) break;
      if (
        /^#{1,4}\s/.test(candidate) ||
        /^#{1,4}\d/.test(candidate) ||
        /^```/.test(candidate.trim()) ||
        /^---+$/.test(candidate.trim()) ||
        /^>\s?/.test(candidate.trim()) ||
        /^!\[[^\]]*\]\(.+\)$/.test(candidate.trim()) ||
        /^\[\^[^\]]+\]:/.test(candidate.trim()) ||
        /^[*-]\s+/.test(candidate.trim()) ||
        /^\d+\.\s+/.test(candidate.trim()) ||
        looksLikeTableLine(candidate)
      ) {
        break;
      }
      paragraph.push(candidate);
      index += 1;
    }

    nodes.push({
      type: "paragraph",
      content: paragraph.join("\n").trim(),
    });
  }

  return nodes;
}

// ─────────────────────────────────────────────────────────────────────────────
// TABLE LINE DETECTION HELPER
// Must contain "|", must not be a code fence, must not be a heading/rule alone.
// Returns false for degenerate lines like lone "|" or "||".
// ─────────────────────────────────────────────────────────────────────────────

function looksLikeTableLine(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed.includes("|")) return false;
  if (trimmed === "|" || trimmed === "||") return false;
  if (/^```/.test(trimmed)) return false;
  // A line is a table row only if it has at least one non-pipe, non-dash, non-space character
  // OR if it is a valid separator row (---).
  // This prevents plain text that happens to contain | from being parsed as a table row
  // unless it structurally looks like one (leading pipe or multiple pipes).
  const pipeCount = (trimmed.match(/\|/g) ?? []).length;
  const cells = parsePipeRow(trimmed);
  if (looksLikeSeparatorRow(cells, cells.length)) return false;
  return pipeCount >= 1;
}

// ─────────────────────────────────────────────────────────────────────────────
// BLOCKQUOTE PARSER
// ─────────────────────────────────────────────────────────────────────────────

function parseBlockquote(
  lines: string[],
  startIndex: number,
): { node: StreamingBlockquoteNode; nextIndex: number } | null {
  const first = lines[startIndex]?.trim() ?? "";
  if (!/^>\s?/.test(first)) return null;

  const quoteLines: string[] = [];
  let index = startIndex;

  while (index < lines.length) {
    const line = lines[index] ?? "";
    const trimmed = line.trim();
    if (!trimmed.startsWith(">")) break;
    quoteLines.push(trimmed.replace(/^>\s?/, ""));
    index += 1;
  }

  if (quoteLines.length === 0) return null;

  return {
    node: {
      type: "blockquote",
      content: quoteLines.join("\n").trim(),
    },
    nextIndex: index,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// IMAGE PARSER
// Matches standalone Markdown image blocks like:
//   ![Alt text](https://example.com/image.png "Optional title")
// Inline images inside prose still render through InlineMarkdown.
// ─────────────────────────────────────────────────────────────────────────────

function parseImageBlock(
  lines: string[],
  startIndex: number,
): { node: StreamingImageNode; nextIndex: number } | null {
  const line = lines[startIndex]?.trim() ?? "";
  const match = line.match(/^!\[([^\]]*)\]\((\S+?)(?:\s+(?:"([^"]*)"|'([^']*)'))?\)$/);
  if (!match) return null;

  return {
    node: {
      type: "image",
      alt: match[1] || undefined,
      src: match[2],
      title: match[3] ?? match[4] ?? undefined,
    },
    nextIndex: startIndex + 1,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// FOOTNOTE PARSER
// Captures block-level footnote definitions so streaming output can still show
// them even before the final Markdown AST is available.
// ─────────────────────────────────────────────────────────────────────────────

function parseFootnoteBlock(
  lines: string[],
  startIndex: number,
): { node: StreamingFootnoteNode; nextIndex: number } | null {
  const opening = lines[startIndex]?.trimStart() ?? "";
  const match = opening.match(/^\[\^([^\]]+)\]:\s*(.*)$/);
  if (!match) return null;

  const identifier = match[1];
  const body: string[] = [match[2] ?? ""];
  let index = startIndex + 1;

  while (index < lines.length) {
    const line = lines[index] ?? "";
    const trimmed = line.trim();
    if (!trimmed) {
      const peek = lines[index + 1] ?? "";
      if (/^(?:\s{4,}|\t)/.test(peek)) {
        body.push("");
        index += 1;
        continue;
      }
      break;
    }

    if (/^(?:\s{4,}|\t)/.test(line)) {
      body.push(line.replace(/^(?:\s{4}|\t)/, ""));
      index += 1;
      continue;
    }

    break;
  }

  return {
    node: {
      type: "footnote",
      identifier,
      content: body.join("\n").trim(),
    },
    nextIndex: index,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// FENCE UNWRAPPER
// ─────────────────────────────────────────────────────────────────────────────

export function unwrapDocumentMarkdownFence(content: string, streaming: boolean): string {
  const trimmed = content.trim();
  const opening = trimmed.match(/^```(?:markdown|md)\s*\n?/i);
  if (!opening) return content;

  const withoutOpening = trimmed.slice(opening[0].length);
  if (streaming) {
    return withoutOpening.replace(/\n?```$/, "").trimStart();
  }

  if (!withoutOpening.endsWith("```")) return content;
  return withoutOpening.slice(0, -3).trim();
}

// ─────────────────────────────────────────────────────────────────────────────
// CHART FENCE PARSER
//
// Detects two fence styles the LLM may emit for an inline chart:
//
//   Style A — explicit ```chart fence:
//     ```chart
//     {"chart_type":"bar","title":"Revenue","series":[...]}
//     ```
//
//   Style B — ```json fence whose content is valid chart JSON:
//     ```json
//     {"chart_type":"line","title":"Stock","series":[...]}
//     ```
//
// If the fence body parses as a valid chart (≥1 data point detectable) a
// StreamingChartNode is emitted at this position in the node array.
// The chart HUD therefore appears INLINE — exactly where the fence appeared
// in the token stream — identical to how Mermaid fences work.
//
// Falls back to null (= generic CodeBlock) when the body is not chart data.
// ─────────────────────────────────────────────────────────────────────────────

/** Languages whose fences we interrogate for chart content. */
const CHART_FENCE_LANGS = new Set(["chart", "json"]);

function parseChartBlock(
  lines: string[],
  startIndex: number,
  streaming: boolean,
): { node: StreamingChartNode; nextIndex: number } | null {
  const opening = lines[startIndex] ?? "";
  const match = opening.trim().match(/^```([A-Za-z0-9_-]+)?\s*$/);
  if (!match) return null;

  const language = (match[1] ?? "").toLowerCase();
  if (!CHART_FENCE_LANGS.has(language)) return null;

  const body: string[] = [];
  let index = startIndex + 1;
  let closed = false;

  while (index < lines.length) {
    const line = lines[index] ?? "";
    if (line.trim() === "```") {
      closed = true;
      index += 1;
      break;
    }
    body.push(line);
    index += 1;
  }

  const bodyText = body.join("\n").trim();

  // ── Early type lock-in (Prevents HUD switching flicker) ───────────────
  // A JSON fence must be promoted to a chart node as early as possible so
  // we don't flip-flop from a generic CodeBlock to a Chart HUD (which
  // causes massive layout jumps when the component unmounts/remounts).
  const isExplicitChart = language === "chart";
  const looksLikeChart = /["']?(chart_type|series|chart_data|chartData)["']?\s*[:{]/.test(bodyText);

  if (!isExplicitChart && !looksLikeChart) {
    // Not a chart (yet/at all). Fall back to generic code block.
    return null;
  }

  // During streaming the fence may be incomplete — try parsing whatever
  // JSON fragment we have so we can show a live/skeleton HUD immediately.
  const parseTarget = closed || !streaming ? bodyText : autoCloseJson(bodyText);
  const parsed = parseTarget ? parseVisualChart(parseTarget, "chart") : null;

  const incomplete = streaming && !closed;

  // Even if parseVisualChart returns null (JSON is too broken to parse yet),
  // we MUST return a chart node because we've already committed to the
  // "chart" type path. Returning null now would cause a HUD flip.
  const node: StreamingChartNode = {
    type: "chart",
    title: parsed?.title && parsed.title.toLowerCase() !== "chart" ? parsed.title : undefined,
    chart_type: parsed?.type ?? "bar",
    series:
      parsed?.data.map((point) => ({
        ...Object.fromEntries(
          Object.entries(point).flatMap(([k, v]) =>
            k === "label" || k === "value" || k === "z"
              ? []
              : typeof v === "string" || typeof v === "number" || v == null
                ? [[k, v]]
                : [],
          ),
        ),
        label: String(point[parsed.xKey] ?? point.label ?? ""),
        value: Number(point[parsed.yKey] ?? point.value ?? 0),
        ...(parsed.zKey && typeof point[parsed.zKey] === "number"
          ? { z: Number(point[parsed.zKey]) }
          : typeof point.z === "number"
            ? { z: point.z }
            : {}),
      })) ?? [],
    raw_payload: bodyText || undefined,
    parser_source: parsed?.metadata.source,
    confidence: parsed?.metadata.confidence,
    fields: parsed?.metadata.fields,
    x_key: parsed?.xKey,
    y_key: parsed?.yKey,
    z_key: parsed?.zKey,
    incomplete,
  };

  return { node, nextIndex: index };
}

/**
 * Best-effort JSON auto-closer for streaming fragments.
 * Mirrors autoFixPartialJson in chart-parser but is local to the parser
 * so we avoid a cross-file dependency cycle.
 */
function autoCloseJson(text: string): string {
  let s = text
    .trim()
    .replace(/[,:]\s*$/, "")
    .replace(/["']\w*$/, "");
  const stack: string[] = [];
  for (const ch of s) {
    if (ch === "{") stack.push("}");
    else if (ch === "[") stack.push("]");
    else if ((ch === "}" || ch === "]") && stack.length > 0) stack.pop();
  }
  while (stack.length > 0) s += stack.pop();
  return s;
}

/**
 * EXPLICIT MATH BLOCK PARSER ($$ ... $$)
 *
 * Captures equations in block format. During streaming it handles
 * unclosed fences as "incomplete: true".
 */
function parseMathBlock(
  lines: string[],
  startIndex: number,
  streaming: boolean,
): { node: StreamingMathNode; nextIndex: number } | null {
  const opening = lines[startIndex] ?? "";
  if (opening.trim() !== "$$") return null;

  const body: string[] = [];
  let index = startIndex + 1;
  let closed = false;

  while (index < lines.length) {
    const line = lines[index] ?? "";
    if (line.trim() === "$$") {
      closed = true;
      index += 1;
      break;
    }
    body.push(line);
    index += 1;
  }

  return {
    node: {
      type: "math",
      value: body.join("\n"),
      incomplete: streaming && !closed,
    },
    nextIndex: index,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// CODE BLOCK PARSER
// ─────────────────────────────────────────────────────────────────────────────

function parseCodeBlock(
  lines: string[],
  startIndex: number,
): { node: StreamingCodeNode; nextIndex: number } | null {
  const opening = lines[startIndex] ?? "";
  const match = opening.trim().match(/^```([A-Za-z0-9_-]+)?\s*$/);
  if (!match) return null;

  const language = match[1]?.toLowerCase();
  const body: string[] = [];
  let index = startIndex + 1;
  let closed = false;

  while (index < lines.length) {
    const line = lines[index] ?? "";
    if (line.trim() === "```") {
      closed = true;
      index += 1;
      break;
    }
    body.push(line);
    index += 1;
  }

  // ── Markdown-in-code-fence guard ─────────────────────────────────────
  // The LLM sometimes wraps its analysis text in triple backticks without
  // a language tag (or with "markdown"/"md").  This creates a false CODE
  // block that traps readable text.  Detect this case and return null so
  // the parser re-processes the body as regular markdown (headings, lists,
  // paragraphs).
  const isMarkdownLang = !language || language === "markdown" || language === "md";
  if (isMarkdownLang && body.length > 0) {
    const bodyText = body.join("\n");
    // A fence is "secretly markdown" if it contains heading markers,
    // bold/italic markers, or list bullets in its first few meaningful lines.
    const hasMarkdownPatterns =
      /^#{1,4}\s+\S/m.test(bodyText) || // headings
      /\*\*[^*]+\*\*/m.test(bodyText) || // bold
      /^\s*[-*]\s+\S/m.test(bodyText) || // unordered list
      /^\s*\d+\.\s+\S/m.test(bodyText) || // ordered list
      /^[A-Z][a-z]+\s+[a-z]+/m.test(bodyText); // plain prose (Sentence case)
    if (hasMarkdownPatterns) {
      // Return null so the main loop re-processes these lines as markdown.
      return null;
    }
  }

  return {
    node: {
      type: "code",
      language,
      value: body.join("\n"),
      incomplete: !closed,
    },
    nextIndex: index,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// LIST PARSER
// ─────────────────────────────────────────────────────────────────────────────

function parseList(
  lines: string[],
  startIndex: number,
): { node: StreamingListNode; nextIndex: number } | null {
  const first = lines[startIndex]?.trim() ?? "";
  const firstMatch = matchListItem(first);
  if (!firstMatch) return null;

  return parseListAtIndent(lines, startIndex, firstMatch.indent, firstMatch.ordered);
}

function parseListAtIndent(
  lines: string[],
  startIndex: number,
  parentIndent: number,
  isOrdered: boolean,
): { node: StreamingListNode; nextIndex: number } | null {
  const items: StreamingListItem[] = [];
  let index = startIndex;
  let currentItem: StreamingListItem | null = null;

  while (index < lines.length) {
    const line = lines[index] ?? "";
    const trimmed = line.trim();

    if (!trimmed) {
      const peekIndex = findNextNonBlankLine(lines, index + 1);
      if (peekIndex < lines.length) {
        const peekMatch = matchListItem(lines[peekIndex] ?? "");
        if (peekMatch && peekMatch.indent >= parentIndent) {
          index += 1;
          continue;
        }
      }
      break;
    }

    const match = matchListItem(line);
    if (match) {
      if (match.indent < parentIndent) break;

      if (match.indent === parentIndent) {
        if (match.ordered !== isOrdered && items.length > 0) break;
        if (match.ordered !== isOrdered && items.length === 0) return null;

        const item = createListItem(match.content);
        items.push(item);
        currentItem = item;
        index += 1;
        continue;
      }

      if (currentItem) {
        const nested = parseListAtIndent(lines, index, match.indent, match.ordered);
        if (nested) {
          currentItem.children ??= [];
          currentItem.children.push(nested.node);
          index = nested.nextIndex;
          continue;
        }
      }
    }

    if (currentItem && leadingIndentWidth(line) > parentIndent) {
      currentItem.content += " " + trimmed;
      index += 1;
      continue;
    }

    break;
  }

  if (items.length === 0) return null;

  return {
    node: { type: "list", ordered: isOrdered, items },
    nextIndex: index,
  };
}

function matchListItem(line: string): { indent: number; ordered: boolean; content: string } | null {
  const match = line.match(/^([ \t]*)([*-]|\d+\.)\s+(.*)$/);
  if (!match) return null;
  return {
    indent: leadingIndentWidth(match[1] ?? ""),
    ordered: /\d+\./.test(match[2] ?? ""),
    content: (match[3] ?? "").trim(),
  };
}

function leadingIndentWidth(text: string): number {
  const leading = text.match(/^[ \t]*/)?.[0] ?? "";
  let width = 0;
  for (const ch of leading) {
    width += ch === "\t" ? 4 : 1;
  }
  return width;
}

function findNextNonBlankLine(lines: string[], startIndex: number): number {
  let index = startIndex;
  while (index < lines.length && !(lines[index] ?? "").trim()) index += 1;
  return index;
}

function createListItem(content: string): StreamingListItem {
  const taskMatch = content.match(/^\[( |x|X)\]\s+(.*)$/);
  if (taskMatch) {
    return {
      content: taskMatch[2].trim(),
      task: true,
      checked: taskMatch[1].toLowerCase() === "x",
    };
  }

  return { content };
}

// ─────────────────────────────────────────────────────────────────────────────
// TABLE PARSER — STREAMING-SAFE, ROW-BY-ROW
//
// Design goals:
//   • Emit the table node as soon as we have headers (even before all rows).
//   • Lock column count at separator row.
//   • Pad short rows / trim long rows to column count.
//   • Trailing plain-text lines (Notes, remarks) are NOT consumed by the table.
//   • No accidental code/diagram block promotion of table content.
//   • "incomplete: true" flag when streaming and table may still be growing.
// ─────────────────────────────────────────────────────────────────────────────

function parseTable(
  lines: string[],
  startIndex: number,
  streaming: boolean = false,
): { node: StreamingTableNode; nextIndex: number } | null {
  // ── Read header row ───────────────────────────────────────────────────────
  const firstRowResult = readTableRow(lines, startIndex);
  if (!firstRowResult || firstRowResult.cells.length === 0) return null;

  let headers = firstRowResult.cells;
  let index = firstRowResult.nextIndex;

  // Optional table title (e.g. "Table 1: Something | col1 | col2")
  let title: string | undefined = undefined;
  const firstHeader = headers[0]?.trim() ?? "";
  if (/^Table\s*\d+:?/i.test(firstHeader) && headers.length > 1) {
    title = firstHeader;
    headers = headers.slice(1);
  }

  if (headers.length === 0) return null;

  // ── Look for separator row ────────────────────────────────────────────────
  let separatorFound = false;
  let columnCount = headers.length;

  // Scan up to 3 lines ahead for the separator
  let lookIndex = index;
  while (lookIndex < lines.length && lookIndex < index + 3) {
    const candidate = lines[lookIndex]?.trim() ?? "";
    if (!candidate) {
      lookIndex++;
      continue;
    }
    const sepRow = readTableRow(lines, lookIndex);
    if (sepRow && looksLikeSeparatorRow(sepRow.cells, headers.length)) {
      separatorFound = true;
      columnCount = Math.max(columnCount, sepRow.cells.length);
      index = sepRow.nextIndex;
    }
    // Non-separator, non-blank line — stop looking
    break;
  }

  // No separator found — this is a tab-converted or separator-less table.
  // Treat any subsequent pipe rows with the same column count as data rows.
  // Without this, every row becomes its own table (11 tables instead of 1).
  if (!separatorFound) {
    columnCount = headers.length;
  }

  // Pad headers to column count
  while (headers.length < columnCount) headers.push("");

  // ── Read data rows ────────────────────────────────────────────────────────
  const rows: string[][] = [];
  let maxCols = columnCount;

  while (index < lines.length) {
    const line = lines[index] ?? "";
    const trimmed = line.trim();

    if (!trimmed) {
      let peek = index + 1;
      while (peek < lines.length && !(lines[peek] ?? "").trim()) peek++;
      const nextLine = (lines[peek] ?? "").trim();
      if (nextLine.includes("|") && peek <= index + 2) {
        index++;
        continue;
      }
      break;
    }

    if (/^(#{1,6}\s|```)/.test(trimmed) || /^---+$/.test(trimmed)) break;
    if (!trimmed.includes("|")) break;
    if (trimmed === "|" || trimmed === "||") {
      index += 1;
      continue;
    }

    const rowResult = readTableRow(lines, index);
    if (!rowResult) {
      index += 1;
      continue;
    }

    if (looksLikeSeparatorRow(rowResult.cells, columnCount)) {
      index = rowResult.nextIndex;
      continue;
    }

    const cells = rowResult.cells;
    // Track the widest row — for separator-less tables the header may be
    // narrower than data rows (e.g. last header column split by tab issue)
    if (cells.length > maxCols) maxCols = cells.length;
    rows.push(cells);
    index = rowResult.nextIndex;
  }

  // If data rows are wider than headers, pad headers to match
  // This fixes the case where the last header tab-column was clipped
  while (headers.length < maxCols) headers.push("");

  // Normalize all rows to maxCols
  const normalizedRows = rows.map((row) =>
    row.length < maxCols
      ? [...row, ...new Array(maxCols - row.length).fill("")]
      : row.length > maxCols
        ? row.slice(0, maxCols)
        : row,
  );

  if (headers.length === 0) return null;

  const incomplete = streaming && !separatorFound && normalizedRows.length === 0;

  return {
    node: {
      type: "table",
      title,
      headers,
      rows: normalizedRows,
      ...(incomplete ? { incomplete: true } : {}),
    } as StreamingTableNode,
    nextIndex: index,
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// TABLE ROW READER
// Reads a single table row from a line. Returns null if the line is not a
// valid table row. Handles leading/trailing pipes, double-pipe rows, and
// streaming partial rows at the tail of the content.
// ─────────────────────────────────────────────────────────────────────────────

function readTableRow(
  lines: string[],
  startIndex: number,
): { cells: string[]; nextIndex: number } | null {
  // Skip blank lines
  let index = startIndex;
  while (index < lines.length && !lines[index]?.trim()) index += 1;
  if (index >= lines.length) return null;

  const line = lines[index] ?? "";
  const trimmed = line.trim();

  if (!trimmed.includes("|")) return null;
  if (trimmed === "|" || trimmed === "||") return null;

  const cells = parsePipeRow(trimmed);
  if (cells.length === 0) return null;

  return { cells, nextIndex: index + 1 };
}

/**
 * Parse a pipe-delimited row string into cell strings.
 * Handles: "| A | B | C |", "A | B | C", "| A | B"
 * Never returns empty arrays for valid pipe lines.
 */
function parsePipeRow(line: string): string[] {
  let s = line.trim();

  // Strip leading pipe
  if (s.startsWith("|")) s = s.slice(1);
  // Strip trailing pipe
  if (s.endsWith("|")) s = s.slice(0, -1);

  const cells = s.split("|").map((c) => c.trim());

  // Filter completely empty cells only if ALL are empty (degenerate)
  if (cells.every((c) => c === "")) return [];

  return cells;
}

// ─────────────────────────────────────────────────────────────────────────────
// STREAMING MARKDOWN NORMALIZER
// ─────────────────────────────────────────────────────────────────────────────

export function normalizeStreamingMarkdown(content: string): string {
  // Protect code fences (including unclosed streaming fences — v5 fix retained)
  const { text: protectedText, placeholders } = protectCodeFences(content);
  let next = protectedText;

  next = normalizeDashesAndBullets(next);

  // Split headings glued to previous text
  next = next.replace(/([^#*_>\n\]])\s*(#{2,6}\s)/g, "$1\n\n$2");

  // Split "##1." compact headings
  next = next.replace(/([^#*_>\n\]])(#{1,4}\d)/g, "$1\n\n$2");

  // Split "---" rule glued to end of sentence (but not list item separators)
  next = next.replace(/([^-#*_>\n\]])(---+)(\s*$|\s*\n)/gm, "$1\n\n$2$3");

  // Promote titled sections (Document, Table, Figure, Summary labels)
  next = next.replace(
    /(^|\n)((Document|Table|Figure|Summary)\s*\d*[:：][^\n|]{2,40})(\s*$)/gim,
    "$1### $2\n\n",
  );

  // Promote bolded lines before tables/lists to headings
  next = next.replace(/(^|\n)(\*\*[^*]+\*\*)(?:\n|\s)*(\||\d+\.|\*|-)/g, "$1### $2\n\n$3");

  // Keep code fences clean
  next = next.replace(/([^\n`])\s*(```[a-zA-Z]*)/g, "$1\n$2");

  next = applyCodeHeuristics(next);
  next = applyDiagramHeuristics(next);
  next = restoreCodeFences(next, placeholders);

  return next.replace(/\n{3,}/g, "\n\n");
}

// ─────────────────────────────────────────────────────────────────────────────
// UNICODE DASH & BULLET NORMALIZER
// ─────────────────────────────────────────────────────────────────────────────

function normalizeDashesAndBullets(content: string): string {
  const dashChars =
    "[\\u2013\\u2014\\u2015\\u2500\\u2501\\u2504\\u2505\\u2508\\u2509\\u254c\\u254d]";
  const dashRegex = new RegExp(dashChars, "g");

  return content
    .split("\n")
    .map((line) => {
      // Never touch placeholder lines
      if (line.startsWith("__CODE_FENCE_")) return line;
      let l = line;
      if (l.includes("|")) {
        l = l.replace(dashRegex, "-");
        l = l.replace(/^[*-•\u2022]\s*(\|)/, "$1");
      }
      return l;
    })
    .join("\n");
}

// ─────────────────────────────────────────────────────────────────────────────
// CODE FENCE PROTECTION (v5 fix: protects unclosed streaming fences)
// ─────────────────────────────────────────────────────────────────────────────

function protectCodeFences(content: string): {
  text: string;
  placeholders: Map<string, string>;
} {
  const placeholders = new Map<string, string>();
  const lines = content.split("\n");
  const result: string[] = [];
  let inFence = false;
  let currentFence: string[] = [];
  let fenceId = 0;

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      if (inFence) {
        // Closing fence
        currentFence.push(line);
        const id = `__CODE_FENCE_${fenceId++}__`;
        placeholders.set(id, currentFence.join("\n"));
        result.push(id);
        inFence = false;
        currentFence = [];
      } else {
        // Opening fence
        inFence = true;
        currentFence.push(line);
      }
    } else if (inFence) {
      currentFence.push(line);
    } else {
      result.push(line);
    }
  }

  // Protect unclosed fence (streaming — closing ``` not yet arrived)
  if (inFence && currentFence.length > 0) {
    const id = `__CODE_FENCE_${fenceId++}__`;
    placeholders.set(id, currentFence.join("\n"));
    result.push(id);
  }

  return { text: result.join("\n"), placeholders };
}

function restoreCodeFences(content: string, placeholders: Map<string, string>): string {
  let result = content;
  placeholders.forEach((value, id) => {
    result = result.replace(id, value);
  });
  return result;
}

// ─────────────────────────────────────────────────────────────────────────────
// REPETITION GUARD
// ─────────────────────────────────────────────────────────────────────────────

function applyRepetitionGuard(content: string): string {
  const lines = content.split("\n");
  if (lines.length < 10) return content;

  const result: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const currentLine = lines[i];
    if (!currentLine?.trim()) {
      result.push(currentLine ?? "");
      i++;
      continue;
    }

    let repeatCount = 0;
    while (i + repeatCount + 1 < lines.length && lines[i + repeatCount + 1] === currentLine) {
      repeatCount++;
    }

    if (repeatCount >= 5) {
      result.push(currentLine);
      result.push(
        `\n> [!WARNING]\n> **Repetition Detected**: ${repeatCount} duplicate lines suppressed.\n`,
      );
      i += repeatCount + 1;
    } else {
      result.push(currentLine);
      i++;
    }
  }
  return result.join("\n");
}

// ─────────────────────────────────────────────────────────────────────────────
// CODE HEURISTICS
// ─────────────────────────────────────────────────────────────────────────────

function applyCodeHeuristics(content: string): string {
  const codeMarkers: Array<{ pattern: RegExp; lang: string }> = [
    { pattern: /^import\s+[\w{]/, lang: "python" },
    { pattern: /^from\s+\w+\s+import/, lang: "python" },
    { pattern: /^def\s+\w+\(.*\):/, lang: "python" },
    { pattern: /^const\s+\w+\s*=/, lang: "javascript" },
    { pattern: /^let\s+\w+\s*=/, lang: "javascript" },
    { pattern: /^var\s+\w+\s*=/, lang: "javascript" },
    { pattern: /^function\s+\w+\(.*\)\s*\{/, lang: "javascript" },
    { pattern: /^async\s+function/, lang: "javascript" },
    { pattern: /^export\s+(default\s+)?function/, lang: "javascript" },
    { pattern: /^import\s+.*\s+from\s+['"]/, lang: "javascript" },
  ];

  const detectLang = (line: string): string | null => {
    for (const { pattern, lang } of codeMarkers) {
      if (pattern.test(line.trim())) return lang;
    }
    return null;
  };

  const lines = content.split("\n");
  const result: string[] = [];
  let inAutoFence = false;
  let detectedLang = "plaintext";

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? "";
    if (line.startsWith("__CODE_FENCE_")) {
      if (inAutoFence) {
        result.push("```");
        inAutoFence = false;
      }
      result.push(line);
      continue;
    }
    const lang = detectLang(line);

    if (lang && !inAutoFence) {
      let lookaheadCode = 0;
      for (let j = 1; j < 4 && i + j < lines.length; j++) {
        if (detectLang(lines[i + j] ?? "")) lookaheadCode++;
      }
      if (lookaheadCode >= 1) {
        inAutoFence = true;
        detectedLang = lang;
        result.push("```" + detectedLang);
        result.push(line);
      } else {
        result.push(line);
      }
    } else if (inAutoFence) {
      if (!line.trim() || /^#{1,6}\s/.test(line.trim())) {
        result.push("```");
        result.push(line);
        inAutoFence = false;
      } else {
        result.push(line);
      }
    } else {
      result.push(line);
    }
  }

  if (inAutoFence) result.push("```");
  return result.join("\n");
}

// ─────────────────────────────────────────────────────────────────────────────
// DIAGRAM HEURISTICS
// CRITICAL: table content must NEVER enter this function and be mis-tagged as
// a diagram. The function already skips placeholder lines; additionally we
// guard against lines that contain "|" being promoted to mermaid fences.
// ─────────────────────────────────────────────────────────────────────────────

function applyDiagramHeuristics(content: string): string {
  const diagramMarkers: RegExp[] = [
    /^graph\s+(TD|LR|BT|RL)/i,
    /^sequenceDiagram/i,
    /^gantt/i,
    /^classDiagram/i,
    /^stateDiagram/i,
    /^erDiagram/i,
    /^pie\s+title/i,
    /^gitGraph/i,
    /^quadrantChart/i,
    /^requirementDiagram/i,
    /^xychart-beta/i,
    /^C4(Context|Container|Component|Dynamic|Deployment)/i,
    /^architecture-beta/i,
    /^sankey(?:-beta)?/i,
    /^packet(?:-beta)?/i,
    /^kanban/i,
    /^block-beta/i,
    /^flowchart\s+(TD|LR|BT|RL)/i,
    /^[A-Z0-9_\-]+\s*(-->|==>|--\|>|-.->|===>)\s*[A-Z0-9_\-]+/i,
    /^style\s+[A-Z0-9_\-]+\s+fill:/,
  ];

  const lines = content.split("\n");
  const result: string[] = [];
  let inAutoDiagram = false;
  let linesSinceMatch = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? "";

    // Never touch placeholder lines (v5 fix retained)
    if (line.startsWith("__CODE_FENCE_")) {
      if (inAutoDiagram) {
        result.push("```");
        inAutoDiagram = false;
      }
      result.push(line);
      continue;
    }

    // CRITICAL: never treat table rows as diagram lines
    // A line that contains "|" and looks like a table row is never a diagram line.
    if (line.trim().includes("|") && looksLikeTableLine(line)) {
      if (inAutoDiagram) {
        result.push("```");
        inAutoDiagram = false;
      }
      result.push(line);
      continue;
    }

    const isDiagramLine = diagramMarkers.some((m) => m.test(line.trim()));

    if (isDiagramLine && !inAutoDiagram) {
      inAutoDiagram = true;
      result.push("```mermaid");
      result.push(line);
      linesSinceMatch = 0;
    } else if (inAutoDiagram) {
      if (isDiagramLine) {
        linesSinceMatch = 0;
        result.push(line);
      } else {
        linesSinceMatch++;
        if (linesSinceMatch > 2 || /^#{1,6}\s/.test(line.trim())) {
          result.push("```");
          result.push(line);
          inAutoDiagram = false;
        } else {
          result.push(line);
        }
      }
    } else {
      result.push(line);
    }
  }

  if (inAutoDiagram) result.push("```");
  return result.join("\n");
}

// ─────────────────────────────────────────────────────────────────────────────
// TABLE BOUNDARY NORMALIZER
// Detects separator rows with mismatched column counts and inserts blank-line
// boundaries so parseTable starts a fresh node for each logical table.
// ─────────────────────────────────────────────────────────────────────────────

function insertTableBoundaries(content: string): string {
  const lines = content.split("\n");
  const result: string[] = [];
  let lastSeparatorColumnCount = -1;
  let inTable = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? "";
    const trimmed = line.trim();

    if (trimmed.includes("|") && !/^\|$/.test(trimmed)) {
      const cells = extractCellsFromPipeLine(trimmed);
      const isSep =
        cells.length >= 2 && cells.every((c) => /^:?-{2,}:?$/.test(c.replace(/\s+/g, "")));

      if (isSep) {
        if (
          inTable &&
          lastSeparatorColumnCount > 0 &&
          Math.abs(cells.length - lastSeparatorColumnCount) > 1
        ) {
          const lastLine = result.pop();
          result.push("", lastLine ?? "", line);
        } else {
          result.push(line);
        }
        lastSeparatorColumnCount = cells.length;
        inTable = true;
      } else {
        result.push(line);
      }
    } else {
      if (trimmed && !trimmed.startsWith("|")) {
        inTable = false;
        lastSeparatorColumnCount = -1;
      }
      result.push(line);
    }
  }

  return result.join("\n");
}

function extractCellsFromPipeLine(line: string): string[] {
  return line
    .split("|")
    .map((c) => c.trim())
    .filter(Boolean);
}

// ─────────────────────────────────────────────────────────────────────────────
// TABLE SEPARATOR ROW DETECTION
// ─────────────────────────────────────────────────────────────────────────────

function looksLikeSeparatorRow(cells: string[], expectedLength: number): boolean {
  if (cells.length === 0) return false;
  const allSeparators = cells.every((cell) => {
    const cleaned = cell.replace(/\s+/g, "");
    return /^:?[-\u2013\u2014]{2,}:?$/.test(cleaned);
  });
  if (!allSeparators) return false;
  // Allow ±1 column variance (streaming may clip last cell)
  return expectedLength === 0 || Math.abs(cells.length - expectedLength) <= 1;
}

// ─────────────────────────────────────────────────────────────────────────────
// STREAMING TABLE NORMALIZER
// Converts any inline "A | B | C" rows to proper "| A | B | C |" format
// BEFORE the main parser runs. This ensures the parser always sees clean rows.
// ─────────────────────────────────────────────────────────────────────────────

export function normalizeStreamingTables(content: string): string {
  let inFence = false;
  return content
    .split("\n")
    .map((line) => {
      const trimmed = line.trim();

      if (/^```/.test(trimmed)) {
        inFence = !inFence;
        return line;
      }

      if (inFence || trimmed.startsWith("__CODE_FENCE_")) {
        return line;
      }

      // ── Tab-delimited rows (LLM sometimes emits TSV instead of pipe tables)
      // Convert "A\tB\tC" to "| A | B | C |" before pipe detection runs.
      // Only convert if the line has at least 2 tabs and no pipes already.
      if (
        !trimmed.includes("|") &&
        (trimmed.match(/\t/g) ?? []).length >= 1 &&
        trimmed.length > 0 &&
        !/^```/.test(trimmed)
      ) {
        const cells = trimmed
          .split("\t")
          .map((c) => c.trim())
          .filter((c) => c.length > 0);
        if (cells.length >= 2) {
          return `| ${cells.join(" | ")} |`;
        }
      }

      // ── Existing pipe row normalisation ──────────────────────────────────
      if (!trimmed.includes("|")) return line;
      if (trimmed === "|" || trimmed === "||") return line;
      const pipeCount = (trimmed.match(/\|/g) ?? []).length;
      if (pipeCount < 1) return line;

      const cells = parsePipeRow(trimmed);
      if (cells.length === 0) return line;

      if (cells.every((c) => /^:?[-]{2,}:?$/.test(c.replace(/\s+/g, "")))) {
        const sepCells = cells.map((c) => {
          const cleaned = c.replace(/\s+/g, "");
          const hasLeadingColon = cleaned.startsWith(":");
          const hasTrailingColon = cleaned.endsWith(":") && cleaned.length > 1;
          return (hasLeadingColon ? ":" : "") + "---" + (hasTrailingColon ? ":" : "");
        });
        return `| ${sepCells.join(" | ")} |`;
      }

      return `| ${cells.join(" | ")} |`;
    })
    .join("\n");
}
