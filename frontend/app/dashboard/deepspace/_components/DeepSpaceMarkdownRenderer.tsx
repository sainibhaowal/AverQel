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
      table: ({ children }) => (
        <div className="my-5 overflow-x-auto rounded-xl border border-white/10">
          <table className="w-full border-collapse text-left">{children}</table>
        </div>
      ),
      h1: ({ children }) => (
        <h1 className="mt-8 mb-4 border-b border-cyan-300/20 pb-3 text-3xl font-bold tracking-tight text-cyan-50">
          {children}
        </h1>
      ),
      h2: ({ children }) => (
        <h2 className="mt-7 mb-3 text-2xl font-semibold tracking-tight text-cyan-100">
          {children}
        </h2>
      ),
      h3: ({ children }) => (
        <h3 className="text-foreground mt-6 mb-2 text-xl font-semibold">{children}</h3>
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
      p: ({ children }) => <p className="text-foreground/90 my-3 leading-8">{children}</p>,
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
      ul: ({ children }) => <ul className="my-2 list-disc space-y-2 pl-5">{children}</ul>,
      ol: ({ children }) => <ol className="my-2 list-decimal space-y-2 pl-5">{children}</ol>,
      li: ({ children }) => (
        <li className="text-foreground/85 pl-1 marker:text-cyan-300">{children}</li>
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
    [streaming],
  );
  const normalizedContent = useMemo(() => normalizeMarkdown(content), [content]);

  // Markdown is intentionally rendered as stable text during token streaming.
  // Re-parsing incomplete fences/tables/lists on every token causes React to
  // replace block nodes and makes the chat viewport flash or jump. The rich
  // renderer is restored as soon as the stream completes.
  if (streaming) {
    return (
      <div
        className="text-foreground/90 my-3 leading-8 break-words whitespace-pre-wrap"
        aria-live="polite"
      >
        {normalizedContent || "\u00a0"}
      </div>
    );
  }

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
