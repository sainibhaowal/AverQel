"use client";

import { Check, Copy, Download, ExternalLink, FileJson, Link2, Play } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { StreamCardBlock } from "../_lib/stream-protocol";

export default function CardBlock({ block }: { block: StreamCardBlock }) {
  const [copied, setCopied] = useState(false);
  const tone = block.tone ?? "neutral";
  const toneClasses = {
    info: "border-cyan-400/25 bg-cyan-400/[0.07]",
    success: "border-emerald-400/25 bg-emerald-400/[0.07]",
    warning: "border-amber-400/25 bg-amber-400/[0.07]",
    error: "border-rose-400/25 bg-rose-400/[0.07]",
    neutral: "border-glass-border bg-surface-1/40",
  } as const;
  const copy = async (value = block.content) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };
  const download = () =>
    downloadText(JSON.stringify(block, null, 2), `${block.title}.json`, "application/json");

  return (
    <article
      className={`group relative overflow-hidden rounded-[1.5rem] border p-5 shadow-sm sm:p-6 ${toneClasses[tone]}`}
    >
      <div className="relative flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          {block.image_url && safeExternalHref(block.image_url) ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={safeExternalHref(block.image_url)}
              alt=""
              loading="lazy"
              className="h-12 w-12 shrink-0 rounded-xl border border-black/10 object-cover dark:border-white/15"
              onError={(event) => {
                event.currentTarget.style.display = "none";
              }}
            />
          ) : (
            <div className="bg-primary/10 text-primary flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-black/5 dark:border-white/10">
              <FileJson size={18} aria-hidden="true" />
            </div>
          )}
          <div className="min-w-0">
            <h3 className="text-foreground text-base font-semibold tracking-tight">
              {block.title}
            </h3>
            {block.subtitle ? (
              <p className="text-foreground/60 mt-1 text-xs">{block.subtitle}</p>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1 opacity-70 transition group-focus-within:opacity-100 group-hover:opacity-100">
          <button
            type="button"
            onClick={() => void copy()}
            className="theme-chip inline-flex h-8 w-8 items-center justify-center rounded-full"
            aria-label={copied ? "Card content copied" : "Copy card content"}
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
          <button
            type="button"
            onClick={download}
            className="theme-chip inline-flex h-8 w-8 items-center justify-center rounded-full"
            aria-label="Download information card"
          >
            <Download size={14} />
          </button>
        </div>
      </div>
      <div className="relative mt-4 text-sm leading-7">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            a: ({ href, children }) => {
              const safeHref = safeExternalHref(href);
              return safeHref ? (
                <a
                  href={safeHref}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="text-primary inline-flex items-center gap-1 underline underline-offset-4"
                >
                  {children}
                  <ExternalLink size={12} aria-hidden="true" />
                </a>
              ) : (
                <>{children}</>
              );
            },
            p: ({ children }) => <p className="text-foreground/85 my-2">{children}</p>,
            ul: ({ children }) => (
              <ul className="text-foreground/80 my-2 list-disc space-y-1 pl-5">{children}</ul>
            ),
            ol: ({ children }) => (
              <ol className="text-foreground/80 my-2 list-decimal space-y-1 pl-5">{children}</ol>
            ),
            strong: ({ children }) => (
              <strong className="text-foreground font-semibold">{children}</strong>
            ),
          }}
        >
          {block.content}
        </ReactMarkdown>
      </div>
      {block.metrics?.length ? (
        <div className="relative mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {block.metrics.map((metric) => (
            <div
              key={`${metric.label}-${String(metric.value)}`}
              className="rounded-xl border border-black/5 bg-black/5 px-3 py-2.5 dark:border-white/10 dark:bg-black/10"
            >
              <div className="text-foreground/55 text-[10px] font-semibold tracking-[0.14em] uppercase">
                {metric.label}
              </div>
              <div className="text-foreground mt-1 text-lg font-semibold tabular-nums">
                {String(metric.value)}
              </div>
              {metric.detail ? (
                <div className="text-foreground/55 mt-0.5 text-[11px]">{metric.detail}</div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
      {block.href && safeExternalHref(block.href) ? (
        <a
          href={safeExternalHref(block.href)}
          target="_blank"
          rel="noreferrer noopener"
          className="text-primary relative mt-5 inline-flex items-center gap-2 text-xs font-semibold tracking-[0.14em] uppercase"
        >
          Open source <Link2 size={13} aria-hidden="true" />
        </a>
      ) : null}
      {block.actions?.length ? (
        <div className="relative mt-5 flex flex-wrap gap-2 border-t border-black/10 pt-4 dark:border-white/10">
          {block.actions.map((action) => {
            const href = safeExternalHref(action.href);
            if (action.action === "copy")
              return (
                <button
                  key={action.label}
                  type="button"
                  onClick={() => void copy(action.content ?? action.label)}
                  className="theme-chip inline-flex items-center gap-2 rounded-full px-3 py-2 text-xs"
                >
                  <Copy size={13} />
                  {action.label}
                </button>
              );
            if (action.action === "download")
              return (
                <button
                  key={action.label}
                  type="button"
                  onClick={() =>
                    downloadText(
                      action.content ?? action.label,
                      action.label,
                      "text/plain;charset=utf-8",
                    )
                  }
                  className="theme-chip inline-flex items-center gap-2 rounded-full px-3 py-2 text-xs"
                >
                  <Download size={13} />
                  {action.label}
                </button>
              );
            return href ? (
              <a
                key={action.label}
                href={href}
                target="_blank"
                rel="noreferrer noopener"
                className="theme-chip inline-flex items-center gap-2 rounded-full px-3 py-2 text-xs"
              >
                <Play size={13} />
                {action.label}
              </a>
            ) : null;
          })}
        </div>
      ) : null}
    </article>
  );
}

function safeExternalHref(value?: string | null): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return url.protocol === "http:" || url.protocol === "https:" ? url.href : undefined;
  } catch {
    return undefined;
  }
}

function downloadText(content: string, filename: string, contentType: string) {
  const url = URL.createObjectURL(new Blob([content], { type: contentType }));
  const anchor = document.createElement("a");
  anchor.href = url;
  const extension = filename.toLowerCase().endsWith(".json") ? ".json" : ".txt";
  const baseName = filename.replace(/\.[^.]+$/, "");
  anchor.download = `${slugify(baseName) || "download"}${extension}`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80);
}
