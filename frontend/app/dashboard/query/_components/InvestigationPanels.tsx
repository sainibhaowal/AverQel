"use client";

import type { ReactNode } from "react";

type ComparisonDoc = {
  title: string;
  status: string;
  healthScore?: string;
  healthBand?: string;
  extraction?: string;
  runtime?: string;
  signals?: string;
  evidence: string[];
};

type CollectionDoc = {
  title: string;
  status?: string;
  health?: string;
  embedding?: string;
};

type EvidenceDoc = {
  title: string;
  status: string;
  evidence: string[];
};

type CollectionStat = {
  label: string;
  value: string;
};

type InvestigationPanelsResult = {
  remainingContent: string;
  panels: ReactNode[];
};

interface InvestigationPanelsProps {
  content: string;
}

export function renderInvestigationPanels({
  content,
}: InvestigationPanelsProps): InvestigationPanelsResult {
  const trimmed = content.trim();
  if (!trimmed) {
    return { remainingContent: "", panels: [] };
  }

  const comparison = parseComparisonAnswer(trimmed);
  if (comparison) {
    return {
      remainingContent: "",
      panels: [<ComparisonPanel key="comparison" {...comparison} />],
    };
  }

  const collectionSummary = parseCollectionSummary(trimmed);
  if (collectionSummary) {
    return {
      remainingContent: "",
      panels: [<CollectionSummaryPanel key="collection-summary" {...collectionSummary} />],
    };
  }

  const evidenceList = parseEvidenceMatches(trimmed);
  if (evidenceList) {
    return {
      remainingContent: "",
      panels: [<EvidenceCardsPanel key="evidence-cards" {...evidenceList} />],
    };
  }

  return { remainingContent: trimmed, panels: [] };
}

function ComparisonPanel(props: {
  intro: string;
  healthiest: string;
  weakest: string;
  docs: ComparisonDoc[];
}) {
  const { intro, healthiest, weakest, docs } = props;

  return (
    <section className="space-y-4">
      <div className="theme-panel border-glass-border/60 rounded-[1.55rem] border px-4 py-4 sm:px-5">
        <div className="flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-foreground/84 text-[14px] leading-7 sm:text-[14.5px]">{intro}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <MetaBadge label="Healthiest" value={healthiest} tone="good" />
            <MetaBadge label="At Risk" value={weakest} tone="warn" />
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        {docs.map((doc) => (
          <article
            key={doc.title}
            className="theme-panel border-glass-border/60 rounded-[1.5rem] border px-4 py-4 sm:px-5"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <h4 className="text-foreground truncate text-[15px] font-semibold tracking-[-0.02em]">
                  {doc.title}
                </h4>
                <div className="mt-2 flex flex-wrap gap-2">
                  <MetaBadge label="Status" value={doc.status} />
                  {doc.healthScore ? (
                    <MetaBadge
                      label="Health"
                      value={`${doc.healthScore}${doc.healthBand ? ` · ${doc.healthBand}` : ""}`}
                      tone={
                        doc.healthBand === "strong" || doc.healthBand === "healthy"
                          ? "good"
                          : doc.healthBand === "watch"
                            ? "neutral"
                            : "warn"
                      }
                    />
                  ) : null}
                </div>
              </div>
            </div>

            <div className="text-foreground/78 mt-4 space-y-3 text-[13.5px] leading-6">
              {doc.extraction ? <DetailRow label="Extraction" value={doc.extraction} /> : null}
              {doc.runtime ? <DetailRow label="Runtime" value={doc.runtime} /> : null}
              {doc.signals ? <DetailRow label="Signals" value={doc.signals} /> : null}
            </div>

            {doc.evidence.length > 0 ? (
              <div className="border-glass-border bg-foreground/[0.03] mt-4 space-y-3 rounded-2xl border px-4 py-4 dark:bg-white/[0.02]">
                <p className="text-primary/80 text-[10px] font-bold tracking-[0.25em] uppercase">
                  Reliability Evidence
                </p>
                <div className="space-y-2">
                  {doc.evidence.map((item, index) => (
                    <div
                      key={`${doc.title}-${index}`}
                      className="text-foreground/80 flex gap-3 text-[13.5px] leading-relaxed"
                    >
                      <span className="bg-primary/40 mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full" />
                      <p>{item}</p>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function CollectionSummaryPanel(props: {
  title: string;
  stats: CollectionStat[];
  docs: CollectionDoc[];
}) {
  const { title, stats, docs } = props;

  return (
    <section className="space-y-4">
      <div className="theme-panel border-glass-border/60 rounded-[1.55rem] border px-4 py-4 sm:px-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-primary/80 text-[10px] font-bold tracking-[0.25em] uppercase">
              Collection Summary
            </p>
            <h4 className="text-foreground mt-2 text-[18px] font-semibold tracking-[-0.03em]">
              {title}
            </h4>
          </div>
          <div className="flex flex-wrap gap-2">
            {stats.map((stat) => (
              <MetaBadge key={stat.label} label={stat.label} value={stat.value} />
            ))}
          </div>
        </div>
      </div>

      <div className="theme-panel border-glass-border/60 rounded-[1.5rem] border px-3 py-2 sm:px-4">
        <div className="divide-glass-border/45 divide-y">
          {docs.map((doc) => (
            <div
              key={doc.title}
              className="flex flex-wrap items-center justify-between gap-3 px-1 py-3"
            >
              <div className="min-w-0">
                <p className="text-foreground/92 truncate text-[14px] font-medium">{doc.title}</p>
                <div className="mt-1 flex flex-wrap gap-2">
                  {doc.status ? <MetaBadge label="Status" value={doc.status} compact /> : null}
                  {doc.health ? <MetaBadge label="Health" value={doc.health} compact /> : null}
                </div>
              </div>
              {doc.embedding ? (
                <p className="text-foreground/64 max-w-[24rem] text-right text-[12.5px] leading-5">
                  {doc.embedding}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function EvidenceCardsPanel(props: { title: string; docs: EvidenceDoc[] }) {
  const { title, docs } = props;

  return (
    <section className="space-y-4">
      <div className="theme-panel border-glass-border/60 rounded-[1.55rem] border px-4 py-4 sm:px-5">
        <h4 className="text-foreground text-[16px] font-semibold tracking-[-0.02em]">{title}</h4>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {docs.map((doc) => (
          <article
            key={doc.title}
            className="theme-panel border-glass-border/60 rounded-[1.5rem] border px-4 py-4 sm:px-5"
          >
            <div className="flex items-start justify-between gap-3">
              <h4 className="text-foreground truncate text-[15px] font-semibold tracking-[-0.02em]">
                {doc.title}
              </h4>
              <MetaBadge label="Status" value={doc.status} compact />
            </div>
            <div className="mt-4 space-y-2">
              {doc.evidence.map((item, index) => (
                <div
                  key={`${doc.title}-${index}`}
                  className="border-glass-border/50 bg-foreground/[0.02] text-foreground/76 rounded-[1.15rem] border px-3 py-3 text-[13px] leading-6 dark:bg-white/[0.02]"
                >
                  {item}
                </div>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function MetaBadge({
  label,
  value,
  tone = "neutral",
  compact = false,
}: {
  label: string;
  value: string;
  tone?: "neutral" | "good" | "warn";
  compact?: boolean;
}) {
  const toneClass =
    tone === "good"
      ? "!border-emerald-500/20 !bg-emerald-500/10 !text-emerald-700 dark:!text-emerald-300"
      : tone === "warn"
        ? "!border-accent/30 !bg-accent/10 !text-accent dark:!text-accent"
        : "!border-foreground/10 !bg-foreground/5 !text-foreground/60";

  return (
    <span
      className={`theme-pill ${toneClass} ${compact ? "px-2 py-0.5" : "px-3 py-1"} tracking-[0.2em] uppercase transition-all hover:scale-[1.02]`}
    >
      <span className="opacity-60">{label}</span>
      <span className="font-bold tracking-normal normal-case">{value}</span>
    </span>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[6rem_minmax(0,1fr)] sm:gap-3">
      <span className="text-primary/70 text-[10px] font-bold tracking-[0.25em] uppercase">
        {label}
      </span>
      <p className="text-foreground/90 text-[14px] leading-relaxed font-medium">{value}</p>
    </div>
  );
}

function parseComparisonAnswer(content: string) {
  if (!content.startsWith("Compared ")) {
    return null;
  }

  const lines = content.split("\n");
  if (lines.length < 4) {
    return null;
  }

  const intro = lines[0]?.trim() || "";
  const healthiest = lines[1]
    ?.replace(/^Healthiest overall:\s*/i, "")
    .replace(/\.$/, "")
    .trim();
  const weakest = lines[2]
    ?.replace(/^Most at risk:\s*/i, "")
    .replace(/\.$/, "")
    .trim();
  if (!healthiest || !weakest) {
    return null;
  }

  const docs: ComparisonDoc[] = [];
  let current: ComparisonDoc | null = null;

  for (const rawLine of lines.slice(3)) {
    const line = rawLine.trimEnd();
    if (!line.trim()) {
      continue;
    }
    if (line.startsWith("- ")) {
      if (current) {
        docs.push(current);
      }
      const body = line.slice(2).trim();
      const match = body.match(/^(.*?): status ([^,]+), health (\d+\/100) \(([^)]+)\)$/i);
      current = {
        title: match?.[1]?.trim() || body,
        status: match?.[2]?.trim() || "unknown",
        healthScore: match?.[3]?.trim(),
        healthBand: match?.[4]?.trim(),
        evidence: [],
      };
      continue;
    }

    if (!current) {
      continue;
    }

    const detail = line.trim();
    if (detail.startsWith("Extraction: ")) {
      current.extraction = detail.slice("Extraction: ".length).trim();
    } else if (detail.startsWith("Runtime: ")) {
      current.runtime = detail.slice("Runtime: ".length).trim();
    } else if (detail.startsWith("Signals: ")) {
      current.signals = detail.slice("Signals: ".length).trim();
    } else if (detail.startsWith("Evidence: ")) {
      current.evidence.push(detail.slice("Evidence: ".length).trim());
    }
  }

  if (current) {
    docs.push(current);
  }

  // Allow partial comparison panels during streaming as soon as the first
  // document card is recognizable. The second card can arrive in later deltas.
  if (docs.length < 1) {
    return null;
  }

  return { intro, healthiest, weakest, docs };
}

function parseCollectionSummary(content: string) {
  if (!content.startsWith('Collection summary for "')) {
    return null;
  }

  const lines = content.split("\n");
  const title = lines[0]
    ?.replace(/^Collection summary for /, "")
    .replace(/:$/, "")
    .trim();
  if (!title) {
    return null;
  }

  const stats: CollectionStat[] = [];
  const docs: CollectionDoc[] = [];
  let inDocs = false;

  for (const rawLine of lines.slice(1)) {
    const line = rawLine.trim();
    if (!line) {
      continue;
    }
    if (line === "Documents:") {
      inDocs = true;
      continue;
    }
    if (!inDocs && line.startsWith("- ")) {
      const statMatch = line.slice(2).split(":");
      if (statMatch.length >= 2) {
        stats.push({
          label: statMatch[0]!.trim(),
          value: statMatch.slice(1).join(":").trim(),
        });
      }
      continue;
    }
    if (inDocs && line.startsWith("- ")) {
      const body = line.slice(2).trim();
      const [titlePart, restPart = ""] = body.split(": ", 2);
      const parts = restPart.split(", ").map((part) => part.trim());
      docs.push({
        title: titlePart.trim(),
        status: parts[0],
        health: parts[1]?.replace(/^health\s+/i, ""),
        embedding: parts[2],
      });
    }
  }

  if (docs.length === 0) {
    return null;
  }

  return { title, stats, docs };
}

function parseEvidenceMatches(content: string) {
  if (!content.startsWith("Documents matching ")) {
    return null;
  }

  const lines = content.split("\n");
  const title = lines[0]?.trim() || "";
  const docs: EvidenceDoc[] = [];
  let current: EvidenceDoc | null = null;

  for (const rawLine of lines.slice(1)) {
    const line = rawLine.trimEnd();
    if (!line.trim()) {
      continue;
    }
    if (line.startsWith("- ")) {
      if (current) {
        docs.push(current);
      }
      const body = line.slice(2).trim();
      const match = body.match(/^(.*)\(([^)]+)\)$/);
      current = {
        title: match?.[1]?.trim() || body,
        status: match?.[2]?.trim() || "unknown",
        evidence: [],
      };
      continue;
    }
    if (current && line.trim().startsWith("Evidence")) {
      current.evidence.push(line.trim());
    }
  }

  if (current) {
    docs.push(current);
  }

  if (docs.length === 0) {
    return null;
  }

  return { title, docs };
}
