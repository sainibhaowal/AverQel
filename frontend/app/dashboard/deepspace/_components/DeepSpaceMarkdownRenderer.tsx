"use client";

import { memo, useEffect, useId, useMemo, useState } from "react";
import { Check, ChevronDown, Copy, Download } from "lucide-react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { normalizeMarkdown, normalizeThinkingDisplay } from "../_lib/markdown";
import { isMermaidErrorSvg } from "../../query/_lib/mermaid";
import { sanitizeMermaidSyntax } from "../../query/_components/CodeBlock";
import AdaptiveMarkdownTable from "../../_components/AdaptiveMarkdownTable";
import { exportDiagramPdf, exportDiagramPng, exportDiagramSvg } from "@/lib/client-export";
import { useTheme } from "../../../context/ThemeContext";

function MermaidPreview({ source }: { source: string }) {
  const id = useId().replace(/:/g, "");
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const [copied, setCopied] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [exporting, setExporting] = useState<"png" | "pdf" | null>(null);
  const sanitizedSource = useMemo(() => sanitizeMermaidSyntax(source), [source]);
  const { theme } = useTheme();

  useEffect(() => {
    let cancelled = false;
    void import("mermaid")
      .then(async ({ default: mermaid }) => {
        const isDark = theme === "dark";
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          suppressErrorRendering: true,
          theme: isDark ? "dark" : "default",
          fontFamily: "inherit",
          themeVariables: {
            primaryColor: isDark ? "#1e293b" : "#f8fafc",
            primaryTextColor: isDark ? "#e2e8f0" : "#0f172a",
            primaryBorderColor: isDark ? "#64748b" : "#475569",
            secondaryColor: isDark ? "#0f172a" : "#ffffff",
            tertiaryColor: isDark ? "#111827" : "#f1f5f9",
            lineColor: isDark ? "#94a3b8" : "#475569",
            nodeTextColor: isDark ? "#e2e8f0" : "#0f172a",
            mainBkg: isDark ? "#0f172a" : "#ffffff",
          },
        });
        const parsed = await mermaid.parse(sanitizedSource, { suppressErrors: true });
        if (!parsed) throw new Error("Invalid Mermaid syntax.");
        const result = await mermaid.render(`deepspace-${id}`, sanitizedSource);
        if (isMermaidErrorSvg(result.svg)) throw new Error("Invalid Mermaid syntax.");
        if (!cancelled) setSvg(result.svg);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id, sanitizedSource, theme]);

  const copySource = async () => {
    try {
      await navigator.clipboard.writeText(sanitizedSource);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  const downloadSource = () => {
    const url = URL.createObjectURL(
      new Blob([sanitizedSource], { type: "text/plain;charset=utf-8" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "diagram.mmd";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const exportDiagram = async (format: "svg" | "png" | "pdf") => {
    if (!svg) return;
    try {
      if (format === "svg") {
        exportDiagramSvg(svg, "diagram.svg");
      } else {
        setExporting(format);
        if (format === "png") await exportDiagramPng(svg, "diagram.png");
        else await exportDiagramPdf(svg, "diagram.pdf");
      }
      setExportOpen(false);
    } finally {
      setExporting(null);
    }
  };

  return (
    <div className="group relative my-4 overflow-x-auto rounded-xl border border-border bg-surface-1 p-4">
      <div className="absolute top-3 right-3 z-10 h-8 w-36 opacity-0 transition group-focus-within:opacity-100 group-hover:opacity-100">
        <button
          type="button"
          onClick={() => void copySource()}
          className="theme-chip text-foreground/72 hover:text-foreground absolute top-0 left-0 inline-flex h-8 w-8 items-center justify-center rounded-full"
          aria-label="Copy Mermaid source"
          title={copied ? "Copied" : "Copy Mermaid source"}
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
        <div className="absolute top-0 right-0">
          <button
            type="button"
            onClick={() => setExportOpen((current) => !current)}
            className="theme-chip text-foreground/72 hover:text-foreground inline-flex h-8 items-center gap-1 rounded-full px-3 text-xs"
            aria-label="Export Mermaid diagram"
            aria-expanded={exportOpen}
          >
            <Download size={14} /> Export <ChevronDown size={13} />
          </button>
          {exportOpen ? (
            <div className="theme-panel absolute top-10 right-0 grid min-w-36 gap-1 rounded-xl p-1 shadow-xl">
              <button
                type="button"
                onClick={downloadSource}
                className="rounded-lg px-3 py-2 text-left text-xs hover:bg-white/10"
              >
                Mermaid (.mmd)
              </button>
              <button
                type="button"
                onClick={() => void exportDiagram("svg")}
                disabled={!svg}
                className="rounded-lg px-3 py-2 text-left text-xs hover:bg-white/10 disabled:opacity-40"
              >
                SVG
              </button>
              <button
                type="button"
                onClick={() => void exportDiagram("png")}
                disabled={!svg || exporting !== null}
                className="rounded-lg px-3 py-2 text-left text-xs hover:bg-white/10 disabled:opacity-40"
              >
                {exporting === "png" ? "PNG…" : "PNG"}
              </button>
              <button
                type="button"
                onClick={() => void exportDiagram("pdf")}
                disabled={!svg || exporting !== null}
                className="rounded-lg px-3 py-2 text-left text-xs hover:bg-white/10 disabled:opacity-40"
              >
                {exporting === "pdf" ? "PDF…" : "PDF"}
              </button>
            </div>
          ) : null}
        </div>
      </div>
      {svg ? (
        <div dangerouslySetInnerHTML={{ __html: svg }} />
      ) : (
        <pre className="text-xs text-cyan-100">
          <code>{error ? sanitizedSource : "Rendering diagram…"}</code>
        </pre>
      )}
    </div>
  );
}

function isAsciiDiagram(source: string): boolean {
  const lines = source.split("\n").filter((line) => line.trim());
  if (lines.length < 3) return false;
  const structuralLines = lines.filter((line) => /[│┌┐└┘├┤┬┴─|+]/.test(line)).length;
  const hasFlow = /(?:↓|↑|←|→|-->|<-|\||v|\^)/.test(source);
  return structuralLines >= 2 && hasFlow;
}

function AsciiDiagramPreview({ source }: { source: string }) {
  const [copied, setCopied] = useState(false);

  const copySource = async () => {
    try {
      await navigator.clipboard.writeText(source);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <section className="group relative my-4 overflow-hidden rounded-xl border border-slate-300 bg-slate-50 shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] dark:border-white/10 dark:bg-black/25 dark:shadow-[inset_0_1px_0_rgba(255,255,255,0.03)]">
      <div className="absolute top-3 right-3 z-10 opacity-0 transition group-focus-within:opacity-100 group-hover:opacity-100">
        <button
          type="button"
          onClick={() => void copySource()}
          className="theme-chip text-foreground/72 hover:text-foreground inline-flex h-8 w-8 items-center justify-center rounded-full"
          aria-label="Copy ASCII diagram"
          title={copied ? "Copied" : "Copy ASCII diagram"}
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      </div>
      <div className="overflow-x-auto p-5 sm:p-6">
        <pre className="m-0 w-max min-w-full font-mono text-[11px] leading-6 whitespace-pre text-slate-800 [font-variant-ligatures:none] dark:text-cyan-100 sm:text-xs">
          <code>{source}</code>
        </pre>
      </div>
    </section>
  );
}

function ChartPreview({ payload }: { payload: Record<string, unknown> }) {
  const title =
    typeof payload.title === "string" && payload.title.trim() ? payload.title : "Chart Data";
  const chartType = typeof payload.chart_type === "string" ? payload.chart_type : "bar";
  const series = Array.isArray(payload.series)
    ? payload.series.filter(
        (item): item is Record<string, unknown> => Boolean(item) && typeof item === "object",
      )
    : [];
  return (
    <section
      role="img"
      aria-label={title}
      className="my-4 rounded-xl border border-white/10 bg-black/20 p-4"
    >
      <div className="flex items-center justify-between gap-3">
        <h4 className="font-semibold">{title}</h4>
        <span className="text-xs text-cyan-300 uppercase">{chartType}</span>
      </div>
      <div className="text-foreground/60 mt-2 text-xs">{series.length} points · JSON chart</div>
      <div className="text-foreground/75 mt-3 grid gap-1 text-xs">
        {series.map((point, index) => (
          <div
            key={`${String(point.label ?? index)}-${index}`}
            className="flex justify-between gap-4 rounded bg-white/[0.03] px-2 py-1"
          >
            <span>{String(point.label ?? point.name ?? index + 1)}</span>
            <span>{String(point.value ?? point.y ?? "")}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function DiffPreview({ source }: { source: string }) {
  return (
    <pre className="my-4 overflow-x-auto rounded-xl border border-white/10 bg-black/30 py-3 text-xs leading-6">
      <code className="block min-w-max font-mono">
        {source.split("\n").map((line, index) => {
          const tone =
            line.startsWith("+++") ||
            line.startsWith("---") ||
            line.startsWith("diff ") ||
            line.startsWith("index ")
              ? "text-violet-200"
              : line.startsWith("@@")
                ? "bg-cyan-300/10 text-cyan-100"
                : line.startsWith("+")
                  ? "bg-emerald-300/10 text-emerald-100"
                  : line.startsWith("-")
                    ? "bg-rose-300/10 text-rose-100"
                    : "text-cyan-100";
          return (
            <span key={`${index}-${line}`} className={`block min-h-6 px-4 ${tone}`}>
              {line || " "}
            </span>
          );
        })}
      </code>
    </pre>
  );
}

const DeepSpaceMarkdownRenderer = memo(function DeepSpaceMarkdownRenderer({
  content,
  streaming = false,
  compact = false,
}: {
  content: string;
  streaming?: boolean;
  compact?: boolean;
}) {
  const components = useMemo<Components>(
    () => ({
      pre: ({ children }) => <>{children}</>,
      code: ({ children, className, ...props }) => {
        const language = className?.match(/language-([^\s]+)/i)?.[1]?.toLowerCase() ?? "";
        const value = String(children).replace(/\n$/, "");
        const inline = !className && !String(children).includes("\n");
        if (inline) {
          return (
            <code className={className} {...props}>
              {children}
            </code>
          );
        }
        // Do not repeatedly mount Mermaid/chart renderers for incomplete stream
        // fences. The plain code block is stable until the provider is done.
        if (!streaming && language === "mermaid" && value.trim())
          return <MermaidPreview source={value} />;
        if (!streaming && isAsciiDiagram(value)) return <AsciiDiagramPreview source={value} />;
        if (language === "diff" || language === "patch") return <DiffPreview source={value} />;
        if (!streaming && language === "chart") {
          try {
            const parsed = JSON.parse(value) as unknown;
            if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
              return <ChartPreview payload={parsed as Record<string, unknown>} />;
            }
          } catch {
            // Keep the incomplete chart as a normal code block while streaming.
          }
        }
        return (
          <pre className="my-4 overflow-x-auto rounded-xl border border-white/10 bg-black/30 p-4 text-xs leading-6 text-cyan-100">
            <code className={className} {...props}>
              {value || (streaming ? " " : "")}
            </code>
          </pre>
        );
      },
      table: ({ children }) => <AdaptiveMarkdownTable>{children}</AdaptiveMarkdownTable>,
      h1: ({ children }) => (
        <h1
          className={`${compact ? "mt-3 mb-2 pb-1 text-lg" : "mt-8 mb-4 pb-3 text-3xl"} border-b border-cyan-300/20 font-bold tracking-tight text-cyan-50`}
        >
          {children}
        </h1>
      ),
      h2: ({ children }) => (
        <h2
          className={`${compact ? "mt-3 mb-1 text-base" : "mt-7 mb-3 text-2xl"} font-semibold tracking-tight text-cyan-100`}
        >
          {children}
        </h2>
      ),
      h3: ({ children }) => (
        <h3
          className={`text-foreground ${compact ? "mt-2 mb-1 text-sm" : "mt-6 mb-2 text-xl"} font-semibold`}
        >
          {children}
        </h3>
      ),
      h4: ({ children }) => (
        <h4 className="text-foreground mt-5 mb-2 text-base font-semibold">{children}</h4>
      ),
      h5: ({ children }) => (
        <h5 className="text-foreground mt-4 mb-2 text-sm font-semibold">{children}</h5>
      ),
      h6: ({ children }) => (
        <h6 className="text-foreground/75 mt-4 mb-2 text-xs font-semibold tracking-wider uppercase">
          {children}
        </h6>
      ),
      th: ({ children }) => (
        <th className="border-b border-white/10 bg-white/5 px-4 py-3 text-xs uppercase">
          {children}
        </th>
      ),
      td: ({ children }) => (
        <td className="text-foreground/80 border-b border-white/5 px-4 py-3 text-sm">{children}</td>
      ),
      p: ({ children }) => (
        <p className={`text-foreground/90 ${compact ? "my-1 leading-5" : "my-3 leading-8"}`}>
          {children}
        </p>
      ),
      a: ({ href, children }) => (
        <a
          href={href}
          target="_blank"
          rel="noreferrer noopener"
          className="font-medium text-cyan-300 underline decoration-cyan-300/40 underline-offset-4 hover:text-cyan-100"
        >
          {children}
        </a>
      ),
      strong: ({ children }) => <strong className="font-semibold text-cyan-50">{children}</strong>,
      em: ({ children }) => <em className="text-foreground/90">{children}</em>,
      del: ({ children }) => <del className="text-foreground/50">{children}</del>,
      hr: () => <hr className="my-7 border-white/10" />,
      ul: ({ children }) => (
        <ul className={`${compact ? "my-1 space-y-0.5" : "my-2 space-y-2"} list-disc pl-5`}>
          {children}
        </ul>
      ),
      ol: ({ children }) => (
        <ol className={`${compact ? "my-1 space-y-0.5" : "my-2 space-y-2"} list-decimal pl-5`}>
          {children}
        </ol>
      ),
      li: ({ children }) => (
        <li
          className={`text-foreground/85 ${compact ? "leading-5" : ""} pl-1 marker:text-cyan-300`}
        >
          {children}
        </li>
      ),
      input: ({ checked, ...props }) =>
        typeof checked === "boolean" ? (
          <input
            {...props}
            type="checkbox"
            checked={checked}
            readOnly
            className="mr-2 accent-cyan-400"
          />
        ) : (
          <input {...props} />
        ),
      blockquote: ({ children }) => (
        <blockquote className="my-3 border-l-2 border-cyan-400/50 bg-cyan-400/5 px-4 py-3">
          {children}
        </blockquote>
      ),
      img: ({ src, alt }) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={alt || "Markdown image"}
          loading="lazy"
          className="my-4 max-h-[34rem] max-w-full rounded-xl border border-white/10 bg-black/20 object-contain"
        />
      ),
    }),
    [compact, streaming],
  );
  // Stream events are already batched once per animation frame by
  // useDeepSpaceStream. Deferring a second time here caused each new delta to
  // cancel the renderer's pending frame, leaving paragraph-shaped stale text
  // onscreen until the provider paused or completed. Render the current live
  // value directly so Markdown structure appears as soon as its marker is
  // complete.
  const normalizedContent = useMemo(
    () => normalizeMarkdown(compact ? normalizeThinkingDisplay(content) : content),
    [compact, content],
  );

  return (
    <div
      className={`text-foreground/90 prose prose-invert my-3 max-w-none break-words ${compact ? "text-xs leading-5" : "leading-8"} ${streaming ? "is-streaming" : ""}`}
      aria-live={streaming ? "polite" : undefined}
    >
      <ReactMarkdown
        // Model output is untrusted and routinely includes dollar prices,
        // shell syntax, and copied LaTeX fragments. Do not run a LaTeX parser
        // in the chat surface: it can turn ordinary text into pathological
        // parser input. Mathematical notation remains readable as Markdown
        // text rather than risking a page-wide rendering failure.
        remarkPlugins={[remarkGfm]}
        components={components}
      >
        {normalizedContent || (streaming ? "\u00a0" : "")}
      </ReactMarkdown>
    </div>
  );
});

export default DeepSpaceMarkdownRenderer;
