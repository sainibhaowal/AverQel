"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Copy,
  Check,
  Eye,
  AlertTriangle,
  Move,
  ZoomIn,
  ZoomOut,
  LocateFixed,
  Download,
  GitBranch,
} from "lucide-react";

interface CodeBlockProps {
  language?: string;
  value: string;
  incomplete?: boolean;
  enableRichPreview?: boolean;
  answerStreaming?: boolean;
  defaultPreviewOpen?: boolean;
  title?: string | null;
  description?: string | null;
}

type CodeFileDescriptor = {
  extension: string;
  mimeType: string;
  baseName: string;
};

type CodeTokenType =
  | "plain"
  | "comment"
  | "string"
  | "number"
  | "keyword"
  | "function"
  | "property"
  | "operator"
  | "punctuation"
  | "bracket";

type CodeToken = {
  value: string;
  type: CodeTokenType;
  bracketDepth?: number;
};

type CodeBlockVariant = "plain" | "mermaid" | "preview";

const COLLAPSED_BODY_MIN_HEIGHT = 260;
const COLLAPSED_BODY_MAX_HEIGHT = 560;
const COLLAPSED_MERMAID_MAX_HEIGHT = 640;

const BRACKET_PALETTE = [
  "hsl(243, 75%, 70%)",
  "hsl(270, 95%, 70%)",
  "hsl(210, 100%, 70%)",
  "hsl(180, 100%, 70%)",
  "hsl(330, 100%, 70%)",
  "hsl(20, 100%, 70%)",
] as const;

const DEFAULT_TOKEN_STYLES: Record<CodeTokenType, string> = {
  plain: "#e2e8f0",
  comment: "#64748b",
  string: "hsl(142, 70%, 70%)",
  number: "hsl(330, 90%, 70%)",
  keyword: "hsl(243, 90%, 75%)",
  function: "hsl(45, 90%, 70%)",
  property: "hsl(270, 90%, 75%)",
  operator: "hsl(0, 90%, 75%)",
  punctuation: "#94a3b8",
  bracket: "#e2e8f0",
};

const JS_TS_KEYWORDS = new Set([
  "as",
  "async",
  "await",
  "break",
  "case",
  "catch",
  "class",
  "const",
  "continue",
  "default",
  "delete",
  "do",
  "else",
  "enum",
  "export",
  "extends",
  "false",
  "finally",
  "for",
  "from",
  "function",
  "if",
  "implements",
  "import",
  "in",
  "instanceof",
  "interface",
  "let",
  "new",
  "null",
  "of",
  "private",
  "protected",
  "public",
  "return",
  "static",
  "super",
  "switch",
  "this",
  "throw",
  "true",
  "try",
  "type",
  "typeof",
  "undefined",
  "var",
  "void",
  "while",
  "with",
  "yield",
]);

const PYTHON_KEYWORDS = new Set([
  "and",
  "as",
  "assert",
  "async",
  "await",
  "break",
  "class",
  "continue",
  "def",
  "del",
  "elif",
  "else",
  "except",
  "False",
  "finally",
  "for",
  "from",
  "global",
  "if",
  "import",
  "in",
  "is",
  "lambda",
  "None",
  "nonlocal",
  "not",
  "or",
  "pass",
  "raise",
  "return",
  "True",
  "try",
  "while",
  "with",
  "yield",
]);

const SQL_KEYWORDS = new Set([
  "add",
  "alter",
  "and",
  "as",
  "asc",
  "by",
  "case",
  "create",
  "delete",
  "desc",
  "distinct",
  "drop",
  "else",
  "end",
  "from",
  "group",
  "having",
  "in",
  "inner",
  "insert",
  "into",
  "join",
  "left",
  "limit",
  "not",
  "null",
  "on",
  "or",
  "order",
  "outer",
  "right",
  "select",
  "set",
  "table",
  "then",
  "union",
  "update",
  "values",
  "when",
  "where",
]);

const BASH_KEYWORDS = new Set([
  "case",
  "do",
  "done",
  "elif",
  "else",
  "esac",
  "export",
  "fi",
  "for",
  "function",
  "if",
  "in",
  "local",
  "readonly",
  "return",
  "select",
  "then",
  "time",
  "until",
  "while",
]);

const CSS_KEYWORDS = new Set([
  "@media",
  "@keyframes",
  "@supports",
  "@layer",
  "@import",
  "@font-face",
  "from",
  "to",
]);

const JSON_KEYWORDS = new Set(["true", "false", "null"]);

function getKeywordSet(language: string): Set<string> {
  switch (language) {
    case "javascript":
    case "js":
    case "typescript":
    case "ts":
    case "jsx":
    case "tsx":
      return JS_TS_KEYWORDS;
    case "python":
    case "py":
      return PYTHON_KEYWORDS;
    case "sql":
      return SQL_KEYWORDS;
    case "bash":
    case "sh":
      return BASH_KEYWORDS;
    case "css":
      return CSS_KEYWORDS;
    case "json":
      return JSON_KEYWORDS;
    default:
      return new Set();
  }
}

function isIdentifierStart(char: string): boolean {
  return /[A-Za-z_$@]/.test(char);
}

function isIdentifierPart(char: string): boolean {
  return /[A-Za-z0-9_$.-]/.test(char);
}

function isNumberStart(value: string, index: number): boolean {
  const char = value[index] ?? "";
  if (!/[0-9]/.test(char)) {
    return false;
  }
  const prev = value[index - 1] ?? "";
  return !/[A-Za-z0-9_$]/.test(prev);
}

function isFunctionNameToken(
  source: string,
  start: number,
  end: number,
  language: string,
  previousSignificantToken: CodeToken | null,
): boolean {
  const identifier = source.slice(start, end);
  const after = source.slice(end);
  const before = source.slice(0, start);
  const nextNonSpace = after.match(/^\s*([(<])/);
  const previousWord = before.match(/([A-Za-z_][\w$-]*)\s*$/)?.[1] ?? "";
  const languageIsPython = language === "python" || language === "py";

  if (previousWord === "function" || previousWord === "def" || previousWord === "class") {
    return true;
  }
  if (previousSignificantToken?.type === "property") {
    return false;
  }
  if (nextNonSpace?.[1] === "(") {
    return true;
  }
  if (languageIsPython && nextNonSpace?.[1] === "(") {
    return true;
  }
  return identifier[0] === identifier[0]?.toUpperCase() && nextNonSpace?.[1] === "(";
}

function tokenizeCode(value: string, language: string): CodeToken[] {
  const tokens: CodeToken[] = [];
  const keywords = getKeywordSet(language);
  let index = 0;
  let bracketDepth = 0;
  let previousSignificantToken: CodeToken | null = null;

  const pushToken = (token: CodeToken) => {
    tokens.push(token);
    if (token.type !== "plain" || token.value.trim()) {
      previousSignificantToken = token.value.trim() ? token : previousSignificantToken;
    }
  };

  while (index < value.length) {
    const char = value[index] ?? "";
    const next = value[index + 1] ?? "";

    if (char === "\n") {
      tokens.push({ value: "\n", type: "plain" });
      index += 1;
      continue;
    }

    if (/\s/.test(char)) {
      let end = index + 1;
      while (end < value.length && /\s/.test(value[end] ?? "") && value[end] !== "\n") {
        end += 1;
      }
      tokens.push({ value: value.slice(index, end), type: "plain" });
      index = end;
      continue;
    }

    if (
      (char === "/" && next === "/") ||
      (char === "#" && !(language === "css" && value.slice(index).startsWith("#")))
    ) {
      let end = index + 1;
      while (end < value.length && value[end] !== "\n") {
        end += 1;
      }
      pushToken({ value: value.slice(index, end), type: "comment" });
      index = end;
      continue;
    }

    if (char === "/" && next === "*") {
      let end = index + 2;
      while (end < value.length && !(value[end] === "*" && value[end + 1] === "/")) {
        end += 1;
      }
      end = Math.min(value.length, end + 2);
      pushToken({ value: value.slice(index, end), type: "comment" });
      index = end;
      continue;
    }

    if (char === "'" || char === '"' || char === "`") {
      const quote = char;
      let end = index + 1;
      let escaped = false;
      while (end < value.length) {
        const current = value[end] ?? "";
        if (escaped) {
          escaped = false;
          end += 1;
          continue;
        }
        if (current === "\\") {
          escaped = true;
          end += 1;
          continue;
        }
        if (current === quote) {
          end += 1;
          break;
        }
        end += 1;
      }
      pushToken({ value: value.slice(index, end), type: "string" });
      index = end;
      continue;
    }

    if (isNumberStart(value, index)) {
      let end = index + 1;
      while (end < value.length && /[0-9._xXa-fA-F]/.test(value[end] ?? "")) {
        end += 1;
      }
      pushToken({ value: value.slice(index, end), type: "number" });
      index = end;
      continue;
    }

    if ("([{".includes(char)) {
      pushToken({
        value: char,
        type: "bracket",
        bracketDepth: bracketDepth++,
      });
      index += 1;
      continue;
    }

    if (")]}".includes(char)) {
      bracketDepth = Math.max(0, bracketDepth - 1);
      pushToken({
        value: char,
        type: "bracket",
        bracketDepth,
      });
      index += 1;
      continue;
    }

    if (isIdentifierStart(char)) {
      let end = index + 1;
      while (end < value.length && isIdentifierPart(value[end] ?? "")) {
        end += 1;
      }
      const identifier = value.slice(index, end);
      const normalizedIdentifier = language === "sql" ? identifier.toLowerCase() : identifier;
      const before = value[index - 1] ?? "";
      const after = value[end] ?? "";
      let type: CodeTokenType = "plain";

      if (keywords.has(normalizedIdentifier)) {
        type = "keyword";
      } else if (before === ".") {
        type = "property";
      } else if (after === ":") {
        type =
          language === "json" || language === "yaml" || language === "yml" ? "property" : "plain";
      } else if (isFunctionNameToken(value, index, end, language, previousSignificantToken)) {
        type = "function";
      }

      pushToken({ value: identifier, type });
      index = end;
      continue;
    }

    if (/[=+\-*/%<>!&|^~?:;,.[\]]/.test(char)) {
      let end = index + 1;
      while (end < value.length && /[=+\-*/%<>!&|^~?:]/.test(value[end] ?? "")) {
        end += 1;
      }
      pushToken({
        value: value.slice(index, end),
        type: /[;,:.]/.test(char) ? "punctuation" : "operator",
      });
      index = end;
      continue;
    }

    pushToken({ value: char, type: "plain" });
    index += 1;
  }

  return tokens;
}

function getTokenColor(token: CodeToken): string {
  if (token.type === "bracket") {
    return (
      BRACKET_PALETTE[(token.bracketDepth ?? 0) % BRACKET_PALETTE.length] ??
      DEFAULT_TOKEN_STYLES.bracket
    );
  }
  return DEFAULT_TOKEN_STYLES[token.type] ?? DEFAULT_TOKEN_STYLES.plain;
}

function renderHighlightedCode(value: string, language: string) {
  const tokens = tokenizeCode(value, language);
  const lines: CodeToken[][] = [[]];

  for (const token of tokens) {
    if (token.value === "\n") {
      lines.push([]);
      continue;
    }
    lines[lines.length - 1]?.push(token);
  }

  return lines.map((line, lineIndex) => (
    <div key={`code-line-${lineIndex}`} className="min-h-[1.75rem]">
      {line.length === 0 ? <span>&nbsp;</span> : null}
      {line.map((token, tokenIndex) => (
        <span
          key={`code-token-${lineIndex}-${tokenIndex}`}
          style={{ color: getTokenColor(token) }}
          className={
            token.type === "function"
              ? "font-semibold"
              : token.type === "comment"
                ? "italic"
                : undefined
          }
        >
          {token.value}
        </span>
      ))}
    </div>
  ));
}

function getCodeBlockVariant(language: string, supportsRichPreview: boolean): CodeBlockVariant {
  if (language === "mermaid") {
    return "mermaid";
  }
  if (supportsRichPreview) {
    return "preview";
  }
  return "plain";
}

function getShellClasses(variant: CodeBlockVariant) {
  switch (variant) {
    case "mermaid":
      return {
        shell:
          "my-6 overflow-hidden rounded-[1.35rem] border border-primary/20 bg-[linear-gradient(180deg,rgba(var(--primary),0.12),rgba(15,23,42,0.96))] shadow-[0_20px_60px_-34px_rgba(var(--primary),0.32)]",
        header:
          "flex flex-wrap items-center justify-between gap-3 border-b border-primary/15 bg-slate-950/55 px-4 py-3",
        label: "text-primary text-[10px] font-semibold tracking-[0.24em] uppercase",
        button:
          "border-primary/20 bg-primary/10 text-primary-foreground/90 hover:bg-primary/20 hover:border-primary/30 inline-flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-[11px] font-medium transition disabled:cursor-not-allowed disabled:opacity-40",
        codeSurface:
          "overflow-auto bg-[linear-gradient(180deg,rgba(2,6,23,0.12),rgba(2,6,23,0.28))] px-4 py-4 text-sm leading-7",
      };
    case "preview":
      return {
        shell:
          "my-6 overflow-hidden rounded-[1.2rem] border border-slate-700/40 bg-slate-950/94 shadow-[0_18px_44px_-32px_rgba(15,23,42,0.72)]",
        header:
          "flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 bg-slate-900/84 px-4 py-3",
        label: "text-[10px] font-semibold tracking-[0.22em] text-slate-300 uppercase",
        button:
          "inline-flex items-center gap-1 rounded-md border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-[11px] font-medium text-slate-300 transition hover:bg-white/[0.06] hover:text-white disabled:cursor-not-allowed disabled:opacity-40",
        codeSurface: "overflow-auto bg-slate-950 px-4 py-4 text-sm leading-7",
      };
    case "plain":
    default:
      return {
        shell:
          "my-6 overflow-hidden rounded-[0.95rem] border border-slate-800/80 bg-slate-950 shadow-[0_12px_30px_-26px_rgba(15,23,42,0.82)]",
        header:
          "flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 bg-[#0b1220] px-4 py-3",
        label: "text-[10px] font-medium tracking-[0.18em] text-slate-400 uppercase",
        button:
          "inline-flex items-center gap-1 rounded-md border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-[11px] font-medium text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-40",
        codeSurface: "overflow-auto bg-slate-950 px-4 py-4 text-sm leading-7",
      };
  }
}

function getCollapsedBodyHeightLimit(language: string): number {
  if (language === "mermaid") {
    return COLLAPSED_MERMAID_MAX_HEIGHT;
  }
  return COLLAPSED_BODY_MAX_HEIGHT;
}

function getCodeFileDescriptor(language: string, mermaidFamily?: string): CodeFileDescriptor {
  switch (language) {
    case "svg":
      return { extension: "svg", mimeType: "image/svg+xml", baseName: "diagram" };
    case "html":
      return { extension: "html", mimeType: "text/html", baseName: "report" };
    case "xml":
      return { extension: "xml", mimeType: "application/xml", baseName: "document" };
    case "json":
      return { extension: "json", mimeType: "application/json", baseName: "data" };
    case "markdown":
    case "md":
      return { extension: "md", mimeType: "text/markdown", baseName: "notes" };
    case "python":
    case "py":
      return { extension: "py", mimeType: "text/x-python", baseName: "snippet" };
    case "javascript":
    case "js":
      return { extension: "js", mimeType: "text/javascript", baseName: "snippet" };
    case "typescript":
    case "ts":
      return { extension: "ts", mimeType: "text/typescript", baseName: "snippet" };
    case "jsx":
      return { extension: "jsx", mimeType: "text/javascript", baseName: "snippet" };
    case "tsx":
      return { extension: "tsx", mimeType: "text/typescript", baseName: "snippet" };
    case "css":
      return { extension: "css", mimeType: "text/css", baseName: "styles" };
    case "sql":
      return { extension: "sql", mimeType: "application/sql", baseName: "query" };
    case "yaml":
    case "yml":
      return { extension: "yaml", mimeType: "application/yaml", baseName: "config" };
    case "bash":
    case "sh":
      return { extension: "sh", mimeType: "text/x-shellscript", baseName: "script" };
    case "mermaid":
      return {
        extension: "mmd",
        mimeType: "text/plain",
        baseName: mermaidFamily === "classdiagram" ? "class-diagram" : "diagram",
      };
    case "vega":
      return { extension: "vega.json", mimeType: "application/json", baseName: "chart" };
    case "vega-lite":
      return { extension: "vl.json", mimeType: "application/json", baseName: "chart" };
    default:
      return { extension: language || "txt", mimeType: "text/plain", baseName: "snippet" };
  }
}

function createObjectUrl(content: string, mimeType: string): string {
  return URL.createObjectURL(new Blob([content], { type: `${mimeType};charset=utf-8` }));
}

// FIX: Stable random ID — generated once per mount, never on re-render.
// Mermaid caches renders by ID. The old code used Math.random() on every
// effect run which broke the cache and leaked orphaned SVG elements into the DOM.
function useStableId(prefix: string): string {
  return useMemo(
    () => `${prefix}-${Math.random().toString(36).slice(2, 10)}`,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
}

// FIX: Reactive dark mode — watches documentElement class changes via
// MutationObserver so theme switches after mount trigger a re-render.
// The old code read the class once at effect time and never updated.
function useMermaidTheme(): "dark" | "default" {
  const [theme, setTheme] = useState<"dark" | "default">(() => {
    if (typeof document === "undefined") return "default";
    return document.documentElement.classList.contains("dark") ? "dark" : "default";
  });

  useEffect(() => {
    if (typeof document === "undefined") return;

    const observer = new MutationObserver(() => {
      const isDark = document.documentElement.classList.contains("dark");
      setTheme(isDark ? "dark" : "default");
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => observer.disconnect();
  }, []);

  return theme;
}

function normalizeRenderedSvg(svg: string, mermaidFamily?: string): string {
  if (!svg.trim()) {
    return svg;
  }

  const classDiagramContrastStyle = `
<style>
svg {
  background: transparent !important;
}
.classBox,
.divider,
.classGroup line,
.classGroup path,
.relation line,
.relation path {
  stroke: #cbd5e1 !important;
}
.classTitle,
.classTitle text,
.classTitle tspan,
.classText,
.classText text,
.classText tspan,
.relation text,
.relation tspan,
.label text,
.label span,
.edgeLabel text {
  fill: #f8fafc !important;
  color: #f8fafc !important;
  opacity: 1 !important;
}
</style>`;

  const contrastStyle = `
<style>
svg {
  background: transparent !important;
}
.node rect,
.node polygon,
.node path,
.node circle,
.node ellipse,
.cluster rect,
.classBox,
.entityBox,
.attributeBoxOdd,
.attributeBoxEven,
.stateGroup rect,
.stateGroup path,
.task,
.section-root rect,
.loopLine,
.note,
.timeline-node,
.section-rect,
.mindmap-node rect,
.mindmap-node circle,
.mindmap-node path,
.mindmap-node polygon {
  stroke: #cbd5e1 !important;
  stroke-width: 1.6px !important;
}
.edgePath path,
.flowchart-link,
.relationshipLine,
.messageLine0,
.messageLine1,
.dependencyLine,
.transition,
.actor-line,
.loopLine,
.activation0,
.activation1,
.activation2,
.timeline-line,
.timeline-connector,
.mindmap-edge,
.mindmap-edge-connector,
path[marker-end],
path[marker-start] {
  stroke: #cbd5e1 !important;
  stroke-width: 1.7px !important;
}
.marker,
.marker path,
.arrowheadPath,
marker path {
  fill: #cbd5e1 !important;
  stroke: #cbd5e1 !important;
}
.label text,
.cluster-label text,
.nodeLabel,
.classLabel .label,
.entityLabel,
.messageText,
.noteText,
.actor,
.actor text,
.section-root text,
.state-title,
.state-title text,
.taskText,
.label span,
.label p,
.label foreignObject div,
.label foreignObject span,
.timeline-event-text,
.event-text,
.section-text,
.marker-text,
.mindmap-node text,
.mindmap-node tspan,
.mindmap-label,
.nodeLabel {
  fill: #f8fafc !important;
  color: #f8fafc !important;
  opacity: 1 !important;
}
.edgeLabel text,
.edgeLabel span,
.edgeLabel div {
  fill: #f8fafc !important;
  color: #f8fafc !important;
  background: transparent !important;
  opacity: 1 !important;
}
.label-container,
.edgeLabel,
.edgeLabel rect,
.edgeLabel foreignObject {
  background: transparent !important;
  fill: transparent !important;
}
.classTitle,
.classText,
.classText text,
.classText tspan,
.classTitle text,
.classTitle tspan,
.relation text,
.relation tspan,
.labelText,
.nodeLabel tspan,
.messageText tspan,
.edgeTerminals,
.edgeTerminals text,
.attributeBoxOdd text,
.attributeBoxEven text,
.entityBox text,
.section-root text,
.timeline-event-text tspan,
.mindmap-node text,
.mindmap-node tspan,
.mindmap-label,
.nodeLabel,
.zen-participant text,
.zen-message text,
.zen-note text,
.zen-fragment text {
  fill: #f8fafc !important;
  color: #f8fafc !important;
  opacity: 1 !important;
}
.divider,
.classGroup line,
.classGroup path,
.relation line,
.relation path {
  stroke: #cbd5e1 !important;
  stroke-width: 1.6px !important;
}
.node rect,
.node polygon,
.node circle,
.node ellipse,
.label-container {
  filter: none !important;
}
</style>`;

  const style = [
    "width:auto !important",
    "max-width:none !important",
    "min-width:0",
    "height:auto !important",
    "max-height:none !important",
    "display:block",
    "overflow:visible",
  ].join(";");

  const styleBlock = mermaidFamily === "classdiagram" ? classDiagramContrastStyle : contrastStyle;
  const withContrast = /<svg\b[^>]*>/i.test(svg)
    ? svg.replace(/<svg\b([^>]*)>/i, `<svg$1>${styleBlock}`)
    : svg;

  if (/<svg\b[^>]*style=/i.test(withContrast)) {
    return withContrast.replace(
      /<svg\b([^>]*?)style=(["'])(.*?)\2([^>]*)>/i,
      (_m, before, quote, existing, after) => {
        const merged = `${existing};${style}`;
        return `<svg${before}style=${quote}${merged}${quote}${after}>`;
      },
    );
  }

  return withContrast.replace(/<svg\b([^>]*)>/i, `<svg$1 style="${style}">`);
}

export function sanitizeMermaidSyntax(source: string): string {
  const normalized = source.trim();
  if (!normalized) {
    return source;
  }

  const simplifyTextualMermaidLabel = (value: string): string => {
    const normalizedValue = value.trim();
    if (!normalizedValue) {
      return value;
    }
    return normalizedValue
      .replaceAll("&", " and ")
      .replaceAll(":", " ")
      .replaceAll(";", " ")
      .replaceAll(",", " ")
      .replaceAll("(", " ")
      .replaceAll(")", " ")
      .replaceAll('"', "")
      .replaceAll("'", "")
      .replace(/[^\w\s/\-]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  };

  const sanitizeMindmapLine = (line: string): string => {
    const leading = line.match(/^\s*/)?.[0] ?? "";
    const content = line.slice(leading.length).trimEnd();
    if (!content || content.startsWith("%%") || content.startsWith("::")) {
      return line;
    }

    const wrapped = content.match(
      /^([A-Za-z_][\w-]*)(\(\(|\(\[|\[\[|\(|\[)(.*?)(\)\)|\]\)|\]\]|\)|\])$/,
    );
    if (wrapped) {
      const [, nodeId, openWrap, label, closeWrap] = wrapped;
      return `${leading}${nodeId}${openWrap}${simplifyTextualMermaidLabel(label)}${closeWrap}`;
    }

    return `${leading}${simplifyTextualMermaidLabel(content)}`;
  };

  const repairMindmapStructure = (lines: string[]): string[] => {
    const body = lines.slice(1);
    const contentLines = body.filter((line) => {
      const trimmed = line.trim();
      return Boolean(trimmed) && !trimmed.startsWith("%%");
    });

    if (contentLines.length === 0) {
      return lines;
    }

    const hasExplicitRoot = contentLines.some((line) => line.trim().startsWith("root"));
    if (hasExplicitRoot) {
      return lines;
    }

    const firstContent = contentLines[0]?.trim() ?? "Root";
    const normalizedRootLabel = simplifyTextualMermaidLabel(
      firstContent.replace(/^[-*]\s*/, "").replace(/^#+\s*/, ""),
    );

    const repaired = [lines[0] ?? "mindmap", `  root((${normalizedRootLabel || "Root"}))`];
    let rootAssigned = false;

    for (const originalLine of body) {
      const trimmed = originalLine.trim();
      if (!trimmed) {
        continue;
      }
      if (trimmed.startsWith("%%")) {
        repaired.push(originalLine);
        continue;
      }

      const sanitizedLine = sanitizeMindmapLine(originalLine).trim();
      if (!rootAssigned && sanitizedLine === simplifyTextualMermaidLabel(firstContent)) {
        rootAssigned = true;
        continue;
      }

      repaired.push(`    ${sanitizedLine}`);
    }

    return repaired;
  };

  const sanitizeJourneyLine = (line: string): string => {
    const inferJourneyActor = (label: string) => {
      const firstWord =
        label
          .trim()
          .split(/\s+/, 1)[0]
          ?.replace(/[^\w-]/g, "") ?? "";
      if (/^(user|admin|system|analyst|reviewer|customer|client)$/i.test(firstWord)) {
        return firstWord;
      }
      return "User";
    };

    const indent = line.match(/^\s*/)?.[0] ?? "";
    const stripped = line.trim();
    if (!stripped || stripped.startsWith("%%")) {
      return line;
    }
    if (stripped.toLowerCase().startsWith("title ")) {
      return `${indent}title ${simplifyTextualMermaidLabel(stripped.slice(6))}`;
    }
    if (stripped.toLowerCase().startsWith("section ")) {
      return `${indent}section ${simplifyTextualMermaidLabel(stripped.slice(8))}`;
    }
    const arrowMatch = stripped.match(/^(?:->|-->|[-*])\s*(.+)$/);
    if (arrowMatch) {
      const label = simplifyTextualMermaidLabel(arrowMatch[1] ?? "");
      return `${indent}${label}: 5: System`;
    }

    const parts = stripped
      .split(":")
      .map((part) => part.trim())
      .filter(Boolean);
    if (parts.length >= 2) {
      const label = simplifyTextualMermaidLabel(parts[0] ?? "");
      const score = parts[1] ?? "";
      const normalizedScore = score.match(/^\d+$/) ? score : "5";
      const actorSource =
        score.match(/^\d+$/) && parts.length > 2
          ? parts.slice(2).join(" ")
          : score.replace(/\$[^$]+\$/g, "").replace(/^[->-]+\s*/, "");
      const actor = simplifyTextualMermaidLabel(actorSource) || inferJourneyActor(label);
      return `${indent}${label}: ${normalizedScore}: ${actor}`;
    }

    const label = simplifyTextualMermaidLabel(stripped);
    return `${indent}${label}: 5: ${inferJourneyActor(label)}`;
  };

  const sanitizeTimelineLine = (line: string): string => {
    const indent = line.match(/^\s*/)?.[0] ?? "";
    const stripped = line.trim();
    if (!stripped || stripped.startsWith("%%")) {
      return line;
    }
    if (stripped.toLowerCase().startsWith("title ")) {
      return `${indent}title ${simplifyTextualMermaidLabel(stripped.slice(6))}`;
    }
    if (stripped.toLowerCase().startsWith("section ")) {
      return `${indent}section ${simplifyTextualMermaidLabel(stripped.slice(8))}`;
    }
    if (stripped.includes(":")) {
      const separatorIndex = stripped.indexOf(":");
      const left = separatorIndex >= 0 ? stripped.slice(0, separatorIndex) : stripped;
      const right = separatorIndex >= 0 ? stripped.slice(separatorIndex + 1) : "";
      return `${indent}${simplifyTextualMermaidLabel(left ?? "")} : ${simplifyTextualMermaidLabel(right ?? "")}`;
    }
    return `${indent}${simplifyTextualMermaidLabel(stripped)}`;
  };

  const sanitizeGanttLine = (line: string): string => {
    const indent = line.match(/^\s*/)?.[0] ?? "";
    const stripped = line.trim();
    const lowered = stripped.toLowerCase();
    if (!stripped || stripped.startsWith("%%")) {
      return line;
    }
    if (lowered.startsWith("title ")) {
      return `${indent}title ${simplifyTextualMermaidLabel(stripped.slice(6))}`;
    }
    if (lowered.startsWith("section ")) {
      return `${indent}section ${simplifyTextualMermaidLabel(stripped.slice(8))}`;
    }
    if (
      lowered.startsWith("dateformat ") ||
      lowered.startsWith("axisformat ") ||
      lowered.startsWith("tickinterval ") ||
      lowered.startsWith("excludes ") ||
      lowered.startsWith("todaymarker ")
    ) {
      return line;
    }
    if (stripped.includes(":")) {
      const separatorIndex = stripped.indexOf(":");
      const left = separatorIndex >= 0 ? stripped.slice(0, separatorIndex) : stripped;
      const right = separatorIndex >= 0 ? stripped.slice(separatorIndex + 1) : "";
      return `${indent}${simplifyTextualMermaidLabel(left ?? "")} :${right ?? ""}`;
    }
    return `${indent}${simplifyTextualMermaidLabel(stripped)}`;
  };

  const normalizeErCardinality = (token: string, side: "left" | "right") => {
    const normalizedToken = token
      .trim()
      .replace(/^["']|["']$/g, "")
      .toLowerCase();
    if (["1", "one", "exactly one", "||"].includes(normalizedToken)) {
      return "||";
    }
    if (["0..1", "0,1", "zero or one", "optional one", "o|", "|o", "o"].includes(normalizedToken)) {
      return side === "left" ? "o|" : "|o";
    }
    if (
      ["many", "1..*", "one or more", "mandatory many", "|{", "}|", "{"].includes(normalizedToken)
    ) {
      return side === "left" ? "}|" : "|{";
    }
    if (
      ["0..*", "0,*", "zero or more", "optional many", "o{", "}o", "*"].includes(normalizedToken)
    ) {
      return side === "left" ? "}o" : "o{";
    }
    return token.trim();
  };

  const normalizeErConnector = (token: string) => {
    const stripped = token.trim().replace(/^["']|["']$/g, "");
    if (stripped.includes("..")) {
      return "..";
    }
    return "--";
  };

  const sanitizeErRelation = (candidate: string): string | null => {
    const stripped = candidate
      .trim()
      .replace(/^\|+|\|+$/g, "")
      .trim();
    if (!stripped || !stripped.includes(":")) {
      return null;
    }

    for (const [pattern, order] of [
      [
        /^([A-Za-z_][\w]*)\s+"([^"]+)"\s+([-.o|{}]+)\s+"([^"]+)"\s+([A-Za-z_][\w]*)(\s*:\s*.*)?$/,
        ["entity", "leftCard", "connector", "rightCard", "target", "label"] as const,
      ],
      [
        /^([A-Za-z_][\w]*)\s+"([^"]+)"\s+([-.o|{}]+)\s+([A-Za-z_][\w]*)\s+"([^"]+)"(\s*:\s*.*)?$/,
        ["entity", "leftCard", "connector", "target", "rightCard", "label"] as const,
      ],
      [
        /^([A-Za-z_][\w]*)\s+([-.o|{}]+)\s+"([^"]+)"\s+([A-Za-z_][\w]*)\s+"([^"]+)"(\s*:\s*.*)?$/,
        ["entity", "connector", "leftCard", "target", "rightCard", "label"] as const,
      ],
    ] as const) {
      const match = stripped.match(pattern);
      if (!match) {
        continue;
      }
      const parts = Object.fromEntries(order.map((key, i) => [key, match[i + 1] ?? ""]));
      return `${String(parts.entity).trim()} ${normalizeErCardinality(String(parts.leftCard), "left")}${normalizeErConnector(String(parts.connector))}${normalizeErCardinality(String(parts.rightCard), "right")} ${String(parts.target).trim()}${String(parts.label ?? "")}`;
    }

    const relationMatch = stripped.match(
      /^([A-Za-z_][\w]*)\s+([|o{}.\- ]+)\s+([A-Za-z_][\w]*)\s*:\s*(.+)$/,
    );
    if (!relationMatch) {
      return null;
    }

    const [, leftEntity, relationBlobRaw, rightEntity, label] = relationMatch;
    const relationBlob = relationBlobRaw.replace(/\s+/g, "");
    const connector = relationBlob.includes("..") ? ".." : "--";
    const [leftRaw = "|", rightRaw = "|"] = relationBlob.split(connector);
    return `${leftEntity} ${normalizeErCardinality(leftRaw || "|", "left")}${connector}${normalizeErCardinality(rightRaw || "|", "right")} ${rightEntity} : ${label}`;
  };

  const normalizeClassCardinality = (token: string) => {
    const normalizedToken = token
      .trim()
      .replace(/^["']|["']$/g, "")
      .toLowerCase();
    if (["o", "0..1", "0,1", "zero or one", "optional one"].includes(normalizedToken)) {
      return "0..1";
    }
    if (["*", "many", "0..*", "0,*", "zero or more"].includes(normalizedToken)) {
      return "*";
    }
    if (["1..*", "one or more"].includes(normalizedToken)) {
      return "1..*";
    }
    if (["1", "one", "exactly one"].includes(normalizedToken)) {
      return "1";
    }
    return token.trim().replace(/^["']|["']$/g, "");
  };

  const sanitizeClassRelation = (candidate: string): string | null => {
    const stripped = candidate.trim();
    if (!stripped || !stripped.includes('"')) {
      return null;
    }

    const malformedDoubleCardMatch = stripped.match(
      /^([A-Za-z_][\w]*)\s+"([^"]+)"\s+([-.<>*o]+)\s+"([^"]+)"\s+([A-Za-z_][\w]*)\s+"([^"]+)"(\s*:\s*.*)?$/,
    );
    if (malformedDoubleCardMatch) {
      const [, leftEntity, leftCard, relation, middleCard, rightEntity, , label = ""] =
        malformedDoubleCardMatch;
      return `${leftEntity} "${normalizeClassCardinality(leftCard)}" ${relation} "${normalizeClassCardinality(middleCard)}" ${rightEntity}${label}`;
    }

    const validMatch = stripped.match(
      /^([A-Za-z_][\w]*)\s+"([^"]+)"\s+([-.<>*o]+)\s+"([^"]+)"\s+([A-Za-z_][\w]*)(\s*:\s*.*)?$/,
    );
    if (validMatch) {
      const [, leftEntity, leftCard, relation, rightCard, rightEntity, label = ""] = validMatch;
      return `${leftEntity} "${normalizeClassCardinality(leftCard)}" ${relation} "${normalizeClassCardinality(rightCard)}" ${rightEntity}${label}`;
    }

    const malformedMatch = stripped.match(
      /^([A-Za-z_][\w]*)\s+"([^"]+)"\s+([-.<>*o]+)\s+([A-Za-z_][\w]*)\s+"([^"]+)"(\s*:\s*.*)?$/,
    );
    if (malformedMatch) {
      const [, leftEntity, leftCard, relation, rightEntity, rightCard, label = ""] = malformedMatch;
      return `${leftEntity} "${normalizeClassCardinality(leftCard)}" ${relation} "${normalizeClassCardinality(rightCard)}" ${rightEntity}${label}`;
    }

    return null;
  };

  const canonicalizeClassMember = (candidate: string): string => {
    const stripped = candidate.trim();
    if (!stripped) return candidate;

    if (/^[+\-#~]?\s*[A-Za-z_]\w*\s*:\s*[\w.~<> ,\[\]]+$/.test(stripped)) {
      return stripped;
    }

    const match = stripped.match(/^([+\-#~]?)\s*([A-Za-z_][\w.<>~, \[\]]*)\s+([A-Za-z_]\w*)$/);
    if (match) {
      const [, visibility, rawType, name] = match;
      const normalizedType = rawType
        .trim()
        .replace(/</g, "~")
        .replace(/>/g, "~")
        .replace(/\s+/g, " ");
      return `${visibility}${name}: ${normalizedType}`;
    }

    return stripped;
  };

  const sanitizeClassAttribute = (candidate: string): string => {
    const stripped = candidate.trim();
    if (
      !stripped ||
      stripped.startsWith("class ") ||
      stripped.startsWith("direction ") ||
      stripped.includes('"')
    ) {
      return candidate;
    }

    if (/^[+\-#~]/.test(stripped)) {
      const canonical = canonicalizeClassMember(stripped);
      if (
        canonical === stripped &&
        /[<~]\s*[A-Z][\w.]*\s*[>~]/.test(canonical) &&
        !canonical.includes(":")
      ) {
        return "";
      }
      return canonical;
    }
    if (/[<~]\s*[A-Z][\w.]*\s*[>~]/.test(stripped)) {
      return "";
    }

    return candidate.replace(
      /<([A-Za-z_][\w., ]*)>/g,
      (_full, typeName: string) => `~${typeName.trim()}~`,
    );
  };

  const isClassDeclarationStart = (candidate: string): string | null => {
    const stripped = candidate.trim();
    const explicitMatch = stripped.match(/^class\s+([A-Za-z_][\w]*)\s*$/);
    if (explicitMatch) {
      return explicitMatch[1] ?? null;
    }

    const implicitMatch = stripped.match(/^([A-Za-z_][\w]*)\s*$/);
    if (implicitMatch) {
      return implicitMatch[1] ?? null;
    }

    return null;
  };

  const repairDetachedClassMembers = (lines: string[]): string[] => {
    const repaired: string[] = [];

    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index] ?? "";
      const className = isClassDeclarationStart(line);
      const trimmed = line.trim();

      if (
        !className ||
        trimmed.includes("{") ||
        trimmed.startsWith("direction ") ||
        trimmed.startsWith("note ") ||
        trimmed.startsWith("%%")
      ) {
        repaired.push(line);
        continue;
      }

      const members: string[] = [];
      let cursor = index + 1;

      while (cursor < lines.length) {
        const candidate = lines[cursor] ?? "";
        const candidateTrimmed = candidate.trim();

        if (!candidateTrimmed) {
          cursor += 1;
          continue;
        }

        if (
          isClassDeclarationStart(candidate) ||
          candidateTrimmed.startsWith("direction ") ||
          candidateTrimmed.startsWith("note ") ||
          candidateTrimmed.startsWith("%%") ||
          candidateTrimmed.startsWith("class ") ||
          candidateTrimmed.includes("{") ||
          candidateTrimmed.includes("}") ||
          sanitizeClassRelation(candidateTrimmed)
        ) {
          break;
        }

        if (/^[+\-#~]/.test(candidateTrimmed)) {
          const sanitizedMember = sanitizeClassAttribute(candidateTrimmed).trim();
          if (sanitizedMember) {
            members.push(`  ${sanitizedMember}`);
          }
          cursor += 1;
          continue;
        }

        break;
      }

      if (members.length > 0) {
        repaired.push(`class ${className} {`);
        repaired.push(...members);
        repaired.push("}");
        index = cursor - 1;
        continue;
      }

      repaired.push(line);
    }

    return repaired;
  };

  // 1. Syntax Self-Healing: Fix common LLM grammar errors before any other processing
  let healed = normalized;

  // Strip hallucinated internal markdown fences often generated by LLMs
  healed = healed.replace(/^\s*```[a-zA-Z-]*\s*$/gm, "");

  // Fix generic flowcharts missing diagram declaration
  const firstLineCheck = healed.trim().split(/\r?\n/)[0]?.trim() || "";
  const hasValidHeader =
    /^(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|erDiagram|journey|gantt|pie|requirementDiagram|gitGraph|c4context|c4container|c4component|c4dynamic|c4deployment|mindmap|timeline|sankey-beta|xychart-beta|block-beta|architecture-beta)\b/i.test(
      firstLineCheck,
    );

  if (!hasValidHeader) {
    // If the block starts immediately with a node edge or a subgraph, inject the missing header.
    if (
      /^\s*[A-Za-z0-9_-]+\s*(-->|==>|-.->|===>)\s*[A-Za-z0-9_-]/.test(firstLineCheck) ||
      /^\s*subgraph\b/i.test(firstLineCheck)
    ) {
      healed = "graph TD\n" + healed;
    }
  }

  // Missing newline after direction (e.g. "graph TDSubgraph")
  if (/^graph\s+(TD|LR|BT|RL)[A-Za-z]/m.test(healed)) {
    healed = healed.replace(/^(graph\s+(?:TD|LR|BT|RL))([A-Za-z])/m, "$1\n$2");
  }
  // Smashed subgraph keyword
  healed = healed.replace(/(subgraph)(\S)/g, "$1 $2");

  let sanitized = healed
    .replace(/^(graph\s+(?:TB|TD|BT|RL|LR))\s*([\s\S]*)$/i, (_full, starter, rest) => {
      const normalizedRest = String(rest)
        .replace(/^\|+\s*/, "")
        .trimStart();
      return normalizedRest ? `${starter}\n${normalizedRest}` : String(starter);
    })
    .replace(/^(flowchart\s+(?:TB|TD|BT|RL|LR))\s*([\s\S]*)$/i, (_full, starter, rest) => {
      const normalizedRest = String(rest)
        .replace(/^\|+\s*/, "")
        .trimStart();
      return normalizedRest ? `${starter}\n${normalizedRest}` : String(starter);
    })
    .replace(/^(erdiagram)\s*(.+)$/i, (_full, _starter, rest) =>
      String(rest).trim() ? `erDiagram\n${String(rest).trimStart()}` : "erDiagram",
    )
    .replace(/^(classdiagram)\s*(.+)$/i, (_full, _starter, rest) =>
      String(rest).trim() ? `classDiagram\n${String(rest).trimStart()}` : "classDiagram",
    )
    .replace(/^(statediagram(?:-v2)?)\s*(.+)$/i, (_full, starter, rest) =>
      String(rest).trim() ? `${starter}\n${String(rest).trimStart()}` : String(starter),
    )
    .replace(/^(sequencediagram)\s*(.+)$/i, (_full, _starter, rest) =>
      String(rest).trim() ? `sequenceDiagram\n${String(rest).trimStart()}` : "sequenceDiagram",
    )
    .replace(/^(mindmap)\s*(.+)$/i, (_full, _starter, rest) =>
      String(rest).trim() ? `mindmap\n${String(rest).trimStart()}` : "mindmap",
    )
    .replace(/^(journey)\s*(.+)$/i, (_full, _starter, rest) =>
      String(rest).trim() ? `journey\n${String(rest).trimStart()}` : "journey",
    )
    .replace(/^(timeline)\s*(.+)$/i, (_full, _starter, rest) =>
      String(rest).trim() ? `timeline\n${String(rest).trimStart()}` : "timeline",
    )
    .replace(/^(gantt)\s*(.+)$/i, (_full, _starter, rest) =>
      String(rest).trim() ? `gantt\n${String(rest).trimStart()}` : "gantt",
    );

  const firstLine = sanitized.split(/\r?\n/, 1)[0]?.trim().toLowerCase() ?? "";
  if (firstLine.startsWith("erdiagram")) {
    sanitized = sanitized
      .split(/\r?\n/)
      .map((line, index) => {
        if (index === 0) {
          return line;
        }
        let nextLine = line
          .replace(/^\|\s*([A-Za-z_][\w]*)\s*\|\s*/, "$1 ")
          .replace(/\s*\|\s*$/, "")
          .replace(/\s+\|\s*\|\s*--/g, " ||--")
          .replace(/^(\s*[A-Za-z_][\w]*)\s+\|\s*--/g, "$1 |--")
          .replace(/--\s*\|\s*\|/g, "--|| ");
        nextLine = nextLine.replace(
          /(:\s*[^:\n]+?)\s+(?=\|?[A-Za-z_][\w]*\s+(?:[|o{}.\-"]|--))/g,
          "$1\n",
        );
        return nextLine
          .split(/\r?\n/)
          .map((candidate) => {
            const trimmed = candidate.trim();
            if (!trimmed) {
              return "";
            }
            return sanitizeErRelation(trimmed) ?? trimmed;
          })
          .filter(Boolean)
          .join("\n");
      })
      .join("\n");
    return sanitized;
  }

  if (firstLine.startsWith("classdiagram")) {
    const lines = repairDetachedClassMembers(sanitized.split(/\r?\n/));
    const hasDirection = lines.some(
      (line, index) => index > 0 && line.trim().toLowerCase().startsWith("direction "),
    );
    const nextLines = lines
      .map((line, index) => {
        if (index === 0) {
          return line;
        }
        return sanitizeClassRelation(line) ?? sanitizeClassAttribute(line);
      })
      .filter((line) => line.trim().length > 0);
    if (!hasDirection) {
      nextLines.splice(1, 0, "direction TB");
    }
    return nextLines.join("\n");
  }

  if (firstLine.startsWith("mindmap")) {
    const mindmapLines = repairMindmapStructure(healed.split(/\r?\n/));
    return [
      mindmapLines[0],
      ...mindmapLines.slice(1).map((line) => sanitizeMindmapLine(line)),
    ].join("\n");
  }

  if (firstLine.startsWith("journey")) {
    const journeyLines = healed.split(/\r?\n/);
    return [
      journeyLines[0],
      ...journeyLines.slice(1).map((line) => sanitizeJourneyLine(line)),
    ].join("\n");
  }

  if (firstLine.startsWith("timeline")) {
    const timelineLines = healed.split(/\r?\n/);
    return [
      timelineLines[0],
      ...timelineLines.slice(1).map((line) => sanitizeTimelineLine(line)),
    ].join("\n");
  }

  if (firstLine.startsWith("gantt")) {
    const ganttLines = healed.split(/\r?\n/);
    return [ganttLines[0], ...ganttLines.slice(1).map((line) => sanitizeGanttLine(line))].join(
      "\n",
    );
  }

  if (!(firstLine.startsWith("flowchart") || firstLine.startsWith("graph"))) {
    return sanitized;
  }

  const complexLabelPattern = /([A-Za-z][\w-]*)\[((?:[^\[\]]|\[[^\]]*\])*)\]/g;
  return sanitized
    .split(/\r?\n/)
    .flatMap((line) => {
      const trimmed = line.trim();
      if (
        !trimmed ||
        trimmed.startsWith("style ") ||
        trimmed.startsWith("classDef ") ||
        trimmed.startsWith("class ") ||
        trimmed.startsWith("linkStyle ")
      ) {
        return [line];
      }
      const normalizedLine = line
        .replace(/(-->|==>|-.->)\s+\|/g, "$1|")
        .replace(/(-->|==>|-.->)\|\s*([^|]+?)\s*\|/g, (_full, arrow, label) => {
          const normalizedLabel = String(label).trim();
          return `${String(arrow)}|${normalizedLabel}|`;
        })
        .replace(/\s+\|\|\s+/g, "\n")
        .replace(/\|\|\s+/g, "\n")
        .replace(/\s+\|\|/g, "\n")
        .replace(/\s+\|\|\s+(?=[A-Za-z][\w-]*\s+(?:\-{1,2}|\.?-{2,}\.?|={2,})[->])/g, "\n")
        .replace(/\|\|\s*(?=[A-Za-z][\w-]*\s+(?:\-{1,2}|\.?-{2,}\.?|={2,})[->])/g, "\n");

      return normalizedLine.split(/\r?\n/).map((segment) =>
        segment.replace(complexLabelPattern, (full, nodeId, rawLabel) => {
          const label = String(rawLabel).trim();
          if (!label) {
            return full;
          }
          if (label.startsWith('"') && label.endsWith('"')) {
            return full;
          }
          if (!/[(),.:;'"]/.test(label)) {
            return full;
          }
          const escaped = label.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
          return `${nodeId}["${escaped}"]`;
        }),
      );
    })
    .join("\n");
}

function getMermaidFamily(source: string): string {
  const normalized = source.trim();
  const lines = normalized.split(/\r?\n/).map((line) => line.trim());
  const firstLine =
    lines.find((line) => line.length > 0 && !line.startsWith("%%"))?.toLowerCase() ?? "";
  if (firstLine.startsWith("classdiagram")) return "classdiagram";
  if (firstLine.startsWith("erdiagram")) return "erdiagram";
  if (firstLine.startsWith("statediagram")) return "statediagram";
  if (firstLine.startsWith("sequencediagram")) return "sequencediagram";
  if (firstLine.startsWith("timeline")) return "timeline";
  if (firstLine.startsWith("gantt")) return "gantt";
  if (firstLine.startsWith("journey")) return "journey";
  if (firstLine.startsWith("mindmap")) return "mindmap";
  if (firstLine.startsWith("pie")) return "pie";
  if (firstLine.startsWith("gitgraph")) return "gitgraph";
  if (firstLine.startsWith("quadrantchart")) return "quadrantchart";
  if (firstLine.startsWith("requirementdiagram")) return "requirementdiagram";
  if (firstLine.startsWith("block-beta")) return "block-beta";
  if (firstLine.startsWith("xychart-beta")) return "xychart-beta";
  if (
    firstLine.startsWith("c4context") ||
    firstLine.startsWith("c4container") ||
    firstLine.startsWith("c4component") ||
    firstLine.startsWith("c4dynamic") ||
    firstLine.startsWith("c4deployment")
  ) {
    return "c4";
  }
  if (firstLine.startsWith("architecture-beta")) return "architecture-beta";
  if (firstLine.startsWith("sankey")) return "sankey";
  if (firstLine.startsWith("packet")) return "packet";
  if (firstLine.startsWith("kanban")) return "kanban";
  if (firstLine.startsWith("zenuml")) return "zenuml";
  if (firstLine.startsWith("flowchart")) return "flowchart";
  if (firstLine.startsWith("graph")) return "graph";
  if (
    normalized.includes("->>") ||
    normalized.includes("-->>") ||
    normalized.includes("participant ")
  ) {
    return "sequencediagram";
  }
  if (normalized.includes("[*] -->") || /\bstate\s+[A-Za-z_]/i.test(normalized)) {
    return "statediagram";
  }
  if (/\b[A-Za-z0-9_-]+\s*(-->|==>|-.->|===>)\s*[A-Za-z0-9_-]+/.test(normalized)) {
    return "flowchart";
  }
  return "generic";
}

function getMermaidMinimumHeight(source: string): number {
  switch (getMermaidFamily(source)) {
    case "classdiagram":
      return 900;
    case "erdiagram":
      return 860;
    case "timeline":
      return 700;
    case "gantt":
      return 700;
    case "journey":
      return 720;
    case "sequencediagram":
      return 640;
    case "mindmap":
      return 720;
    case "c4":
    case "architecture-beta":
      return 760;
    case "sankey":
      return 620;
    case "packet":
    case "kanban":
    case "quadrantchart":
    case "xychart-beta":
    case "zenuml":
    case "block":
      return 560;
    case "gitgraph":
      return 520;
    case "pie":
      return 500;
    case "flowchart":
    case "graph":
      return 460;
    case "statediagram":
      return 440;
    default:
      return 420;
  }
}

function measureVisibleSvgContent(svg: SVGSVGElement): {
  x: number;
  y: number;
  width: number;
  height: number;
} | null {
  const elements = Array.from(
    svg.querySelectorAll<SVGGraphicsElement>(
      "rect, polygon, path, circle, ellipse, line, polyline, text, foreignObject",
    ),
  );

  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  let found = false;

  for (const element of elements) {
    if (
      element instanceof SVGSVGElement ||
      element.closest("defs, marker, clipPath, mask, pattern, symbol")
    ) {
      continue;
    }

    const computed = window.getComputedStyle(element);
    if (
      computed.display === "none" ||
      computed.visibility === "hidden" ||
      Number.parseFloat(computed.opacity || "1") === 0
    ) {
      continue;
    }

    try {
      const bbox = element.getBBox();
      if (!(bbox.width > 0 || bbox.height > 0)) {
        continue;
      }

      const matrix = typeof element.getCTM === "function" ? element.getCTM() : null;
      if (matrix) {
        const corners = [
          { x: bbox.x, y: bbox.y },
          { x: bbox.x + bbox.width, y: bbox.y },
          { x: bbox.x, y: bbox.y + bbox.height },
          { x: bbox.x + bbox.width, y: bbox.y + bbox.height },
        ].map((point) => ({
          x: matrix.a * point.x + matrix.c * point.y + matrix.e,
          y: matrix.b * point.x + matrix.d * point.y + matrix.f,
        }));

        minX = Math.min(minX, ...corners.map((corner) => corner.x));
        minY = Math.min(minY, ...corners.map((corner) => corner.y));
        maxX = Math.max(maxX, ...corners.map((corner) => corner.x));
        maxY = Math.max(maxY, ...corners.map((corner) => corner.y));
      } else {
        minX = Math.min(minX, bbox.x);
        minY = Math.min(minY, bbox.y);
        maxX = Math.max(maxX, bbox.x + bbox.width);
        maxY = Math.max(maxY, bbox.y + bbox.height);
      }
      found = true;
    } catch {
      // Ignore SVG elements that cannot provide bounds yet.
    }
  }

  if (!found) {
    return null;
  }

  return {
    x: minX,
    y: minY,
    width: maxX - minX,
    height: maxY - minY,
  };
}

function hasMeaningfulSvgBounds(
  bounds: {
    x: number;
    y: number;
    width: number;
    height: number;
  } | null,
): bounds is {
  x: number;
  y: number;
  width: number;
  height: number;
} {
  return Boolean(
    bounds &&
    bounds.width > MIN_MEANINGFUL_SVG_DIMENSION &&
    bounds.height > MIN_MEANINGFUL_SVG_DIMENSION,
  );
}

function readSvgViewBoxBounds(svg: SVGSVGElement): {
  x: number;
  y: number;
  width: number;
  height: number;
} | null {
  const viewBox = svg.viewBox?.baseVal;
  if (
    !viewBox ||
    !Number.isFinite(viewBox.width) ||
    viewBox.width <= 0 ||
    !Number.isFinite(viewBox.height) ||
    viewBox.height <= 0
  ) {
    return null;
  }

  return {
    x: viewBox.x,
    y: viewBox.y,
    width: viewBox.width,
    height: viewBox.height,
  };
}

const MIN_MEANINGFUL_SVG_DIMENSION = 20;

export default function CodeBlock({
  language,
  value,
  incomplete = false,
  enableRichPreview = true,
  answerStreaming = false,
  defaultPreviewOpen = false,
  title = null,
}: CodeBlockProps) {
  const normalizedLanguage = (language ?? "code").toLowerCase();
  const normalizedMermaidValue =
    normalizedLanguage === "mermaid" ? sanitizeMermaidSyntax(value) : value;
  const codeValue = normalizedLanguage === "mermaid" ? normalizedMermaidValue : value;
  const shouldInitiallyOpenPreview =
    normalizedLanguage === "mermaid" && defaultPreviewOpen && !incomplete && !answerStreaming;
  const autoOpenIdentity = `${normalizedLanguage}:${defaultPreviewOpen ? "1" : "0"}:${normalizedMermaidValue}`;
  const supportsRichPreview =
    enableRichPreview &&
    (normalizedLanguage === "mermaid" ||
      normalizedLanguage === "vega" ||
      normalizedLanguage === "vega-lite");
  const mermaidFamily =
    normalizedLanguage === "mermaid" ? getMermaidFamily(normalizedMermaidValue) : "generic";
  const blockVariant = getCodeBlockVariant(normalizedLanguage, supportsRichPreview);
  const shellClasses = getShellClasses(blockVariant);
  const codeFileDescriptor = useMemo(
    () => getCodeFileDescriptor(normalizedLanguage, mermaidFamily),
    [mermaidFamily, normalizedLanguage],
  );

  const [copied, setCopied] = useState(false);
  // FIX: Separate copy error state so failed clipboard writes show feedback.
  const [copyError, setCopyError] = useState(false);
  const [renderedSvg, setRenderedSvg] = useState<string | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(() => shouldInitiallyOpenPreview);
  const [hasAutoOpened, setHasAutoOpened] = useState(() => shouldInitiallyOpenPreview);
  const [isRendering, setIsRendering] = useState(false);
  const [panEnabled, setPanEnabled] = useState(false);
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [bodyHeight, setBodyHeight] = useState(420);
  const mountedRef = useRef(true);
  const codeBodyRef = useRef<HTMLPreElement | null>(null);
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const svgStageRef = useRef<HTMLDivElement | null>(null);
  const scaleRef = useRef(1);
  const offsetRef = useRef({ x: 0, y: 0 });
  const autoOpenIdentityRef = useRef(autoOpenIdentity);
  const dragStateRef = useRef<{ active: boolean; x: number; y: number }>({
    active: false,
    x: 0,
    y: 0,
  });

  // FIX: Stable ID — never changes after mount.
  const diagramId = useStableId("codeblock-diagram");
  // FIX: Reactive theme — updates on dark/light mode switch.
  const mermaidTheme = useMermaidTheme();
  const usesRelaxedMermaidSecurity = [
    "c4",
    "architecture-beta",
    "sankey",
    "packet",
    "kanban",
    "block-beta",
    "timeline",
    "mindmap",
    "journey",
    "pie",
    "xychart-beta",
  ].includes(mermaidFamily);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    scaleRef.current = scale;
  }, [scale]);

  useEffect(() => {
    offsetRef.current = offset;
  }, [offset]);

  useEffect(() => {
    if (!isExpanded) {
      dragStateRef.current.active = false;
      setPanEnabled(false);
      setScale(1);
      setOffset({ x: 0, y: 0 });
    }
  }, [isExpanded]);

  useEffect(() => {
    if (autoOpenIdentityRef.current === autoOpenIdentity) {
      return;
    }

    autoOpenIdentityRef.current = autoOpenIdentity;
    setHasAutoOpened(false);
  }, [autoOpenIdentity]);

  useEffect(() => {
    if (answerStreaming && isExpanded && normalizedLanguage !== "mermaid") {
      setIsExpanded(false);
    }
  }, [answerStreaming, isExpanded, normalizedLanguage]);

  useEffect(() => {
    if (
      defaultPreviewOpen &&
      normalizedLanguage === "mermaid" &&
      !incomplete &&
      !answerStreaming &&
      !isExpanded &&
      !hasAutoOpened
    ) {
      setIsExpanded(true);
      setHasAutoOpened(true);
    }
  }, [
    answerStreaming,
    defaultPreviewOpen,
    hasAutoOpened,
    incomplete,
    isExpanded,
    normalizedLanguage,
  ]);

  useEffect(() => {
    if (isExpanded) {
      return;
    }

    const element = codeBodyRef.current;
    if (!element) {
      return;
    }

    const updateHeight = () => {
      const minimumHeight =
        normalizedLanguage === "mermaid"
          ? getMermaidMinimumHeight(normalizedMermaidValue)
          : COLLAPSED_BODY_MIN_HEIGHT;
      const maximumHeight = getCollapsedBodyHeightLimit(normalizedLanguage);
      setBodyHeight(
        Math.min(maximumHeight, Math.max(minimumHeight, Math.ceil(element.scrollHeight))),
      );
    };

    updateHeight();

    if (typeof ResizeObserver === "undefined") {
      return;
    }

    const observer = new ResizeObserver(() => {
      updateHeight();
    });
    observer.observe(element);

    return () => observer.disconnect();
  }, [isExpanded, normalizedMermaidValue, normalizedLanguage]);

  const clampScale = (nextScale: number) => Math.min(4.5, Math.max(0.25, nextScale));

  const getSvgBounds = () => {
    const stage = svgStageRef.current;
    const svg = stage?.querySelector("svg");
    if (!stage || !svg) {
      return null;
    }

    if (svg.dataset.averqelViewportNormalized === "true") {
      const normalizedViewBoxBounds = readSvgViewBoxBounds(svg);
      if (normalizedViewBoxBounds) {
        return normalizedViewBoxBounds;
      }
    }

    const measuredBounds = measureVisibleSvgContent(svg);
    if (measuredBounds) {
      return measuredBounds;
    }

    const viewBoxBounds = readSvgViewBoxBounds(svg);
    if (viewBoxBounds) {
      return viewBoxBounds;
    }

    let bbox: {
      x: number;
      y: number;
      width: number;
      height: number;
    } | null = null;
    try {
      const nextBbox = typeof svg.getBBox === "function" ? svg.getBBox() : null;
      if (
        nextBbox &&
        Number.isFinite(nextBbox.width) &&
        nextBbox.width > 0 &&
        Number.isFinite(nextBbox.height) &&
        nextBbox.height > 0
      ) {
        bbox = {
          x: nextBbox.x,
          y: nextBbox.y,
          width: nextBbox.width,
          height: nextBbox.height,
        };
      }
    } catch {
      // Ignore SVGs that cannot provide a bbox yet and fall back to the viewBox.
    }

    return bbox;
  };

  const getVisibleSvgBounds = () => {
    const stage = svgStageRef.current;
    const svg = stage?.querySelector("svg");
    if (!stage || !svg) {
      return null;
    }

    return measureVisibleSvgContent(svg);
  };

  const normalizeSvgViewport = (
    preferredBounds?: {
      x: number;
      y: number;
      width: number;
      height: number;
    } | null,
  ) => {
    const stage = svgStageRef.current;
    const svg = stage?.querySelector("svg");
    if (!stage || !svg || typeof svg.getBBox !== "function") {
      return null;
    }

    try {
      const bbox = preferredBounds ?? measureVisibleSvgContent(svg) ?? svg.getBBox();
      if (!(bbox.width > 0 && bbox.height > 0)) {
        return null;
      }

      const padding = 28;
      const width = Math.ceil(bbox.width + padding * 2);
      const height = Math.ceil(bbox.height + padding * 2);
      svg.setAttribute(
        "viewBox",
        `${Math.floor(bbox.x - padding)} ${Math.floor(bbox.y - padding)} ${width} ${height}`,
      );
      svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
      svg.setAttribute("width", `${width}`);
      svg.setAttribute("height", `${height}`);
      svg.setAttribute("overflow", "visible");
      svg.dataset.averqelViewportNormalized = "true";
      return {
        x: 0,
        y: 0,
        width,
        height,
      };
    } catch {
      // Ignore Mermaid SVGs that are not ready for bbox reads yet.
      return null;
    }
  };

  const computeCenteredOffset = useCallback(
    (
      nextScale: number,
      boundsOverride?: {
        x: number;
        y: number;
        width: number;
        height: number;
      } | null,
    ) => {
      const viewport = viewportRef.current;
      const bounds = boundsOverride ?? getSvgBounds();
      if (!viewport || !bounds) {
        return null;
      }

      return {
        x: (viewport.clientWidth - bounds.width * nextScale) / 2 - bounds.x * nextScale,
        y: (viewport.clientHeight - bounds.height * nextScale) / 2 - bounds.y * nextScale,
      };
    },
    [],
  );

  const centerDiagram = (nextScale: number) => {
    const centeredOffset = computeCenteredOffset(nextScale);
    setScale(nextScale);
    setOffset(centeredOffset ?? { x: 0, y: 0 });
  };

  const fitDiagram = useCallback(
    (
      boundsOverride?: {
        x: number;
        y: number;
        width: number;
        height: number;
      } | null,
    ) => {
      const viewport = viewportRef.current;
      const bounds = boundsOverride ?? getSvgBounds();
      if (!viewport || !bounds) {
        return;
      }

      const padding =
        mermaidFamily === "timeline" || mermaidFamily === "gantt" || mermaidFamily === "journey"
          ? 32
          : mermaidFamily === "classdiagram" || mermaidFamily === "erdiagram"
            ? 16
            : 56;
      let fitScale = clampScale(
        Math.min(
          (viewport.clientWidth - padding) / bounds.width,
          (viewport.clientHeight - padding) / bounds.height,
        ),
      );

      const minimumFitScale =
        mermaidFamily === "classdiagram" || mermaidFamily === "erdiagram"
          ? 0.9
          : mermaidFamily === "timeline" ||
              mermaidFamily === "journey" ||
              mermaidFamily === "gantt" ||
              mermaidFamily === "mindmap"
            ? 0.85
            : mermaidFamily === "flowchart" ||
                mermaidFamily === "graph" ||
                mermaidFamily === "statediagram"
              ? 0.7
              : 0.6;
      fitScale = clampScale(Math.max(minimumFitScale, fitScale));

      setScale(fitScale);
      setOffset(computeCenteredOffset(fitScale, bounds) ?? { x: 0, y: 0 });
    },
    [computeCenteredOffset, mermaidFamily],
  );

  const zoomAtViewportCenter = (multiplier: number) => {
    const viewport = viewportRef.current;
    const currentScale = scaleRef.current;
    const nextScale = clampScale(currentScale * multiplier);
    if (nextScale === currentScale || !viewport) {
      return;
    }

    const centerX = viewport.clientWidth / 2;
    const centerY = viewport.clientHeight / 2;
    const nextOffset = {
      x: centerX - ((centerX - offsetRef.current.x) / currentScale) * nextScale,
      y: centerY - ((centerY - offsetRef.current.y) / currentScale) * nextScale,
    };
    setScale(nextScale);
    setOffset(nextOffset);
  };

  useEffect(() => {
    if (!isExpanded || !renderedSvg || isRendering) {
      return;
    }

    let frame = 0;
    let cancelled = false;
    let rafId = 0;

    setScale(1);
    setOffset({ x: 0, y: 0 });

    const attemptFit = () => {
      if (cancelled) {
        return;
      }

      const viewport = viewportRef.current;
      const visibleBounds = getVisibleSvgBounds();
      if (
        viewport &&
        viewport.clientWidth > 0 &&
        viewport.clientHeight > 0 &&
        hasMeaningfulSvgBounds(visibleBounds)
      ) {
        const normalizedBounds = normalizeSvgViewport(visibleBounds);
        fitDiagram(normalizedBounds ?? visibleBounds);
        return;
      }

      if (frame < 20) {
        frame += 1;
        rafId = window.requestAnimationFrame(attemptFit);
        return;
      }

      const normalizedBounds = normalizeSvgViewport();
      const fallbackBounds = getSvgBounds();
      if (viewport && viewport.clientWidth > 0 && viewport.clientHeight > 0 && fallbackBounds) {
        fitDiagram(normalizedBounds ?? fallbackBounds);
      }
    };

    rafId = window.requestAnimationFrame(attemptFit);

    return () => {
      cancelled = true;
      window.cancelAnimationFrame(rafId);
    };
  }, [fitDiagram, isExpanded, renderedSvg, isRendering]);

  // FIX: handleCopy now catches clipboard permission errors and shows feedback.
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(codeValue);
      setCopied(true);
      setCopyError(false);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopyError(true);
      window.setTimeout(() => setCopyError(false), 2000);
    }
  };

  const handleSave = () => {
    if (!codeValue.trim()) {
      return;
    }

    const objectUrl = createObjectUrl(codeValue, codeFileDescriptor.mimeType);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `${codeFileDescriptor.baseName}.${codeFileDescriptor.extension}`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  };

  useEffect(() => {
    let cancelled = false;

    async function renderRichPreview() {
      if (!supportsRichPreview) {
        setRenderedSvg(null);
        setRenderError(null);
        setIsRendering(false);
        return;
      }

      if (!isExpanded) {
        setIsRendering(false);
        return;
      }

      // Vega and Mermaid render only on demand once the user opens the preview.
      if (incomplete) {
        setRenderedSvg(null);
        setRenderError(null);
        setIsRendering(false);
        return;
      }

      try {
        if (!cancelled && mountedRef.current) {
          setIsRendering(true);
        }
        if (normalizedLanguage === "mermaid") {
          const mermaidSource = normalizedMermaidValue;
          const mermaidModule = await import("mermaid");
          const mermaid = mermaidModule.default;
          const isDark = mermaidTheme === "dark";
          const isClassDiagram = mermaidFamily === "classdiagram";
          const mermaidThemeVariables: Record<string, unknown> = {
            primaryColor: isDark ? "#e0f2fe" : "#dbeafe",
            primaryTextColor: "#0f172a",
            primaryBorderColor: isDark ? "#60a5fa" : "#2563eb",
            secondaryColor: isDark ? "#dcfce7" : "#dcfce7",
            secondaryTextColor: "#0f172a",
            tertiaryColor: isDark ? "#fef3c7" : "#fef3c7",
            tertiaryTextColor: "#0f172a",
            nodeTextColor: "#0f172a",
            lineColor: isDark ? "#94a3b8" : "#475569",
            textColor: isDark ? "#e2e8f0" : "#0f172a",
            mainBkg: isDark ? "#020817" : "#ffffff",
            clusterBkg: isDark ? "#0f172a" : "#eff6ff",
            clusterBorder: isDark ? "#334155" : "#93c5fd",
            edgeLabelBackground: "transparent",
            actorTextColor: "#f8fafc",
            actorBorder: isDark ? "#cbd5e1" : "#334155",
          };

          if (!isClassDiagram) {
            mermaidThemeVariables.fontSize =
              mermaidFamily === "erdiagram"
                ? "14px"
                : mermaidFamily === "timeline" || mermaidFamily === "gantt"
                  ? "17px"
                  : "16px";
          }

          // FIX: Removed @ts-ignore — typed cast instead of broad suppression.
          (mermaid.initialize as (config: Record<string, unknown>) => void)({
            startOnLoad: false,
            securityLevel: usesRelaxedMermaidSecurity ? "loose" : "strict",
            suppressErrorRendering: true,
            theme: mermaidTheme,
            fontFamily: isClassDiagram
              ? undefined
              : '"IBM Plex Sans", "Segoe UI", ui-sans-serif, system-ui, -apple-system, sans-serif',
            flowchart: {
              useMaxWidth: false,
              htmlLabels: false,
              nodeSpacing: 42,
              rankSpacing: 54,
              curve: "basis",
            },
            sequence: { useMaxWidth: false, showSequenceNumbers: true },
            gantt: { useMaxWidth: false },
            themeVariables: mermaidThemeVariables,
          });

          try {
            await mermaid.parse(mermaidSource, { suppressErrors: true });
          } catch (error) {
            if (!cancelled && mountedRef.current) {
              setRenderError(error instanceof Error ? error.message : "Invalid Mermaid syntax.");
              setIsRendering(false);
            }
            return;
          }

          // FIX: Uses stable diagramId — no new ID per render, no cache misses,
          // no orphaned SVG elements left in the DOM.
          const { svg } = await mermaid.render(diagramId, mermaidSource);

          if (!cancelled && mountedRef.current) {
            setRenderedSvg(normalizeRenderedSvg(svg, mermaidFamily));
            setRenderError(null);
            setIsRendering(false);
          }
          return;
        }

        // Vega / Vega-Lite
        const [{ parse, View }, vegaLiteModule] = await Promise.all([
          import("vega"),
          normalizedLanguage === "vega-lite" ? import("vega-lite") : Promise.resolve(null),
        ]);

        const parsedSpec = JSON.parse(value) as Record<string, unknown>;
        const vegaLiteCompiler = vegaLiteModule as unknown as {
          compile: (spec: Record<string, unknown>) => {
            spec: Record<string, unknown>;
          };
        } | null;

        const compiled =
          normalizedLanguage === "vega-lite" && vegaLiteCompiler
            ? vegaLiteCompiler.compile(parsedSpec).spec
            : parsedSpec;

        const view = new View(parse(compiled), { renderer: "none" });
        const svg = await view.toSVG();

        if (!cancelled && mountedRef.current) {
          setRenderedSvg(svg);
          setRenderError(null);
          setIsRendering(false);
        }
      } catch (error) {
        if (!cancelled && mountedRef.current) {
          setRenderedSvg(null);
          setRenderError(error instanceof Error ? error.message : "Unable to render preview.");
          setIsRendering(false);
        }
      }
    }

    void renderRichPreview();

    return () => {
      cancelled = true;
    };
  }, [
    incomplete,
    isExpanded,
    normalizedLanguage,
    supportsRichPreview,
    normalizedMermaidValue,
    mermaidTheme,
    diagramId,
    mermaidFamily,
    value,
    usesRelaxedMermaidSecurity,
  ]);

  return (
    <div className={shellClasses.shell}>
      {/* Header bar */}
      {/* Header bar */}
      <div className={shellClasses.header}>
        <div className="flex min-w-0 items-center gap-2">
          <span className={shellClasses.label}>
            {normalizedLanguage === "mermaid" ? "DIAGRAM" : language || "code"}
          </span>
          {title ? (
            <>
              <div className="h-3 w-[1px] bg-white/10" />
              <h4 className="truncate text-[13px] font-semibold tracking-tight text-white/90">
                {title}
              </h4>
            </>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {supportsRichPreview && isExpanded && !answerStreaming && renderedSvg && !isRendering ? (
            <div className="flex items-center gap-1 rounded-full border border-white/10 bg-slate-900/90 p-0.5">
              <button
                type="button"
                onClick={() => setPanEnabled((current) => !current)}
                className={`rounded-full px-2 py-1.5 transition ${
                  panEnabled
                    ? "bg-primary/25 text-primary"
                    : "text-white/70 hover:bg-white/5 hover:text-white"
                }`}
                title="Toggle pan"
              >
                <Move size={14} />
              </button>
              <button
                type="button"
                onClick={() => zoomAtViewportCenter(1.2)}
                className="rounded-full px-2 py-1.5 text-white/70 transition hover:bg-white/5 hover:text-white"
                title="Zoom in"
              >
                <ZoomIn size={14} />
              </button>
              <button
                type="button"
                onClick={() => zoomAtViewportCenter(1 / 1.2)}
                className="rounded-full px-2 py-1.5 text-white/70 transition hover:bg-white/5 hover:text-white"
                title="Zoom out"
              >
                <ZoomOut size={14} />
              </button>
              <button
                type="button"
                onClick={() => fitDiagram()}
                className="rounded-full px-3 py-1.5 text-[11px] font-semibold text-white/70 transition hover:bg-white/5 hover:text-white"
                title="Fit diagram"
              >
                Fit
              </button>
              <button
                type="button"
                onClick={() => centerDiagram(scaleRef.current)}
                className="rounded-full px-2 py-1.5 text-white/70 transition hover:bg-white/5 hover:text-white"
                title="Center diagram"
              >
                <LocateFixed size={14} />
              </button>
            </div>
          ) : null}
          <button
            type="button"
            onClick={handleSave}
            disabled={!codeValue.trim()}
            className={shellClasses.button}
            title={`Save as .${codeFileDescriptor.extension}`}
          >
            <Download size={13} />
            <span className="hidden sm:inline">Save</span>
          </button>
          <button type="button" onClick={handleCopy} className={shellClasses.button}>
            {copied ? (
              <Check size={13} />
            ) : copyError ? (
              <AlertTriangle size={13} className="text-amber-500" />
            ) : (
              <Copy size={13} />
            )}
            <span className="hidden sm:inline">
              {copied ? "Copied" : copyError ? "Failed" : "Copy"}
            </span>
          </button>
          {supportsRichPreview ? (
            <button
              type="button"
              onClick={() => setIsExpanded((current) => !current)}
              disabled={incomplete || answerStreaming || !value.trim()}
              className={`${shellClasses.button} ${isExpanded ? "border-primary/20 bg-primary/10 text-primary" : ""}`}
              title="View diagram"
              aria-label={isExpanded ? "Hide View" : "View"}
            >
              <Eye size={13} />
              <span>{isExpanded ? "Hide View" : "View"}</span>
            </button>
          ) : null}
        </div>
      </div>
      {supportsRichPreview && isExpanded && !answerStreaming ? (
        isRendering || incomplete ? (
          <div className="px-4 py-4">
            <div className="border-primary/15 bg-primary/5 rounded-[1.5rem] border p-6 backdrop-blur-sm">
              <div className="flex items-center gap-4">
                <div className="bg-primary/10 text-primary border-primary/20 flex h-10 w-10 items-center justify-center rounded-2xl border">
                  <GitBranch size={20} />
                </div>
                <div className="space-y-0.5">
                  <div className="flex items-center gap-2">
                    <span className="text-primary/90 text-sm font-semibold tracking-tight">
                      Processing Repository
                    </span>
                    <span className="bg-primary h-1.5 w-1.5 animate-ping rounded-full" />
                  </div>
                  <div className="text-primary/40 text-[11px] font-medium tracking-wide uppercase">
                    Analyzing Git Topology
                  </div>
                </div>
              </div>
              <div className="mt-5 space-y-2">
                <div className="bg-primary/5 h-2 w-full animate-pulse rounded-full" />
                <div className="bg-primary/5 h-2 w-3/4 animate-pulse rounded-full" />
                <div className="bg-primary/5 h-2 w-5/6 animate-pulse rounded-full" />
              </div>
            </div>
          </div>
        ) : renderedSvg ? (
          <div
            ref={viewportRef}
            data-testid="diagram-stage"
            className={`relative overflow-hidden bg-slate-950/70 ${
              panEnabled ? "cursor-grab active:cursor-grabbing" : "cursor-default"
            }`}
            style={{ height: bodyHeight }}
            onPointerDown={(event) => {
              if (!panEnabled) {
                return;
              }
              dragStateRef.current = { active: true, x: event.clientX, y: event.clientY };
              event.currentTarget.setPointerCapture(event.pointerId);
            }}
            onPointerMove={(event) => {
              if (!panEnabled || !dragStateRef.current.active) {
                return;
              }

              const deltaX = event.clientX - dragStateRef.current.x;
              const deltaY = event.clientY - dragStateRef.current.y;
              dragStateRef.current = { active: true, x: event.clientX, y: event.clientY };
              setOffset((current) => ({
                x: current.x + deltaX,
                y: current.y + deltaY,
              }));
            }}
            onPointerUp={(event) => {
              dragStateRef.current.active = false;
              if (event.currentTarget.hasPointerCapture(event.pointerId)) {
                event.currentTarget.releasePointerCapture(event.pointerId);
              }
            }}
            onPointerLeave={() => {
              dragStateRef.current.active = false;
            }}
          >
            <div className="absolute inset-0 overflow-hidden">
              <div
                ref={svgStageRef}
                className="absolute top-0 left-0 [&_svg]:block [&_svg]:max-w-none"
                style={{
                  transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
                  transformOrigin: "top left",
                  willChange: "transform",
                }}
                dangerouslySetInnerHTML={{ __html: renderedSvg }}
              />
            </div>
          </div>
        ) : renderError ? (
          <div className="px-4 py-4">
            <div className="rounded-[1.5rem] border border-amber-300/20 bg-amber-500/10 p-6 text-sm text-amber-100/85">
              {renderError}
            </div>
          </div>
        ) : (
          <div className="px-4 py-4">
            <div className="rounded-[1.5rem] border border-white/10 bg-white/5 p-6 text-sm text-white/70">
              Diagram render is not ready yet.
            </div>
          </div>
        )
      ) : (
        <pre
          ref={codeBodyRef}
          data-testid="highlighted-code-block"
          className={shellClasses.codeSurface}
          style={{ height: bodyHeight }}
        >
          <code className="relative block text-[13.5px] font-[var(--font-geist-mono,ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,Liberation_Mono,Courier_New,monospace)] sm:text-[14px]">
            <span className="pointer-events-none absolute whitespace-pre-wrap opacity-0">
              {codeValue}
            </span>
            {renderHighlightedCode(codeValue, normalizedLanguage)}
          </code>
        </pre>
      )}

      {renderError && !(supportsRichPreview && isExpanded && !answerStreaming) ? (
        <div className="border-glass-border/20 border-t px-4 py-3 text-xs text-amber-700 dark:text-amber-200/85">
          {renderError}
        </div>
      ) : null}
    </div>
  );
}
