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
    .split("\n");
  // Expand compact pipe boundaries before looking for a header/separator
  // pair. Keep a fully recoverable compact table intact so its existing
  // column-aware recovery remains authoritative.
  const lines = rawLines.flatMap((line) => {
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

  return repairOrderedListNumbers(normalizedLines).join("\n");
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
  return repaired.split("\n");
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

    // Detail bullets and blank lines belong to the preceding ordered list.
    // A normal paragraph or heading ends it and resets numbering.
    if (listActive && (line.trim() === "" || /^\s*[-*+]\s+/.test(line))) return line;
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
