"use client";

import { useEffect, useId, useMemo, useState } from "react";
import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";

import { normalizeMarkdown } from "../_lib/markdown";
import { isMermaidErrorSvg } from "../../query/_lib/mermaid";
import { sanitizeMermaidSyntax } from "../../query/_components/CodeBlock";

function MermaidPreview({ source }: { source: string }) {
  const id = useId().replace(/:/g, "");
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const sanitizedSource = useMemo(() => sanitizeMermaidSyntax(source), [source]);

  useEffect(() => {
    let cancelled = false;
    void import("mermaid")
      .then(async ({ default: mermaid }) => {
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          suppressErrorRendering: true,
          theme: "dark",
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
  }, [id, sanitizedSource]);

  if (svg) {
    return (
      <div
        className="my-4 overflow-x-auto rounded-xl border border-white/10 bg-black/20 p-4"
        dangerouslySetInnerHTML={{ __html: svg }}
      />
    );
  }
  return (
    <pre className="my-4 overflow-x-auto rounded-xl border border-white/10 bg-black/30 p-4 text-xs text-cyan-100">
      <code>{error ? sanitizedSource : "Rendering diagram…"}</code>
    </pre>
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

export default function DeepSpaceMarkdownRenderer({
  content,
  streaming = false,
}: {
  content: string;
  streaming?: boolean;
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
      table: ({ children }) => (
        <div className="my-5 overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full border-collapse text-left">{children}</table>
        </div>
      ),
      th: ({ children }) => (
        <th className="border-b border-white/10 bg-white/5 px-4 py-3 text-xs uppercase">
          {children}
        </th>
      ),
      td: ({ children }) => (
        <td className="text-foreground/80 border-b border-white/5 px-4 py-3 text-sm">{children}</td>
      ),
      p: ({ children }) => <p className="text-foreground/90 leading-8">{children}</p>,
      ul: ({ children }) => <ul className="my-2 list-disc space-y-2 pl-5">{children}</ul>,
      ol: ({ children }) => <ol className="my-2 list-decimal space-y-2 pl-5">{children}</ol>,
      blockquote: ({ children }) => (
        <blockquote className="my-3 border-l-2 border-cyan-400/50 bg-cyan-400/5 px-4 py-3">
          {children}
        </blockquote>
      ),
      img: ({ src, alt }) => (
        // GIFs retain native animation in the browser. This renders the URL
        // explicitly present in the Markdown; private generated artifacts use
        // the separate authenticated artifact viewer instead.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt={alt || "Markdown image"}
          loading="lazy"
          className="my-4 max-h-[34rem] max-w-full rounded-xl border border-white/10 bg-black/20 object-contain"
        />
      ),
    }),
    [streaming],
  );
  const normalizedContent = useMemo(() => normalizeMarkdown(content), [content]);
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={components}
    >
      {normalizedContent}
    </ReactMarkdown>
  );
}
