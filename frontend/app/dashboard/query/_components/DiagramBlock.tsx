"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Eye, GitBranch, Minimize2, Sparkles } from "lucide-react";

import type { StreamDiagramBlock } from "../_lib/stream-protocol";
import { isMermaidErrorSvg } from "../_lib/mermaid";

import CodeBlock, { sanitizeMermaidSyntax } from "./CodeBlock";
import GraphBlock from "./GraphBlock";

interface DiagramBlockProps {
  block: StreamDiagramBlock;
  isStreaming?: boolean;
}

// FIX: Stable random ID that doesn't depend on useId format staying stable.
function useStableId(prefix: string): string {
  return useMemo(
    () => `${prefix}-${Math.random().toString(36).slice(2, 10)}`,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );
}

// FIX: Properly watches for dark mode changes on documentElement instead of
// reading it once at render time (which breaks when user switches theme).
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

export default function DiagramBlock({ block, isStreaming = false }: DiagramBlockProps) {
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isExpanded, setIsExpanded] = useState(false);
  const [isRendering, setIsRendering] = useState(false);
  const [copied, setCopied] = useState(false);
  const elementId = useStableId("diagram");
  const mermaidTheme = useMermaidTheme();
  const isMermaid = block.source === "mermaid";
  const sanitizedSyntax = useMemo(
    () => (isMermaid ? sanitizeMermaidSyntax(block.syntax) : block.syntax),
    [block.syntax, isMermaid],
  );
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!isMermaid) {
      setSvg(null);
      setError(null);
      setIsRendering(false);
      return;
    }
    if (!isExpanded || block.incomplete || !sanitizedSyntax.trim()) {
      setIsRendering(false);
      return;
    }

    let cancelled = false;

    async function renderDiagram() {
      if (!cancelled && mountedRef.current) {
        setIsRendering(true);
      }
      try {
        const mermaidModule = await import("mermaid");
        const mermaid = mermaidModule.default;
        const isDark = mermaidTheme === "dark";

        (mermaid.initialize as (config: Record<string, unknown>) => void)({
          startOnLoad: false,
          securityLevel: "strict",
          suppressErrorRendering: true,
          theme: mermaidTheme,
          fontFamily: "inherit",
          flowchart: { useMaxWidth: false, htmlLabels: true },
          sequence: { useMaxWidth: false },
          gantt: { useMaxWidth: false },
          themeVariables: {
            fontSize: "14px",
            primaryColor: isDark ? "#1e293b" : "#f1f5f9",
            primaryTextColor: isDark ? "#f8fafc" : "#0f172a",
            primaryBorderColor: isDark ? "#334155" : "#cbd5e1",
            lineColor: isDark ? "#64748b" : "#94a3b8",
            secondaryColor: isDark ? "#0f172a" : "#ffffff",
            nodeTextColor: isDark ? "#ffffff" : "#000000",
            mainBkg: isDark ? "#0f172a" : "#ffffff",
          },
        });

        try {
          const parsed = await mermaid.parse(sanitizedSyntax, { suppressErrors: true });
          if (!parsed) {
            if (!cancelled && mountedRef.current) {
              setError("Invalid Mermaid syntax.");
              setIsRendering(false);
            }
            return;
          }
        } catch (parseError) {
          if (!cancelled && mountedRef.current) {
            const message =
              parseError instanceof Error ? parseError.message : "Invalid Mermaid syntax.";
            setError(message);
            setIsRendering(false);
          }
          return;
        }

        const rendered = await mermaid.render(elementId, sanitizedSyntax);

        if (isMermaidErrorSvg(rendered.svg)) {
          if (!cancelled && mountedRef.current) {
            setSvg(null);
            setError("Mermaid could not render this diagram. Showing the source instead.");
            setIsRendering(false);
          }
          return;
        }

        if (!cancelled && mountedRef.current) {
          setSvg(rendered.svg);
          setError(null);
          setIsRendering(false);
        }
      } catch (renderError) {
        if (!cancelled && mountedRef.current) {
          const message =
            renderError instanceof Error ? renderError.message : "Failed to render diagram.";
          setError(message);
          setIsRendering(false);
        }
      }
    }

    setError(null);
    const renderTimer = window.setTimeout(() => void renderDiagram(), 0);
    return () => {
      cancelled = true;
      window.clearTimeout(renderTimer);
    };
  }, [block.incomplete, elementId, isExpanded, isMermaid, mermaidTheme, sanitizedSyntax]);

  // FIX: Fullscreen uses a portal into document.body so it can never be
  // clipped by a parent with overflow:hidden or CSS transform.
  const expandedOverlay =
    isExpanded && typeof document !== "undefined"
      ? createPortal(
          <div className="fixed inset-0 z-[9999] flex flex-col bg-slate-950/95 backdrop-blur-xl">
            <div className="flex shrink-0 items-center justify-end px-6 py-4">
              <button
                onClick={() => setIsExpanded(false)}
                className="flex items-center gap-2 rounded-full bg-slate-800/80 px-4 py-2 text-xs font-semibold text-white shadow-xl backdrop-blur transition-all hover:scale-105 hover:bg-slate-700"
              >
                <Minimize2 size={16} />
                Exit Fullscreen
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-auto p-8">
              {!isMermaid && block.graph ? (
                <div className="mx-auto max-w-6xl">
                  <GraphBlock block={{ ...block, graph: block.graph }} />
                </div>
              ) : isRendering ? (
                <div className="mx-auto max-w-4xl rounded-[1.5rem] border border-white/10 bg-white/5 p-6 text-sm text-white/70">
                  Rendering diagram view...
                </div>
              ) : svg ? (
                <div
                  className="[&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-none"
                  dangerouslySetInnerHTML={{ __html: svg }}
                />
              ) : error ? (
                <div className="mx-auto max-w-4xl rounded-[1.5rem] border border-amber-300/20 bg-amber-500/10 p-6 text-sm text-amber-100/85">
                  {error}
                </div>
              ) : (
                <div className="mx-auto max-w-4xl rounded-[1.5rem] border border-white/10 bg-white/5 p-6 text-sm text-white/70">
                  Diagram render is not ready yet.
                </div>
              )}
            </div>
          </div>,
          document.body,
        )
      : null;

  const handleCopy = async () => {
    const source =
      block.source === "graph_json" && block.graph
        ? JSON.stringify(block.graph, null, 2)
        : sanitizedSyntax;
    if (!source.trim()) {
      return;
    }
    try {
      await navigator.clipboard.writeText(source);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  };

  if (isMermaid) {
    return (
      <CodeBlock
        language="mermaid"
        value={sanitizedSyntax}
        incomplete={Boolean(block.incomplete || isStreaming)}
        enableRichPreview={true}
        answerStreaming={false}
        defaultPreviewOpen={true}
        title={block.title}
        description={block.description}
      />
    );
  }

  return (
    <section className="theme-panel w-full min-w-0 rounded-[1.8rem] px-5 py-5 shadow-[0_24px_70px_-44px_rgba(8,47,73,0.18)] sm:px-6 dark:shadow-[0_24px_70px_-44px_rgba(8,47,73,0.95)]">
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="theme-accent-pill inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11px] font-semibold tracking-[0.18em] uppercase">
          <GitBranch size={12} />
          {formatDiagramLabel(block.diagram_type)}
        </div>
        {block.title ? (
          <h4 className="text-foreground text-[15px] font-semibold tracking-[-0.015em]">
            {block.title}
          </h4>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={handleCopy}
            className="hover:border-primary/30 rounded-full border border-white/10 px-3 py-1 text-[11px] font-semibold tracking-[0.14em] uppercase transition"
          >
            {copied ? "Copied" : "Copy"}
          </button>
          <button
            type="button"
            onClick={() => setIsExpanded(true)}
            disabled={Boolean(block.incomplete || (!block.syntax.trim() && !block.graph))}
            className="hover:border-primary/30 inline-flex items-center gap-2 rounded-full border border-white/10 px-3 py-1 text-[11px] font-semibold tracking-[0.14em] uppercase transition disabled:cursor-not-allowed disabled:opacity-40"
            title="View diagram"
          >
            <Eye size={12} />
            View
          </button>
        </div>
      </div>

      {block.description ? (
        <p className="text-foreground/72 mb-4 text-[14px] leading-7">{block.description}</p>
      ) : null}

      {expandedOverlay}
      <div className="theme-code-surface text-foreground/72 rounded-[1.45rem] p-4 text-sm">
        <div className="theme-chip text-primary mb-3 inline-flex items-center gap-2 rounded-full px-3 py-1 text-[11px] tracking-[0.18em] uppercase">
          <Sparkles size={12} />
          {block.incomplete
            ? "Streaming diagram..."
            : block.syntax.trim() || block.graph
              ? "Diagram block ready"
              : "Preparing diagram..."}
        </div>
        {block.incomplete ? (
          <pre className="text-primary/80 overflow-x-auto text-xs leading-6 break-words whitespace-pre-wrap transition-opacity duration-500">
            {block.syntax}
          </pre>
        ) : block.source === "graph_json" && block.graph ? (
          <div className="space-y-3">
            <GraphBlock block={{ ...block, graph: block.graph }} />
            <div className="text-foreground/60 text-xs leading-6">
              Graph structure is ready. Use <span className="font-semibold text-current">View</span>{" "}
              to open the visual graph.
            </div>
          </div>
        ) : block.syntax.trim() ? (
          <>
            <pre className="text-primary/80 overflow-x-auto text-xs leading-6 break-words whitespace-pre-wrap">
              {block.syntax}
            </pre>
            <div className="text-foreground/60 mt-3 text-xs leading-6">
              Diagram syntax is complete. Use{" "}
              <span className="font-semibold text-current">View</span> to open the rendered visual.
            </div>
          </>
        ) : (
          <div className="text-foreground/60 text-xs leading-6">Preparing diagram block...</div>
        )}
        {error && !isExpanded ? (
          <p className="mt-3 text-xs text-amber-700 dark:text-amber-200/85">{error}</p>
        ) : null}
      </div>
    </section>
  );
}

function formatDiagramLabel(value: DiagramBlockProps["block"]["diagram_type"]) {
  return value.replace("mermaid_", "").replace(/_/g, " ");
}
