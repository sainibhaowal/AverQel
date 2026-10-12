"use client";

import { useState } from "react";
import { Check, ChevronDown, Copy } from "lucide-react";

export type OperationalSummary = {
  sample_size: number;
  failure_rate: number;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  providers: Array<{
    provider: string;
    sample_size: number;
    failure_rate: number;
    p50_latency_ms: number | null;
    p95_latency_ms: number | null;
  }>;
};

type CopyResult = {
  conversationId: string;
  status: "copied" | "unavailable";
};

function formatFailureRate(rate: number): string {
  if (!Number.isFinite(rate)) return "—";
  return new Intl.NumberFormat(undefined, {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(Math.min(1, Math.max(0, rate)));
}

function formatLatency(latency: number | null): string {
  return latency === null || !Number.isFinite(latency) ? "—" : `${Math.round(latency)} ms`;
}

function splitProviderModel(value: string): { provider: string; model: string } {
  const separator = value.indexOf(":");
  if (separator < 0) return { provider: value || "Unknown provider", model: "Unknown model" };
  return {
    provider: value.slice(0, separator) || "Unknown provider",
    model: value.slice(separator + 1) || "Unknown model",
  };
}

export default function DeepSpaceOperationalSummary({
  summary,
  conversationId,
}: {
  summary: OperationalSummary;
  conversationId: string | null;
}) {
  const [copyResult, setCopyResult] = useState<CopyResult | null>(null);
  const visibleCopyStatus =
    conversationId && copyResult?.conversationId === conversationId ? copyResult.status : null;
  const providerMetrics = [...summary.providers].sort(
    (left, right) =>
      right.sample_size - left.sample_size || left.provider.localeCompare(right.provider),
  );

  const copyConversationId = async () => {
    if (!conversationId) return;
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard access is unavailable.");
      await navigator.clipboard.writeText(conversationId);
      setCopyResult({ conversationId, status: "copied" });
    } catch {
      setCopyResult({ conversationId, status: "unavailable" });
    }
  };

  return (
    <details className="group mx-auto mb-3 w-full max-w-4xl rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-xs text-emerald-950 shadow-sm dark:border-emerald-400/20 dark:bg-emerald-950/20 dark:text-emerald-100">
      <summary className="flex cursor-pointer list-none items-center gap-3 rounded-xl px-3 py-2 transition-colors outline-none hover:bg-emerald-500/5 focus-visible:ring-2 focus-visible:ring-emerald-500/60 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 flex-1">
          {summary.sample_size > 0 ? (
            <span className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
              <span>
                Provider health · {summary.sample_size} recent turns ·{" "}
                {formatFailureRate(summary.failure_rate)} failures
              </span>
              <span className="whitespace-nowrap">
                p50 {formatLatency(summary.p50_latency_ms)} · p95{" "}
                {formatLatency(summary.p95_latency_ms)}
              </span>
            </span>
          ) : (
            <span>Provider health · No recent usage yet</span>
          )}
        </span>
        <span className="flex shrink-0 items-center gap-1.5 font-medium">
          Details
          <ChevronDown
            aria-hidden="true"
            className="h-4 w-4 transition-transform group-open:rotate-180"
          />
        </span>
      </summary>

      <div className="space-y-4 border-t border-emerald-700/15 px-3 py-3 dark:border-emerald-300/15">
        <p className="text-emerald-900/75 dark:text-emerald-100/75">
          Recent usage from your account, not a live provider check. P50 is the median latency; p95
          is the slower end of recent requests.
        </p>

        {summary.sample_size === 0 ? (
          <p className="rounded-lg border border-emerald-700/15 bg-white/45 px-3 py-2 dark:border-emerald-300/15 dark:bg-black/10">
            No recent usage yet. Provider statistics will appear after a model request is recorded.
          </p>
        ) : providerMetrics.length > 0 ? (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {providerMetrics.map((metric) => {
              const { provider, model } = splitProviderModel(metric.provider);
              return (
                <article
                  key={metric.provider}
                  aria-label={`${provider} ${model} metrics`}
                  className="min-w-0 rounded-lg border border-emerald-700/15 bg-white/45 p-3 dark:border-emerald-300/15 dark:bg-black/10"
                >
                  <p className="truncate font-semibold" title={provider}>
                    {provider}
                  </p>
                  <p className="mt-0.5 break-all text-emerald-900/75 dark:text-emerald-100/75">
                    {model}
                  </p>
                  <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-2">
                    <div>
                      <dt className="text-emerald-900 dark:text-emerald-100">Turns</dt>
                      <dd className="mt-0.5 font-medium">{metric.sample_size}</dd>
                    </div>
                    <div>
                      <dt className="text-emerald-900 dark:text-emerald-100">Failures</dt>
                      <dd className="mt-0.5 font-medium">
                        {formatFailureRate(metric.failure_rate)}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-emerald-900 dark:text-emerald-100">P50 latency</dt>
                      <dd className="mt-0.5 font-medium">{formatLatency(metric.p50_latency_ms)}</dd>
                    </div>
                    <div>
                      <dt className="text-emerald-900 dark:text-emerald-100">P95 latency</dt>
                      <dd className="mt-0.5 font-medium">{formatLatency(metric.p95_latency_ms)}</dd>
                    </div>
                  </dl>
                </article>
              );
            })}
          </div>
        ) : (
          <p className="rounded-lg border border-emerald-700/15 bg-white/45 px-3 py-2 dark:border-emerald-300/15 dark:bg-black/10">
            Provider/model details are unavailable for these recent turns.
          </p>
        )}

        <div className="border-t border-emerald-700/15 pt-3 dark:border-emerald-300/15">
          <p className="font-semibold">Current conversation</p>
          {conversationId ? (
            <div className="mt-2 flex min-w-0 flex-wrap items-center gap-2">
              <span className="shrink-0 text-emerald-900 dark:text-emerald-100">
                Conversation ID
              </span>
              <code className="min-w-0 flex-1 rounded-md bg-white/55 px-2 py-1 font-mono text-[11px] break-all select-all dark:bg-black/15">
                {conversationId}
              </code>
              <button
                type="button"
                onClick={() => void copyConversationId()}
                aria-label="Copy conversation ID"
                className="inline-flex min-h-8 shrink-0 items-center gap-1.5 rounded-md border border-emerald-700/20 bg-white/55 px-2.5 font-medium transition-colors hover:bg-white/90 focus-visible:ring-2 focus-visible:ring-emerald-500/60 focus-visible:outline-none dark:border-emerald-300/20 dark:bg-black/15 dark:hover:bg-black/25"
              >
                {visibleCopyStatus === "copied" ? (
                  <Check aria-hidden="true" className="h-3.5 w-3.5" />
                ) : (
                  <Copy aria-hidden="true" className="h-3.5 w-3.5" />
                )}
                {visibleCopyStatus === "copied" ? "Copied" : "Copy"}
              </button>
              <span
                role="status"
                aria-live="polite"
                className={
                  visibleCopyStatus === "unavailable"
                    ? "w-full text-amber-800 dark:text-amber-200"
                    : "sr-only"
                }
              >
                {visibleCopyStatus === "copied"
                  ? "Conversation ID copied."
                  : visibleCopyStatus === "unavailable"
                    ? "Clipboard unavailable. Select the ID to copy it manually."
                    : ""}
              </span>
            </div>
          ) : (
            <p className="mt-2 text-emerald-900/75 dark:text-emerald-100/75">
              No conversation is selected.
            </p>
          )}
        </div>
      </div>
    </details>
  );
}
