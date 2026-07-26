/**
 * Small, shared cleanup for answer Markdown before it reaches the renderer.
 *
 * The renderer itself is intentionally delegated to react-markdown. These
 * normalizations only repair common model formatting mistakes that would make
 * otherwise valid Markdown unreadable while an answer is streaming.
 */
export function normalizeMarkdown(content: string): string {
  if (!content) return "";

  const unwrapped = unwrapMarkdownFence(content).replace(/\r\n?/g, "\n");
  const next = unwrapped
    .split(/(```[\s\S]*?```)/g)
    .map((segment, index) => (index % 2 === 1 ? segment : normalizeMarkdownText(segment)))
    .join("");

  const lines = next.split("\n");
  const compacted: string[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index] ?? "";
    const previous = compacted[compacted.length - 1] ?? "";
    const following = lines[index + 1] ?? "";
    if (
      line.trim() === "" &&
      previous.includes("|") &&
      following.includes("|") &&
      (isTableSeparator(previous) || isTableSeparator(following))
    ) {
      continue;
    }
    compacted.push(line);
  }

  return compacted
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function normalizeMarkdownText(content: string): string {
  return content
    // Providers frequently emit HTML line breaks in otherwise plain Markdown.
    .replace(/<br\s*\/?\s*>/gi, "\n")
    .replace(/([^#\n])(#{1,6}\s)/g, "$1\n\n$2")
    .split("\n")
    .flatMap((line) => {
      const recoveredTable = recoverCompactTable(line);
      if (recoveredTable) return recoveredTable.split("\n");

      const trimmed = line.trim();
      if (!trimmed.startsWith("|")) return [line];

      // Repair compact tables such as `| A | B | | --- | --- |`.
      return [
        line
          .replace(/\|\|/g, "|\n|")
          .replace(/\|\s+\|(?=\s*:?-{2,})/g, "|\n|"),
      ];
    })
    .join("\n");
}

/**
 * Recover a table whose rows were concatenated into one provider paragraph.
 * This only runs when a real Markdown separator row is present, so ordinary
 * prose containing pipes is left untouched.
 */
function recoverCompactTable(line: string): string | null {
  if (!line.trim().startsWith("|")) return null;

  const separator = line.match(/(?:^|\|)\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?/);
  if (!separator || separator.index === undefined) return null;

  const header = pipeCells(line.slice(0, separator.index));
  if (header.length < 2) return null;

  const remainder = pipeCells(line.slice(separator.index + separator[0].length));
  if (remainder.length > 0 && remainder.length % header.length !== 0) return null;

  const rows = [
    `| ${header.join(" | ")} |`,
    `| ${header.map(() => "---").join(" | ")} |`,
  ];
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

function unwrapMarkdownFence(content: string): string {
  const trimmed = content.trim();
  const match = trimmed.match(/^```(?:markdown|md)\s*\n([\s\S]*?)\n?```$/i);
  return match ? match[1]!.trim() : content;
}

function isTableSeparator(line: string): boolean {
  return /^\|?(?:\s*:?-{2,}:?\s*\|)+\s*:?-{2,}:?\s*\|?$/.test(line.trim());
}
