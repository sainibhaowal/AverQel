"use client";

import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  BookmarkPlus,
  Pencil,
  Save,
  X,
} from "lucide-react";
import { useState } from "react";

import type { StreamInfographicBlock } from "../_lib/stream-protocol";

import VisualIcon, { visualIconBadgeClasses } from "./VisualIcon";

const layoutLabels: Record<StreamInfographicBlock["layout"], string> = {
  steps: "Process",
  timeline: "Timeline",
  comparison: "Comparison",
  feature_grid: "Overview",
  stats: "Key figures",
};

const flowDirectionLabels: Record<NonNullable<StreamInfographicBlock["direction"]>, string> = {
  LR: "Left to right",
  RL: "Right to left",
  TD: "Top to bottom",
  DT: "Bottom to top",
};

export default function InfographicBlock({
  block,
  onChange,
  onSaveArtifact,
}: {
  block: StreamInfographicBlock;
  onChange?: (
    block: StreamInfographicBlock,
  ) => void | boolean | StreamInfographicBlock | Promise<void | boolean | StreamInfographicBlock>;
  onSaveArtifact?: (block: StreamInfographicBlock) => void | boolean | Promise<void | boolean>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => JSON.stringify(block, null, 2));
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const flowDirection = block.direction ?? "LR";
  const isHorizontalFlow = flowDirection === "LR" || flowDirection === "RL";

  const parseDraft = () => {
    const parsed = JSON.parse(draft) as StreamInfographicBlock;
    if (
      !parsed ||
      parsed.id !== block.id ||
      parsed.type !== "infographic" ||
      !layoutLabels[parsed.layout] ||
      !Array.isArray(parsed.items) ||
      parsed.items.length < 2 ||
      parsed.items.length > 8
    ) {
      throw new Error("Check the infographic layout and its 2–8 items.");
    }
    if (
      parsed.layout === "timeline" &&
      parsed.items.some((item) => !item.date?.trim() || item.date.length > 300)
    ) {
      throw new Error("Each timeline date must contain 1–300 characters.");
    }
    if (parsed.layout === "stats" && parsed.items.some((item) => item.value == null)) {
      throw new Error("Each statistics item needs a value.");
    }
    if (parsed.direction != null && !["LR", "RL", "TD", "DT"].includes(parsed.direction)) {
      throw new Error("Choose LR, RL, TD, or DT for the process direction.");
    }
    return {
      ...parsed,
      ...(parsed.layout === "steps" ? { direction: parsed.direction ?? "LR" } : {}),
      revision: (block.revision ?? 0) + 1,
    };
  };

  const saveDraft = async () => {
    if (saving) return;
    setSaving(true);
    try {
      const parsed = parseDraft();
      setError(null);
      setStatus(null);
      const saved = await onChange?.(parsed);
      if (saved === false) {
        setError(
          "The save did not complete. Your draft is still open; review any warning and try again.",
        );
        return;
      }
      const persisted =
        saved && typeof saved === "object" && saved.type === "infographic" ? saved : parsed;
      setDraft(JSON.stringify(persisted, null, 2));
      setStatus("Changes saved.");
      setEditing(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The infographic JSON is invalid.");
    } finally {
      setSaving(false);
    }
  };

  const saveArtifact = async () => {
    if (saving) return;
    setSaving(true);
    try {
      setError(null);
      setStatus(null);
      let artifact = block;
      if (editing) {
        artifact = parseDraft();
        const committed = await onChange?.(artifact);
        if (committed === false) {
          setError("Save the infographic changes before saving it to the Library.");
          return;
        }
        if (committed && typeof committed === "object" && committed.type === "infographic") {
          artifact = committed;
        }
      }
      const saved = await onSaveArtifact?.(artifact);
      if (saved === false) throw new Error("The visual artifact could not be saved.");
      if (editing) {
        setDraft(JSON.stringify(artifact, null, 2));
        setEditing(false);
      }
      setStatus("Saved to Library.");
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "The visual artifact could not be saved.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <section
      className="group relative my-4 overflow-hidden rounded-[1.5rem] border border-glass-border bg-surface-0 p-5 shadow-sm sm:p-7 dark:bg-surface-1"
      aria-label={`${layoutLabels[block.layout]} infographic`}
    >
      <header className="relative mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2 text-[10px] font-semibold tracking-[0.2em] text-muted-foreground uppercase">
            <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground" />
            {layoutLabels[block.layout]}
            {block.layout === "steps" ? (
              <span
                className={`rounded-lg border border-glass-border bg-surface-1 px-2 py-1 text-[9px] tracking-[0.12em] text-foreground dark:bg-surface-2 ${
                  isHorizontalFlow ? "hidden sm:inline-flex" : ""
                }`}
              >
                {flowDirectionLabels[flowDirection]}
              </span>
            ) : null}
          </div>
          <h3 className="text-foreground m-0 text-xl font-semibold tracking-tight sm:text-2xl">
            {block.title}
          </h3>
          {block.subtitle ? (
            <p className="text-foreground/80 dark:text-foreground/65 mt-2 mb-0 max-w-3xl text-sm leading-6">
              {block.subtitle}
            </p>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1 opacity-70 transition group-focus-within:opacity-100 group-hover:opacity-100">
          {onChange ? (
            editing ? (
              <>
                <button
                  type="button"
                  onClick={() => void saveDraft()}
                  disabled={saving}
                  className="theme-chip inline-flex h-8 items-center gap-1 rounded-lg px-2.5 text-[11px]"
                  aria-label="Save infographic"
                >
                  <Save size={13} /> {saving ? "Saving…" : "Save changes"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setDraft(JSON.stringify(block, null, 2));
                    setEditing(false);
                    setError(null);
                    setStatus(null);
                  }}
                  className="theme-chip inline-flex h-8 w-8 items-center justify-center rounded-lg"
                  aria-label="Cancel infographic edit"
                >
                  <X size={14} />
                </button>
              </>
            ) : (
              <button
                type="button"
                onClick={() => {
                  setDraft(JSON.stringify(block, null, 2));
                  setEditing(true);
                  setError(null);
                  setStatus(null);
                }}
                className="theme-chip inline-flex h-8 items-center gap-1 rounded-lg px-2.5 text-[11px]"
                aria-label="Edit infographic"
              >
                <Pencil size={13} /> Edit
              </button>
            )
          ) : null}
          {onSaveArtifact ? (
            <button
              type="button"
              onClick={() => void saveArtifact()}
              disabled={saving}
              className="theme-chip inline-flex h-8 items-center gap-1 rounded-lg px-2.5 text-[11px]"
              aria-label="Save infographic to Library"
            >
              <BookmarkPlus size={13} /> {saving ? "Saving…" : "Save to Library"}
            </button>
          ) : null}
        </div>
      </header>

      {editing ? (
        <textarea
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value);
            setError(null);
            setStatus(null);
          }}
          aria-label="Edit infographic fields as JSON"
          className="border-glass-border bg-background/70 text-foreground relative min-h-64 w-full rounded-xl border p-3 font-mono text-xs leading-5"
        />
      ) : (
        <div className="relative">
          {block.layout === "steps" ? (
            <ol
              aria-label={`Process steps, ${flowDirectionLabels[flowDirection].toLowerCase()}`}
              data-flow-direction={flowDirection}
              dir={flowDirection === "RL" ? "rtl" : "ltr"}
              className={`m-0 list-none gap-x-5 gap-y-6 p-0 ${
                isHorizontalFlow
                  ? "grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4"
                  : flowDirection === "DT"
                    ? "flex flex-col-reverse gap-6"
                    : "flex flex-col gap-6"
              }`}
            >
              {block.items.map((item, index) => {
                const isSmallRowEnd = (index + 1) % 2 === 0;
                const isWideRowEnd = (index + 1) % 4 === 0;
                const HorizontalArrow = flowDirection === "RL" ? ArrowLeft : ArrowRight;
                const NextMobileArrow =
                  isHorizontalFlow || flowDirection === "TD" ? ArrowDown : ArrowUp;
                const rowArrowVisibility = isSmallRowEnd
                  ? isWideRowEnd
                    ? "sm:hidden xl:hidden"
                    : "sm:hidden xl:block"
                  : isWideRowEnd
                    ? "sm:block xl:hidden"
                    : "sm:block xl:block";

                return (
                  <li
                    key={`${item.title}-${index}`}
                    dir="ltr"
                    className={`group relative flex min-w-0 flex-col rounded-[1.3rem] border border-glass-border bg-surface-0 p-4 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:border-foreground/30 hover:shadow-md motion-reduce:transform-none motion-reduce:transition-none sm:p-5 dark:bg-surface-1 ${
                      isHorizontalFlow
                        ? ""
                        : "md:grid md:grid-cols-[minmax(14rem,0.8fr)_minmax(0,1.2fr)] md:items-center md:gap-x-8"
                    }`}
                  >
                    <div
                      className={`flex min-h-[4.5rem] min-w-0 items-center gap-3 ${
                        isHorizontalFlow || !item.description ? "" : "md:col-start-1"
                      }`}
                    >
                      <div
                        className={`flex size-10 shrink-0 items-center justify-center rounded-xl border shadow-sm ${visualIconBadgeClasses}`}
                      >
                        {item.icon ? (
                          <VisualIcon name={item.icon} />
                        ) : (
                          <span className="font-mono text-xs font-semibold">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                        )}
                      </div>
                      <div className="min-w-0">
                        <div className="mb-1 text-[9px] font-semibold tracking-[0.16em] text-muted-foreground uppercase">
                          Step {String(index + 1).padStart(2, "0")}
                        </div>
                        <h4 className="text-foreground m-0 text-sm leading-snug font-semibold tracking-tight [overflow-wrap:anywhere] sm:text-base">
                          {item.title}
                        </h4>
                      </div>
                    </div>
                    {item.description ? (
                      <p
                        className={`text-foreground/80 dark:text-foreground/70 mt-3 mb-0 text-sm leading-6 [text-wrap:pretty] ${
                          isHorizontalFlow
                            ? ""
                            : "md:col-start-2 md:row-start-1 md:mt-0 md:border-l md:border-glass-border md:py-1 md:pl-8"
                        }`}
                      >
                        {item.description}
                      </p>
                    ) : null}
                    {index < block.items.length - 1 ? (
                      isHorizontalFlow ? (
                        <>
                          <NextMobileArrow
                            size={15}
                            className="absolute -bottom-5 left-1/2 z-10 -translate-x-1/2 text-muted-foreground sm:hidden"
                            data-flow-connector="mobile"
                            aria-hidden="true"
                          />
                          <HorizontalArrow
                            size={15}
                            className={`absolute top-1/2 z-10 hidden -translate-y-1/2 text-muted-foreground ${
                              flowDirection === "RL" ? "-left-3" : "-right-3"
                            } ${rowArrowVisibility}`}
                            data-flow-connector="row"
                            aria-hidden="true"
                          />
                        </>
                      ) : (
                        <NextMobileArrow
                          size={15}
                          className={`absolute left-1/2 z-10 -translate-x-1/2 text-muted-foreground ${
                            flowDirection === "DT" ? "-top-5" : "-bottom-5"
                          }`}
                          data-flow-connector="column"
                          aria-hidden="true"
                        />
                      )
                    ) : null}
                  </li>
                );
              })}
            </ol>
          ) : null}

          {block.layout === "timeline" ? (
            <ol className="m-0 grid list-none gap-3 border-l border-glass-border p-0 pl-5 sm:grid-cols-2 sm:border-0 sm:pl-0 xl:grid-cols-4">
              {block.items.map((item, index) => (
                <li
                  key={`${item.title}-${index}`}
                  className="relative rounded-2xl border border-glass-border bg-surface-0 p-4 sm:pt-5 dark:bg-surface-1"
                >
                  <span className="absolute top-5 -left-[1.64rem] h-3 w-3 rounded-full border-2 border-glass-border bg-surface-0 sm:top-[-0.35rem] sm:left-5 dark:bg-surface-1" />
                  <div className="mb-3 text-[10px] font-semibold tracking-[0.16em] [overflow-wrap:anywhere] break-words text-muted-foreground uppercase">
                    {item.date}
                  </div>
                  <h4 className="text-foreground m-0 text-sm font-semibold">{item.title}</h4>
                  {item.description ? (
                    <p className="text-foreground/80 dark:text-foreground/65 mt-2 mb-0 text-xs leading-5">
                      {item.description}
                    </p>
                  ) : null}
                </li>
              ))}
            </ol>
          ) : null}

          {block.layout === "comparison" ? (
            <div className="grid items-stretch gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {block.items.map((item, index) => {
                const wideFinalCard =
                  block.items.length > 2 &&
                  block.items.length % 2 === 1 &&
                  index === block.items.length - 1 &&
                  Boolean(item.description?.trim());

                return (
                  <article
                    key={`${item.title}-${index}`}
                    className={`group relative flex h-full min-w-0 flex-col overflow-hidden rounded-[1.4rem] border border-glass-border bg-surface-0 p-5 shadow-sm transition duration-200 hover:-translate-y-0.5 hover:border-foreground/30 hover:shadow-md motion-reduce:transform-none motion-reduce:transition-none sm:p-6 dark:bg-surface-1 ${
                      wideFinalCard
                        ? "sm:col-span-2 sm:grid sm:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] sm:items-center sm:gap-x-8 xl:col-span-1 xl:flex xl:flex-col xl:items-stretch xl:gap-x-0"
                        : ""
                    }`}
                  >
                    <div className={wideFinalCard ? "sm:col-start-1" : ""}>
                      <div className="flex min-w-0 items-center gap-3">
                        <div
                          className={`flex size-11 shrink-0 items-center justify-center rounded-2xl border shadow-sm ${visualIconBadgeClasses}`}
                        >
                          {item.icon ? (
                            <VisualIcon name={item.icon} />
                          ) : (
                            <span className="text-sm font-semibold tracking-wide">
                              {String.fromCharCode(65 + index)}
                            </span>
                          )}
                        </div>
                        <h4 className="text-foreground m-0 min-w-0 text-base font-semibold tracking-tight [overflow-wrap:anywhere] sm:text-lg">
                          {item.title}
                        </h4>
                      </div>
                      {item.value != null ? (
                        <p className="mt-5 mb-0 rounded-xl border border-glass-border border-l-[3px] bg-surface-1 px-4 py-3 text-left text-[15px] leading-6 font-semibold [text-wrap:pretty] [overflow-wrap:anywhere] text-foreground sm:text-base dark:bg-surface-2">
                          {item.value}
                        </p>
                      ) : null}
                    </div>
                    {item.description ? (
                      <p
                        className={`text-foreground/80 dark:text-foreground/70 mt-4 mb-0 max-w-[68ch] text-left text-sm leading-6 [text-wrap:pretty] ${
                          wideFinalCard
                            ? "sm:col-start-2 sm:mt-0 sm:flex sm:items-center sm:self-stretch sm:border-l sm:border-glass-border sm:pl-6 xl:col-start-auto xl:mt-4 xl:block xl:self-auto xl:border-l-0 xl:pl-0"
                            : ""
                        }`}
                      >
                        {item.description}
                      </p>
                    ) : null}
                  </article>
                );
              })}
            </div>
          ) : null}

          {block.layout === "feature_grid" ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {block.items.map((item, index) => (
                <article
                  key={`${item.title}-${index}`}
                  className="overflow-hidden rounded-2xl border border-glass-border bg-surface-0 dark:bg-surface-1"
                >
                  {safeExternalHref(item.image_url) ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={safeExternalHref(item.image_url)}
                      alt={item.title}
                      loading="lazy"
                      className="h-36 w-full object-cover"
                      onError={(event) => {
                        event.currentTarget.style.display = "none";
                      }}
                    />
                  ) : null}
                  <div className="p-4">
                    <div
                      className={`mb-3 flex h-9 w-9 items-center justify-center rounded-xl border shadow-sm ${visualIconBadgeClasses}`}
                    >
                      <VisualIcon name={item.icon} />
                    </div>
                    <h4 className="text-foreground m-0 text-sm font-semibold">{item.title}</h4>
                    {item.description ? (
                      <p className="text-foreground/80 dark:text-foreground/65 mt-2 mb-0 text-xs leading-5">
                        {item.description}
                      </p>
                    ) : null}
                  </div>
                </article>
              ))}
            </div>
          ) : null}

          {block.layout === "stats" ? (
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {block.items.map((item, index) => (
                <article
                  key={`${item.title}-${index}`}
                  className="rounded-2xl border border-glass-border bg-surface-0 p-4 dark:bg-surface-1"
                >
                  <div className="mb-3 flex items-center gap-2 text-muted-foreground">
                    <VisualIcon name={item.icon} size={16} />
                    <h4 className="text-foreground m-0 text-xs font-semibold">{item.title}</h4>
                  </div>
                  <div className="text-foreground text-3xl font-semibold tracking-tight tabular-nums">
                    {item.value}
                  </div>
                  {item.description ? (
                    <p className="text-foreground/80 dark:text-foreground/65 mt-2 mb-0 text-xs leading-5">
                      {item.description}
                    </p>
                  ) : null}
                </article>
              ))}
            </div>
          ) : null}
        </div>
      )}

      {block.note ? (
        <p className="text-foreground/80 dark:text-foreground/65 relative mt-5 mb-0 border-t border-glass-border pt-4 text-xs leading-5">
          {block.note}
        </p>
      ) : null}
      {block.sources?.length ? (
        <div className="relative mt-4 flex flex-wrap gap-x-4 gap-y-2 border-t border-glass-border pt-4 text-[11px]">
          {block.sources.map((source, index) => {
            const href = safeExternalHref(source.url);
            return href ? (
              <a
                key={`${source.url}-${index}`}
                href={href}
                target="_blank"
                rel="noreferrer noopener"
                className="text-primary underline decoration-primary/40 underline-offset-4 hover:text-primary/80"
              >
                {source.title}
              </a>
            ) : null;
          })}
        </div>
      ) : null}
      {status ? (
        <p className="relative mt-3 text-xs text-emerald-700 dark:text-emerald-300" role="status">
          {status}
        </p>
      ) : null}
      {error ? (
        <p className="relative mt-3 text-xs text-rose-300" role="alert">
          {error}
        </p>
      ) : null}
    </section>
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
