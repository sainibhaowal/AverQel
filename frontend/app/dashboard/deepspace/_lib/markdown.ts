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
  return content
    .replace(/<br\s*\/?\s*>/gi, "\n")
    .replace(/([^#\n])(#{1,6}\s)/g, "$1\n\n$2")
    .split("\n")
    .flatMap((line) => {
      const recoveredTable = recoverCompactTable(line);
      if (recoveredTable) return recoveredTable.split("\n");

      const trimmed = line.trim();
      if (!trimmed.startsWith("|")) return [line];
      return [line.replace(/\|\|/g, "|\n|").replace(/\|\s+\|(?=\s*:?-{2,})/g, "|\n|")];
    })
    .join("\n");
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
