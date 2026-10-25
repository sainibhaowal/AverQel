"use client";

import { Check, Copy, ExternalLink } from "lucide-react";
import { useState } from "react";

import type { StreamCardBlock } from "../_lib/stream-protocol";

const scoreText = (value: number) =>
  new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);

const scoreFillClasses = {
  info: "bg-foreground",
  success: "bg-foreground",
  warning: "bg-foreground",
  error: "bg-foreground",
  neutral: "bg-foreground",
} as const;

const scoreTextClasses = {
  info: "text-foreground",
  success: "text-foreground",
  warning: "text-foreground",
  error: "text-foreground",
  neutral: "text-foreground",
} as const;

export function CardLayoutAside({
  block,
  onCopyCode,
}: {
  block: StreamCardBlock;
  onCopyCode: (code: string) => Promise<boolean>;
}) {
  const [copied, setCopied] = useState(false);
  if (block.layout === "evaluation" && block.score) {
    const tone = block.score.tone ?? "warning";
    return (
      <div className="shrink-0 text-right" role="group" aria-label="Evaluation score">
        <span className={"text-xl leading-none font-semibold tabular-nums " + scoreTextClasses[tone]}>
          {scoreText(block.score.value)}/{scoreText(block.score.max)}
        </span>
      </div>
    );
  }

  if (block.layout === "referral" && block.code) {
    const code = block.code;
    return (
      <div
        className="flex min-w-0 shrink-0 items-center gap-2 text-xs sm:text-sm"
        role="group"
        aria-label="Referral code"
      >
        <span className="text-foreground/70">Code:</span>
        <span
          className="text-foreground max-w-28 truncate font-mono font-medium sm:max-w-48"
          title={code}
        >
          {code}
        </span>
        <button
          type="button"
          onClick={() => {
            void onCopyCode(code).then((success) => {
              if (!success) return;
              setCopied(true);
              window.setTimeout(() => setCopied(false), 1400);
            });
          }}
          className="theme-chip inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
          aria-label={copied ? "Referral code copied" : "Copy referral code"}
          title={copied ? "Copied" : "Copy referral code"}
        >
          {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
        </button>
      </div>
    );
  }

  return null;
}

export function CardLayoutBody({ block }: { block: StreamCardBlock }) {
  if (block.layout === "evaluation" && block.score) {
    const tone = block.score.tone ?? "warning";
    const percent = Math.min(100, Math.max(0, (block.score.value / block.score.max) * 100));
    return (
      <div className="relative mt-4" data-testid="evaluation-card-summary">
        <div
          className="h-2 w-full overflow-hidden rounded-full bg-surface-2 dark:bg-surface-0/10"
          role="progressbar"
          aria-label={block.title + " score"}
          aria-valuemin={0}
          aria-valuemax={block.score.max}
          aria-valuenow={block.score.value}
          aria-valuetext={scoreText(block.score.value) + " out of " + scoreText(block.score.max)}
        >
          <div
            className={"h-full rounded-full transition-[width] duration-500 " + scoreFillClasses[tone]}
            style={{ width: String(percent) + "%" }}
          />
        </div>
        {block.metrics?.length ? (
          <dl className="mt-4 grid min-w-0 grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
            {block.metrics.map((metric, index) => (
              <div
                key={metric.label + "-" + index}
                className="flex min-w-0 flex-col"
                data-testid="evaluation-card-metric"
              >
                <dt className="text-foreground/70 order-2 mt-1 text-sm leading-5 [text-wrap:pretty]">
                  {metric.label}
                </dt>
                <dd className="text-foreground m-0 text-xl leading-tight font-semibold tabular-nums [overflow-wrap:anywhere]">
                  {String(metric.value)}
                </dd>
                {metric.detail ? (
                  <p className="text-foreground/65 order-1 mt-1 text-xs leading-5 [text-wrap:pretty]">
                    {metric.detail}
                  </p>
                ) : null}
              </div>
            ))}
          </dl>
        ) : null}
      </div>
    );
  }

  if (block.layout === "referral" && block.primary_metric) {
    return (
      <div className="relative mt-4" data-testid="referral-card-summary">
        <div className="border-glass-border border-b pb-4">
          <p className="text-foreground m-0 text-3xl leading-none font-semibold tracking-tight tabular-nums [overflow-wrap:anywhere] sm:text-4xl">
            {String(block.primary_metric.value)}
          </p>
          <p className="text-foreground/85 mt-2 text-base leading-6 [text-wrap:pretty]">
            {block.primary_metric.label}
          </p>
          {block.primary_metric.detail ? (
            <p className="text-foreground/65 mt-1 text-sm leading-5 [text-wrap:pretty]">
              {block.primary_metric.detail}
            </p>
          ) : null}
        </div>
        {block.details?.length ? (
          <dl className="divide-glass-border mt-3 divide-y">
            {block.details.map((detail, index) => {
              const href = safeExternalHref(detail.href);
              return (
                <div
                  key={detail.label + "-" + index}
                  className="grid min-w-0 grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] items-start gap-4 py-2.5"
                  data-testid="referral-card-detail"
                >
                  <dt className="text-foreground/70 min-w-0 text-sm leading-5 [text-wrap:pretty]">
                    {detail.label}
                  </dt>
                  <dd className="text-foreground m-0 min-w-0 text-right text-sm leading-5 font-medium [overflow-wrap:anywhere] [text-wrap:pretty]">
                    {href ? (
                      <a href={href} target="_blank" rel="noreferrer noopener" className="underline">
                        {detail.value}
                      </a>
                    ) : (
                      detail.value
                    )}
                  </dd>
                </div>
              );
            })}
          </dl>
        ) : null}
      </div>
    );
  }

  return null;
}

export function CardSourceBadges({ block }: { block: StreamCardBlock }) {
  if (
    (block.layout !== "evaluation" && block.layout !== "referral") ||
    !block.sources?.length
  ) {
    return null;
  }
  return (
    <div
      className="relative mt-3 flex flex-wrap items-center gap-2"
      role="group"
      aria-label="Card sources"
    >
      {block.sources.flatMap((source, index) => {
        const href = safeExternalHref(source.url);
        if (!href) return [];
        return [
          <a
            key={source.url + "-" + index}
            href={href}
            target="_blank"
            rel="noreferrer noopener"
            className="border-glass-border bg-surface-1 text-foreground inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] leading-4 dark:bg-surface-2"
          >
            <span className="truncate">{source.title}</span>
            <ExternalLink size={11} aria-hidden="true" />
          </a>,
        ];
      })}
    </div>
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
