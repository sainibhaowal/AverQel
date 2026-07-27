/**
 * Mermaid 11 can return an error SVG from render() instead of throwing. Do
 * not mount that SVG because it displays Mermaid's red parser-error graphic.
 */
export function isMermaidErrorSvg(svg: string): boolean {
  if (!svg.trim()) return true;

  const text = svg
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&(?:amp|lt|gt|quot|apos);/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .toLowerCase();

  return (
    text.includes("syntax error in text") ||
    text.includes("mermaid version") ||
    text.includes("error found")
  );
}
