export function normalizeMarkdown(content: string): string {
  if (!content) return "";
  const unwrapped = content.replace(/^```(?:markdown|md)\s*\n([\s\S]*?)\n?```$/i, "$1");
  return unwrapped
    .replace(/\r\n?/g, "\n")
    .split(/(```[\s\S]*?```)/g)
    .map((segment, index) => (index % 2 === 1 ? segment : normalizeMarkdownText(segment)))
    .join("")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/**
 * Providers sometimes prefix visible reasoning with a conversational wrapper
 * such as "Here's a thinking process:". A truncated stream can leave only
 * "'s a thinking process:". It is presentation noise, not part of the
 * reasoning, so remove only that exact leading wrapper from the activity view.
 */
export function normalizeThinkingDisplay(content: string): string {
  return content.replace(
    /^\s*(?:(?:here(?:['’]s|\s+is)?|this\s+is|that\s+is)|['’]s)\s+(?:a\s+)?thinking\s+process\s*:\s*/i,
    "",
  );
}

function normalizeMarkdownText(content: string): string {
  const rawLines = content
    .replace(/<br\s*\/?\s*>/gi, "\n")
    .replace(/([^#\n])(#{1,6}\s)/g, "$1\n\n$2")
    // Recover providers that escape the opening pipe or put the index header
    // before it (`# | Title | ...`), both of which block GFM table detection.
    .replace(/(^|\n)\s*\\\|/g, "$1|")
    .split("\n")
    // A few providers emit a leading `**` (or `__`) without its closing
    // marker. CommonMark must display that token literally. Repair only an
    // odd, unescaped marker count per text line; fenced code is split out by
    // normalizeMarkdown before this function runs and remains untouched.
    .map((line) => line.replace(/^(\s*)#\s*\|/, "$1| # |"))
    .map(repairDanglingStrongMarker);
  // Expand compact pipe boundaries before looking for a header/separator
  // pair. Keep a fully recoverable compact table intact so its existing
  // column-aware recovery remains authoritative.
  const lines = rawLines.flatMap((line) => {
    if (line.trim() === "|") return [];
    const repairedCitations = repairCompactCitationLine(line);
    if (repairedCitations.length > 1) return repairedCitations;
    const repairedListLine = repairCompactOrderedListLine(line);
    if (repairedListLine.length > 1) return repairedListLine;
    if (!line.trim().startsWith("|") || recoverCompactTable(line)) return [line];
    return normalizeCompactPipeLine(line).split("\n");
  });
  const normalizedLines: string[] = [];

  for (let index = 0; index < lines.length; ) {
    const line = lines[index]!;
    const recoveredTable = recoverCompactTable(line);
    if (recoveredTable) {
      if (normalizedLines.length && normalizedLines[normalizedLines.length - 1]?.trim()) {
        normalizedLines.push("");
      }
      normalizedLines.push(...recoveredTable.split("\n"));
      index += 1;
      continue;
    }

    const headerCells = pipeCells(line);
    if (line.trim().startsWith("|") && headerCells.length >= 2) {
      let separatorIndex = index + 1;
      while (separatorIndex < lines.length && !lines[separatorIndex]!.trim()) {
        separatorIndex += 1;
      }
      const separatorCells = separatorIndex < lines.length ? pipeCells(lines[separatorIndex]!) : [];
      if (isTableSeparator(separatorCells)) {
        // Providers sometimes insert a blank line between a table header and
        // its separator. Treat this pair as one table only when the next line
        // is unambiguously a Markdown separator, so normal pipe prose stays
        // untouched.
        if (normalizedLines.length && normalizedLines[normalizedLines.length - 1]?.trim()) {
          normalizedLines.push("");
        }
        normalizedLines.push(formatTableRow(headerCells));
        normalizedLines.push(formatTableSeparator(headerCells.length));
        index = separatorIndex + 1;

        while (index < lines.length) {
          const rowLine = lines[index]!;
          if (!rowLine.trim()) {
            let next = index + 1;
            while (next < lines.length && !lines[next]!.trim()) next += 1;
            if (next < lines.length && lines[next]!.trim().startsWith("|")) {
              index = next;
              continue;
            }
            break;
          }
          if (!rowLine.trim().startsWith("|")) break;
          const rowCells = pipeCells(rowLine);
          if (rowCells.length === 0) break;
          if (rowCells.length % headerCells.length !== 0) {
            const normalized = normalizeCompactPipeLine(rowLine);
            normalizedLines.push(...normalized.split("\n"));
          } else {
            for (let offset = 0; offset < rowCells.length; offset += headerCells.length) {
              normalizedLines.push(
                formatTableRow(rowCells.slice(offset, offset + headerCells.length)),
              );
            }
          }
          index += 1;
        }
        continue;
      }
    }

    if (!line.trim().startsWith("|")) {
      normalizedLines.push(line);
    } else {
      normalizedLines.push(...normalizeCompactPipeLine(line).split("\n"));
    }
    index += 1;
  }

  // Run once more after compact tables/lists have been split into physical
  // lines. Providers can stream an entire table or list as one paragraph;
  // repairing only before that split would see an even total and miss the
  // individual dangling markers shown in the rendered rows.
  return repairOrderedListNumbers(normalizedLines).map(repairDanglingStrongMarker).join("\n");
}

function repairDanglingStrongMarker(line: string): string {
  // Table cells (and provider-generated inline separators) are independent
  // Markdown text runs. A row can therefore contain two dangling opening
  // markers while the row-level count is even; repair each pipe-delimited
  // cell separately.
  if (line.includes("|")) {
    return repairPipeDelimitedLine(line);
  }

  return repairStrongMarkersOutsideCode(line);
}

function repairStrongMarkersOutsideCode(line: string): string {
  // Leave inline code spans byte-for-byte intact; asterisks in a code sample
  // are content, not Markdown emphasis. Complete fenced blocks are already
  // excluded by normalizeMarkdown.
  const segments = line.split(/(`+[^`]*`+)/g);
  return segments
    .map((segment, index) => (index % 2 === 1 ? segment : repairStrongMarkerText(segment)))
    .join("");
}

function repairPipeDelimitedLine(line: string): string {
  const parts: string[] = [];
  let segmentStart = 0;
  let codeTicks = 0;

  for (let index = 0; index < line.length; ) {
    if (line[index] === "`") {
      let end = index + 1;
      while (end < line.length && line[end] === "`") end += 1;
      const runLength = end - index;
      if (codeTicks === 0) codeTicks = runLength;
      else if (runLength === codeTicks) codeTicks = 0;
      index = end;
      continue;
    }
    if (line[index] === "|" && codeTicks === 0) {
      // This must not call repairDanglingStrongMarker again: model-generated
      // wide tables can contain thousands of pipes, and recursive per-cell
      // repair caused a browser stack overflow.
      parts.push(repairStrongMarkersOutsideCode(line.slice(segmentStart, index)));
      segmentStart = index + 1;
    }
    index += 1;
  }

  parts.push(repairStrongMarkersOutsideCode(line.slice(segmentStart)));
  return parts.join("|");
}

function repairStrongMarkerText(text: string): string {
  const markers = [...text.matchAll(/(?<!\\)(?:\*\*|__)/g)];
  if (markers.length === 0) return text;

  const unmatched: number[] = [];
  const openMarkers: Array<{ index: number; value: string }> = [];
  for (const marker of markers) {
    const index = marker.index ?? -1;
    if (index < 0) continue;
    const value = marker[0];
    const before = text[index - 1] ?? "";
    const after = text[index + value.length] ?? "";
    const canOpen =
      (!before || /\s/.test(before) || "([{\"'“‘—–-|".includes(before)) &&
      Boolean(after) &&
      !/\s/.test(after);
    const canClose =
      Boolean(before) &&
      !/\s/.test(before) &&
      (!after || /\s/.test(after) || ".,!?;:)]}\"'”’—–-|".includes(after));

    if (canClose && openMarkers.length) {
      const opening = openMarkers.pop()!;
      if (opening.value !== value) {
        unmatched.push(opening.index, index);
      }
      continue;
    }
    if (canOpen) openMarkers.push({ index, value });
    else unmatched.push(index);
  }
  unmatched.push(...openMarkers.map(({ index }) => index));

  return unmatched
    .sort((left, right) => right - left)
    .reduce((result, index) => `${result.slice(0, index)}${result.slice(index + 2)}`, text);
}

function repairCompactCitationLine(line: string): string[] {
  const markers = line.match(/\[\d+\](?=\s)/g) ?? [];
  if (markers.length < 2 || !/^\s*\[1\]\s+/.test(line)) return [line];
  return line
    .replace(/\s+(?=\[\d+\]\s)/g, "\n")
    .split("\n")
    .map((entry) => (entry.trim() ? `- ${entry.trim()}` : entry));
}

function repairCompactOrderedListLine(line: string): string[] {
  // Providers occasionally stream `1. First ... site2. Second ...` as one
  // paragraph. Split only an ordered-list marker followed by a title-like
  // token; ordinary prose such as `version 2.0` remains untouched.
  if (!/^\s*\d{1,3}\.\s+/.test(line)) return [line];
  const repaired = line.replace(/(?<=\S)(?=\d{1,3}\.\s+(?:\*\*|__|\[|[A-Z]))/g, "\n");
  return repaired.split("\n").flatMap(splitOrderedListSections);
}

function splitOrderedListSections(line: string): string[] {
  const match = line.match(/^(\s*)(\d{1,3})\.\s+(.*)$/);
  if (!match || !match[3]?.includes("|")) return [line];

  const sections = match[3]
    .split(/\s*\|\s*/)
    .map((section) => section.trim())
    .filter(Boolean);
  if (sections.length < 2) return [line];

  return sections.map((section, index) => {
    const normalizedSection = section.replace(/^•\s*/, "- ");
    return index === 0 ? `${match[1]}${match[2]}. ${normalizedSection}` : `   ${normalizedSection}`;
  });
}

function repairOrderedListNumbers(lines: string[]): string[] {
  const counters = new Map<string, number>();
  let listActive = false;
  return lines.map((line) => {
    const match = line.match(/^(\s*)\d{1,3}\.\s+(.*)$/);
    if (match) {
      const indent = match[1] ?? "";
      const next = (counters.get(indent) ?? 0) + 1;
      counters.set(indent, next);
      for (const key of counters.keys()) {
        if (key.length > indent.length) counters.delete(key);
      }
      listActive = true;
      return `${indent}${next}. ${match[2]}`;
    }

    // Providers often put detail bullets at column zero below a numbered
    // section. CommonMark treats that as a new sibling list, closes the
    // ordered list, and visually restarts the next section at 1. Nest those
    // bullets beneath the active numbered item so one semantic ordered list
    // remains open and the browser renders 1, 2, 3… correctly.
    if (listActive && /^\s*[-*+•]\s+/.test(line)) {
      return `   - ${line.replace(/^\s*[-*+•]\s+/, "")}`;
    }
    // Blank and already-indented continuation lines also belong to the
    // preceding ordered item. A normal paragraph or heading ends the list.
    if (listActive && (line.trim() === "" || /^\s{2,}\S/.test(line))) return line;
    counters.clear();
    listActive = false;
    return line;
  });
}

function isTableSeparator(cells: string[]): boolean {
  return cells.length >= 2 && cells.every((cell) => /^:?-{2,}:?$/.test(cell));
}

function formatTableRow(cells: string[]): string {
  return `| ${cells.join(" | ")} |`;
}

function formatTableSeparator(columnCount: number): string {
  return formatTableRow(Array.from({ length: columnCount }, () => "---"));
}

function normalizeCompactPipeLine(line: string): string {
  return (
    line
      .replace(/\|\|/g, "|\n|")
      // Some providers join consecutive table rows as `| | Row`. Split
      // that boundary only for pipe-prefixed table lines; prose containing
      // pipes is left untouched.
      .replace(/\|\s+\|(?=\s*(?:\*\*|[^\s|]))/g, "|\n|")
      .replace(/\|\s+\|(?=\s*:?-{2,})/g, "|\n|")
  );
}

function recoverCompactTable(line: string): string | null {
  if (!line.trim().startsWith("|")) return null;

  const cells = pipeCells(line);
  const separatorIndex = cells.findIndex((cell) => /^:?-{2,}:?$/.test(cell));
  if (separatorIndex < 2) return null;

  const header = cells.slice(0, separatorIndex);
  let remainderIndex = separatorIndex;
  while (remainderIndex < cells.length && /^:?-{2,}:?$/.test(cells[remainderIndex])) {
    remainderIndex += 1;
  }
  // A common streamed form emits fewer separator cells than headers, e.g.
  // `| A | B | C | |---|---|`. It is still unambiguously a separator-only
  // line when no cells follow it, so pad the separator safely.
  if (remainderIndex === cells.length && remainderIndex - separatorIndex < header.length) {
    remainderIndex = cells.length;
  }
  const remainder = cells.slice(remainderIndex);
  let rowWidth = header.length;
  let indexedRows = false;
  if (remainder.length > 0 && remainder.length % rowWidth !== 0) {
    const indexedRowWidth = header.length + 1;
    indexedRows =
      remainder.length % indexedRowWidth === 0 &&
      Array.from({ length: remainder.length / indexedRowWidth }, (_, rowIndex) =>
        /^\d+$/.test(remainder[rowIndex * indexedRowWidth] ?? ""),
      ).every(Boolean);
    if (indexedRows) rowWidth = indexedRowWidth;
    else return null;
  }

  const outputHeader = indexedRows ? ["#", ...header] : header;
  const rows = [
    `| ${outputHeader.join(" | ")} |`,
    `| ${outputHeader.map(() => "---").join(" | ")} |`,
  ];
  for (let index = 0; index < remainder.length; index += rowWidth) {
    const row = remainder.slice(index, index + rowWidth);
    rows.push(`| ${row.join(" | ")} |`);
  }
  return rows.join("\n");
}

function pipeCells(value: string): string[] {
  return value
    .split("|")
    .map((cell) => cell.trim())
    .filter(Boolean);
}
