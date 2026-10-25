"use client";

import { Check, Copy, Download, ExternalLink, FileJson, Link2, Play } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { StreamCardBlock } from "../_lib/stream-protocol";

import { CardLayoutAside, CardLayoutBody, CardSourceBadges } from "./CardLayoutContent";
import VisualIcon, {
  DetailVisualIcon,
  visualCardDetailSurfaceClasses,
  visualCardToneClasses,
  visualIconBadgeClasses,
} from "./VisualIcon";

export default function CardBlock({ block }: { block: StreamCardBlock }) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);
  const tone = block.tone ?? "neutral";
  const layout = block.layout ?? "standard";
  const imageHref = safeExternalHref(block.image_url);
  const copy = async (value = block.content): Promise<boolean> => {
    setCopyError(null);
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
      return true;
    } catch (caught) {
      setCopied(false);
      setCopyError(caught instanceof Error ? caught.message : "Card content could not be copied.");
      return false;
    }
  };
  const download = () =>
    downloadText(JSON.stringify(block, null, 2), `${block.title}.json`, "application/json");

  return (
    <article
      className={`group relative overflow-hidden rounded-[1.5rem] border p-5 shadow-sm sm:p-6 ${visualCardToneClasses[tone]}`}
      data-card-layout={layout}
    >
      {layout === "feature" && imageHref ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={imageHref}
          alt={block.image_alt || block.title}
          loading="lazy"
          className="relative mb-5 max-h-72 w-full rounded-2xl border border-glass-border object-cover"
          onError={(event) => {
            event.currentTarget.style.display = "none";
          }}
        />
      ) : null}
      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          {imageHref && layout !== "feature" ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageHref}
              alt={block.image_alt || block.title}
              loading="lazy"
              className={`${layout === "place" ? "h-24 w-24 sm:h-32 sm:w-32" : "h-12 w-12"} shrink-0 rounded-xl border border-glass-border object-cover`}
              onError={(event) => {
                event.currentTarget.style.display = "none";
              }}
            />
          ) : (
            <div
              className={`${layout === "feature" ? "h-14 w-14" : "h-12 w-12"} flex shrink-0 items-center justify-center rounded-xl border shadow-sm ${visualIconBadgeClasses}`}
            >
              {block.icon ? (
                <VisualIcon name={block.icon} size={layout === "feature" ? 26 : 18} />
              ) : (
                <FileJson size={18} aria-hidden="true" />
              )}
            </div>
          )}
          <div className="min-w-0">
            <h3 className="text-foreground m-0 text-lg leading-tight font-semibold tracking-tight sm:text-xl">
              {block.title}
            </h3>
            {block.subtitle ? (
              <p className="text-foreground/75 dark:text-foreground/60 mt-1 max-w-xl text-sm leading-6 [text-wrap:pretty]">
                {block.subtitle}
              </p>
            ) : null}
          </div>
        </div>
        <div className="ml-auto flex min-w-0 max-w-full flex-wrap items-center justify-end gap-1 opacity-70 transition group-focus-within:opacity-100 group-hover:opacity-100">
          <CardLayoutAside block={block} onCopyCode={copy} />
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
      {copyError ? (
        <p className="relative mt-3 text-xs text-rose-600 dark:text-rose-300" role="alert">
          {copyError}
        </p>
      ) : null}
      <CardLayoutBody block={block} />
      {block.content.trim() ? <div className="relative mt-4 max-w-3xl text-sm leading-6 [text-wrap:pretty]">
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
      </div> : null}
      {layout !== "evaluation" && layout !== "referral" && block.details?.length ? (
        <dl className="relative mt-6 grid auto-rows-fr items-stretch gap-3 sm:grid-cols-2">
          {block.details.map((detail, index) => {
            const href = safeExternalHref(detail.href);
            return (
              <div
                key={`${detail.label}-${index}`}
                className={`flex h-full min-h-20 min-w-0 items-start gap-3 rounded-2xl border px-4 py-3 ${visualCardDetailSurfaceClasses}`}
              >
                <span
                  className={`mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-xl border shadow-sm ${visualIconBadgeClasses}`}
                  data-card-detail-icon
                >
                  <DetailVisualIcon name={detail.icon} label={detail.label} size={17} />
                </span>
                <div className="min-w-0">
                  <dt className="text-foreground/70 dark:text-foreground/65 text-[11px] leading-4 font-semibold tracking-[0.14em] uppercase">
                    {detail.label}
                  </dt>
                  <dd className="text-foreground/90 m-0 mt-1.5 text-sm leading-6 [text-wrap:pretty] [overflow-wrap:anywhere] break-words">
                    {href ? (
                      <a
                        href={href}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="underline underline-offset-2"
                      >
                        {detail.value}
                      </a>
                    ) : (
                      detail.value
                    )}
                  </dd>
                </div>
              </div>
            );
          })}
        </dl>
      ) : null}
      {layout !== "evaluation" && layout !== "referral" && block.metrics?.length ? (
        <div className="relative mt-6 grid items-stretch gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {block.metrics.map((metric) => (
            <div
              key={`${metric.label}-${String(metric.value)}`}
              className={`h-full rounded-2xl border px-4 py-3 ${visualCardDetailSurfaceClasses}`}
            >
              <div className="text-foreground/70 dark:text-foreground/65 text-[11px] leading-4 font-semibold tracking-[0.14em] uppercase">
                {metric.label}
              </div>
              <div className="text-foreground mt-1.5 text-xl leading-tight font-semibold tracking-tight tabular-nums">
                {String(metric.value)}
              </div>
              {metric.detail ? (
                <div className="text-foreground/75 dark:text-foreground/65 mt-1 text-sm leading-5 [text-wrap:pretty]">
                  {metric.detail}
                </div>
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
      {(layout === "evaluation" || layout === "referral") ? (
        <CardSourceBadges block={block} />
      ) : block.sources?.length ? (
        <div className="border-glass-border relative mt-5 flex flex-wrap gap-x-4 gap-y-2 border-t pt-4 text-[11px]">
          {block.sources.map((source, index) => {
            const href = safeExternalHref(source.url);
            return href ? (
              <a
                key={`${source.url}-${index}`}
                href={href}
                target="_blank"
                rel="noreferrer noopener"
                className="text-primary decoration-primary/25 underline underline-offset-4"
              >
                {source.title}
              </a>
            ) : null;
          })}
        </div>
      ) : null}
      {block.actions?.length ? (
        <div className="border-glass-border relative mt-5 flex flex-wrap gap-2 border-t pt-4">
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
