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

function normalizeMarkdownText(content: string): string {
  const rawLines = content
    .replace(/<br\s*\/?\s*>/gi, "\n")
    .replace(/([^#\n])(#{1,6}\s)/g, "$1\n\n$2")
    .split("\n");
  // Expand compact pipe boundaries before looking for a header/separator
  // pair. Keep a fully recoverable compact table intact so its existing
  // column-aware recovery remains authoritative.
  const lines = rawLines.flatMap((line) => {
    if (!line.trim().startsWith("|") || recoverCompactTable(line)) return [line];
    return normalizeCompactPipeLine(line).split("\n");
  });
  const normalizedLines: string[] = [];

  for (let index = 0; index < lines.length; ) {
    const line = lines[index]!;
    const recoveredTable = recoverCompactTable(line);
    if (recoveredTable) {
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

  return normalizedLines.join("\n");
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
  if (remainder.length > 0 && remainder.length % header.length !== 0) return null;

  const rows = [`| ${header.join(" | ")} |`, `| ${header.map(() => "---").join(" | ")} |`];
  for (let index = 0; index < remainder.length; index += header.length) {
    rows.push(`| ${remainder.slice(index, index + header.length).join(" | ")} |`);
  }
  return rows.join("\n");
}

function pipeCells(value: string): string[] {
  return value
    .split("|")
    .map((cell) => cell.trim())
    .filter(Boolean);
}
