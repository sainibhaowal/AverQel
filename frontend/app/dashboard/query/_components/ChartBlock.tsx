import { AnimatePresence, motion } from "framer-motion";
import { memo, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import {
  Activity,
  BarChart3,
  CheckCircle2,
  Download,
  FileJson,
  LineChart as LineChartIcon,
  Pencil,
  Plus,
  PieChart as PieChartIcon,
  RotateCcw,
  ScanSearch,
  ScatterChart as ScatterChartIcon,
  ShieldCheck,
} from "lucide-react";
import RoundedSelect from "@/app/components/ui/RoundedSelect";

import type {
  StreamChartBlock,
  StreamChartPoint,
  StreamChartSeriesGroup,
} from "../_lib/stream-protocol";

interface ChartBlockProps {
  block: StreamChartBlock;
  onChange?: (block: StreamChartBlock) => void | boolean | Promise<void | boolean>;
  onSaveArtifact?: (block: StreamChartBlock) => void | Promise<void>;
}

type HoverPoint = {
  label: string;
  value: number;
  color: string;
  x: number;
  y: number;
  z?: number;
};

const CHART_COLORS = [
  "hsl(243, 75%, 59%)",
  "hsl(270, 95%, 60%)",
  "hsl(210, 100%, 50%)",
  "hsl(180, 100%, 40%)",
  "hsl(330, 100%, 60%)",
  "hsl(20, 100%, 50%)",
];

const CHART_SOURCE_METADATA_KEYS = new Set([
  "assets",
  "block_id",
  "confidence",
  "fields",
  "history",
  "is_streaming",
  "parser_source",
  "raw_payload",
  "revision",
  "schema_version",
  "source_markdown",
  "source_mermaid",
  "type",
  "undo",
  "visual_model",
]);

function withSynchronizedChartSource(block: StreamChartBlock): StreamChartBlock {
  const source = JSON.stringify(
    Object.fromEntries(
      Object.entries(block).filter(([key]) => !CHART_SOURCE_METADATA_KEYS.has(key)),
    ),
  );
  return { ...block, raw_payload: source, source_markdown: source };
}

// Re-defining the main component with Tooltip state
const ChartBlock = memo(function ChartBlock({ block, onChange, onSaveArtifact }: ChartBlockProps) {
  const chartAreaRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const hoverLeaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeHoverKey = useRef<string | null>(null);
  const [tooltipPosition, setTooltipPosition] = useState<{ left: number; top: number } | null>(
    null,
  );
  const [isEditing, setIsEditing] = useState(false);
  const [draftState, setDraftState] = useState<{
    blockId: string;
    series: StreamChartPoint[];
    equation: string | null;
  }>({ blockId: block.id, series: block.series, equation: block.equation ?? null });
  const [draftGroups, setDraftGroups] = useState<StreamChartSeriesGroup[]>(
    () => block.series_groups?.map((group) => ({ ...group, points: [...group.points] })) ?? [],
  );
  const [equationInput, setEquationInput] = useState(block.equation ?? "");
  const [equationError, setEquationError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const [artifactStatus, setArtifactStatus] = useState<string | null>(null);
  const [savingArtifact, setSavingArtifact] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const draftSeries = draftState.blockId === block.id ? draftState.series : block.series;
  const activeGroups =
    draftState.blockId === block.id
      ? draftGroups
      : (block.series_groups?.map((group) => ({ ...group, points: [...group.points] })) ?? []);
  const editingCurrentBlock = isEditing && draftState.blockId === block.id;

  const activeEquation =
    draftState.blockId === block.id ? draftState.equation : (block.equation ?? null);
  const activeBlock = editingCurrentBlock
    ? withSynchronizedChartSource({
        ...block,
        series: draftSeries,
        series_groups: activeGroups.length > 0 ? activeGroups : block.series_groups,
        equation: activeEquation,
      })
    : block;
  const plottablePointCount =
    normalizePoints(activeBlock).length ||
    (activeBlock.series_groups ?? []).reduce((count, group) => count + group.points.length, 0);
  const canRenderVisual = plottablePointCount > 1;
  const [manualView, setManualView] = useState<"chart" | "payload" | null>(null);
  const [activePoint, setActivePoint] = useState<HoverPoint | null>(null);
  const handlePointHover = useCallback((point: HoverPoint | null) => {
    if (hoverLeaveTimer.current !== null) {
      clearTimeout(hoverLeaveTimer.current);
      hoverLeaveTimer.current = null;
    }

    if (point) {
      const pointKey = `${point.label}:${point.value}:${point.x}:${point.y}:${point.z ?? ""}`;
      if (activeHoverKey.current === pointKey) return;
      activeHoverKey.current = pointKey;
      setActivePoint(point);
      return;
    }

    hoverLeaveTimer.current = setTimeout(() => {
      hoverLeaveTimer.current = null;
      activeHoverKey.current = null;
      setActivePoint(null);
      setTooltipPosition(null);
    }, 80);
  }, []);

  useEffect(
    () => () => {
      if (hoverLeaveTimer.current !== null) clearTimeout(hoverLeaveTimer.current);
    },
    [],
  );

  useLayoutEffect(() => {
    const boundary = chartAreaRef.current;
    const tooltip = tooltipRef.current;
    if (!activePoint || !boundary || !tooltip) return;

    const updatePosition = () => {
      const boundaryRect = boundary.getBoundingClientRect();
      const tooltipRect = tooltip.getBoundingClientRect();
      const margin = 8;
      const maxLeft = Math.max(margin, boundaryRect.width - tooltipRect.width - margin);
      const left = Math.max(margin, Math.min(activePoint.x - tooltipRect.width / 2, maxLeft));
      const topLimit = Math.max(margin, boundaryRect.height - tooltipRect.height - margin);
      const above = activePoint.y - tooltipRect.height - 12;
      const below = activePoint.y + 12;
      const preferredTop = above >= margin ? above : below;
      const top = Math.max(margin, Math.min(preferredTop, topLimit));

      setTooltipPosition((current) =>
        current?.left === left && current.top === top ? current : { left, top },
      );
    };

    updatePosition();
    window.addEventListener("resize", updatePosition);
    const resizeObserver =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(updatePosition);
    resizeObserver?.observe(boundary);
    resizeObserver?.observe(tooltip);

    return () => {
      window.removeEventListener("resize", updatePosition);
      resizeObserver?.disconnect();
    };
  }, [activePoint]);
  const icon = getChartIcon(block.chart_type);
  const chartTitle = block.title?.trim() || "Chart Data";
  const hasPayload = typeof block.raw_payload === "string" && block.raw_payload.trim().length > 0;
  const confidenceLabel =
    typeof block.confidence === "number" && block.confidence >= 0.9 ? "High fidelity" : "Heuristic";
  const view = resolveChartView({
    canRenderVisual,
    hasPayload,
    isStreaming: Boolean(block.is_streaming),
    manualView,
  });

  const downloadPayload = () => {
    const payload = JSON.stringify(
      {
        title: chartTitle,
        chart_type: activeBlock.chart_type,
        series: activeBlock.series,
        series_groups: activeBlock.series_groups,
        annotations: activeBlock.annotations,
        legend: activeBlock.legend,
        secondary_y_label: activeBlock.secondary_y_label,
        x_key: activeBlock.x_key,
        y_key: activeBlock.y_key,
        z_key: activeBlock.z_key,
        equation: activeBlock.equation,
      },
      null,
      2,
    );
    const url = URL.createObjectURL(new Blob([payload], { type: "application/json" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${slugify(chartTitle) || "chart"}.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const updatePoint = (index: number, key: "label" | "value", value: string) => {
    setDraftState((current) => ({
      blockId: block.id,
      series: (current.blockId === block.id ? current.series : block.series).map(
        (point, pointIndex) =>
          pointIndex === index
            ? {
                ...point,
                [key]: key === "value" ? (value === "" ? 0 : Number(value)) : value,
              }
            : point,
      ),
      equation: current.blockId === block.id ? current.equation : (block.equation ?? null),
    }));
  };

  const resetDraft = () => {
    setDraftState({ blockId: block.id, series: block.series, equation: block.equation ?? null });
    setDraftGroups(
      block.series_groups?.map((group) => ({ ...group, points: [...group.points] })) ?? [],
    );
    setEquationInput(block.equation ?? "");
    setEquationError(null);
    setIsEditing(false);
  };

  const toggleEditing = () => {
    if (!isEditing || draftState.blockId !== block.id) {
      setDraftState({ blockId: block.id, series: block.series, equation: block.equation ?? null });
      setDraftGroups(
        block.series_groups?.map((group) => ({ ...group, points: [...group.points] })) ?? [],
      );
      setEquationInput(block.equation ?? "");
      setEquationError(null);
    }
    setIsEditing((current) => !current);
  };

  const commitEditing = async () => {
    if (editingCurrentBlock) {
      const nextBlock = withSynchronizedChartSource({
        ...block,
        series: draftSeries,
        series_groups: activeGroups.length > 0 ? activeGroups : block.series_groups,
        equation: activeEquation,
        revision: (block.revision ?? 0) + 1,
      });
      setSaveError(null);
      setIsSaving(true);
      try {
        const saved = await onChange?.(nextBlock);
        if (saved === false) {
          setSaveError("Chart changes could not be saved. Try again.");
          return;
        }
      } catch {
        setSaveError("Chart changes could not be saved. Try again.");
        return;
      } finally {
        setIsSaving(false);
      }
    }
    setManualView("chart");
    setIsEditing(false);
  };

  const saveArtifact = async () => {
    if (!onSaveArtifact || savingArtifact) return;
    setArtifactError(null);
    setArtifactStatus(null);
    setSavingArtifact(true);
    try {
      await onSaveArtifact(withSynchronizedChartSource(activeBlock));
      setArtifactStatus("Saved to Library.");
    } catch (caught) {
      setArtifactError(
        caught instanceof Error ? caught.message : "The chart could not be saved to Library.",
      );
    } finally {
      setSavingArtifact(false);
    }
  };

  return (
    <section className="theme-panel relative w-full min-w-0 overflow-hidden rounded-[1.8rem] shadow-[0_24px_70px_-44px_rgba(8,47,73,0.16)] dark:shadow-[0_24px_70px_-44px_rgba(8,47,73,0.82)]">
      <div className="border-b border-black/5 px-5 py-4 sm:px-6 dark:border-white/8">
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <div className="bg-primary/10 text-primary border-primary/15 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border">
                {icon}
              </div>
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="visual-chart-title text-foreground m-0 text-[15px] leading-5 font-semibold tracking-[-0.015em]">
                    {chartTitle}
                  </h4>
                  <span className="theme-accent-pill rounded-lg px-2.5 py-1 text-[10px] font-semibold tracking-[0.16em] uppercase">
                    {block.chart_type}
                  </span>
                  {block.is_streaming ? (
                    <span className="rounded-lg border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-[10px] font-semibold tracking-[0.16em] text-amber-700 uppercase dark:text-amber-200">
                      live
                    </span>
                  ) : null}
                </div>
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                onClick={downloadPayload}
                className="visual-block-action inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium"
                aria-label="Download chart data"
                title="Download chart data"
              >
                <Download className="h-3.5 w-3.5" /> Data
              </button>
              {onSaveArtifact ? (
                <button
                  type="button"
                  onClick={() => void saveArtifact()}
                  disabled={savingArtifact}
                  aria-busy={savingArtifact}
                  className="visual-block-action inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium disabled:opacity-50"
                  aria-label="Save chart artifact"
                >
                  {savingArtifact ? "Saving…" : artifactStatus ? "Saved" : "Save artifact"}
                </button>
              ) : null}
              {!block.is_streaming ? (
                <button
                  type="button"
                  onClick={() => {
                    setArtifactStatus(null);
                    if (editingCurrentBlock) void commitEditing();
                    else toggleEditing();
                  }}
                  disabled={isSaving}
                  aria-busy={isSaving}
                  className={`visual-block-action inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] font-medium ${editingCurrentBlock ? "visual-block-action--active" : ""}`}
                >
                  <Pencil className="h-3.5 w-3.5" />
                  {editingCurrentBlock ? (isSaving ? "Saving…" : "Done") : "Edit data"}
                </button>
              ) : null}
              {hasPayload ? (
                <div className="visual-block-action-group">
                  <button
                    type="button"
                    onClick={() => setManualView("chart")}
                    disabled={!canRenderVisual}
                    className={`visual-block-action-segment rounded-lg px-3 py-1.5 text-[11px] font-medium transition ${
                      view === "chart"
                        ? "visual-block-action--active shadow-sm"
                        : "hover:text-foreground"
                    }`}
                  >
                    Visual
                  </button>
                  <button
                    type="button"
                    onClick={() => setManualView("payload")}
                    className={`visual-block-action-segment rounded-lg px-3 py-1.5 text-[11px] font-medium transition ${
                      view === "payload"
                        ? "visual-block-action--active shadow-sm"
                        : "hover:text-foreground"
                    }`}
                  >
                    Payload
                  </button>
                </div>
              ) : null}
            </div>
          </div>
          {saveError ? (
            <p
              className="mt-2 text-right text-[11px] text-rose-600 dark:text-rose-300"
              role="alert"
            >
              {saveError}
            </p>
          ) : null}
          {artifactError ? (
            <p
              className="mt-2 text-right text-[11px] text-rose-600 dark:text-rose-300"
              role="alert"
            >
              {artifactError}
            </p>
          ) : null}
          {artifactStatus ? (
            <p
              className="mt-2 text-right text-[11px] text-emerald-700 dark:text-emerald-300"
              role="status"
              aria-live="polite"
            >
              {artifactStatus}
            </p>
          ) : null}
          <div className="text-foreground/60 flex flex-wrap items-center gap-3 text-xs sm:ml-[3.25rem]">
            <span className="inline-flex items-center gap-1.5">
              <CheckCircle2 className="text-primary h-3.5 w-3.5" />
              {confidenceLabel}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Activity className="h-3.5 w-3.5" />
              {block.series.length} points
            </span>
            {block.parser_source ? (
              <span className="inline-flex items-center gap-1.5 capitalize">
                <ScanSearch className="h-3.5 w-3.5" />
                {block.parser_source}
              </span>
            ) : null}
          </div>
        </div>
      </div>

      <div className="min-w-0 px-4 py-4 sm:px-6">
        {editingCurrentBlock ? (
          <div className="bg-background/55 mb-5 rounded-[1.3rem] border border-black/5 p-4 dark:border-white/8">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-foreground/65 text-xs font-semibold tracking-[0.14em] uppercase">
                Editable data
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={resetDraft}
                  className="visual-block-action inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px]"
                >
                  <RotateCcw className="h-3 w-3" /> Reset
                </button>
                <button
                  type="button"
                  onClick={() =>
                    setDraftState((current) => {
                      const series = current.blockId === block.id ? current.series : block.series;
                      return {
                        blockId: block.id,
                        series: [...series, { label: `Point ${series.length + 1}`, value: 0 }],
                        equation:
                          current.blockId === block.id
                            ? current.equation
                            : (block.equation ?? null),
                      };
                    })
                  }
                  className="visual-block-action inline-flex items-center gap-1 rounded-lg px-2.5 py-1 text-[11px]"
                >
                  <Plus className="h-3 w-3" /> Add point
                </button>
              </div>
            </div>
            {activeGroups.length > 0 ? (
              <div className="mb-4 space-y-3">
                <div className="text-foreground/55 text-[10px] font-semibold tracking-[0.12em] uppercase">
                  Named series
                </div>
                {activeGroups.map((group, groupIndex) => (
                  <div
                    key={`${block.id}-group-${group.name}-${groupIndex}`}
                    className="border-glass-border bg-background/45 rounded-xl border p-3"
                  >
                    <div className="mb-2 grid gap-2 sm:grid-cols-[minmax(0,1fr)_7rem_auto_auto]">
                      <input
                        aria-label={`Series ${groupIndex + 1} name`}
                        value={group.name}
                        onChange={(event) =>
                          setDraftGroups((current) =>
                            current.map((item, index) =>
                              index === groupIndex ? { ...item, name: event.target.value } : item,
                            ),
                          )
                        }
                        className="border-glass-border bg-background/70 text-foreground min-w-0 rounded-lg border px-2.5 py-2 text-xs outline-none"
                      />
                      <RoundedSelect
                        label={`Series ${groupIndex + 1} axis`}
                        value={group.axis ?? "left"}
                        onChange={(axis) =>
                          setDraftGroups((current) =>
                            current.map((item, index) =>
                              index === groupIndex
                                ? { ...item, axis: axis as "left" | "right" }
                                : item,
                            ),
                          )
                        }
                        options={[
                          { value: "left", label: "Left axis" },
                          { value: "right", label: "Right axis" },
                        ]}
                        triggerClassName="min-w-0 px-2.5 py-2 text-xs"
                      />
                      <input
                        aria-label={`Series ${groupIndex + 1} color`}
                        type="text"
                        value={group.color ?? CHART_COLORS[groupIndex % CHART_COLORS.length]}
                        placeholder="CSS color"
                        onChange={(event) =>
                          setDraftGroups((current) =>
                            current.map((item, index) =>
                              index === groupIndex ? { ...item, color: event.target.value } : item,
                            ),
                          )
                        }
                        className="border-glass-border bg-background/70 text-foreground h-9 w-28 rounded-lg border px-2.5 py-2 text-xs outline-none"
                      />
                      <label className="text-foreground/65 inline-flex items-center gap-1.5 text-xs">
                        <input
                          type="checkbox"
                          checked={group.visible !== false}
                          onChange={(event) =>
                            setDraftGroups((current) =>
                              current.map((item, index) =>
                                index === groupIndex
                                  ? { ...item, visible: event.target.checked }
                                  : item,
                              ),
                            )
                          }
                        />
                        Visible
                      </label>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {group.points.map((point, pointIndex) => (
                        <div
                          key={`${group.name}-${pointIndex}`}
                          className="grid grid-cols-[minmax(0,1fr)_7rem] gap-2"
                        >
                          <input
                            aria-label={`Series ${groupIndex + 1} point ${pointIndex + 1} label`}
                            value={String(point.label ?? "")}
                            onChange={(event) =>
                              setDraftGroups((current) =>
                                current.map((item, index) =>
                                  index === groupIndex
                                    ? {
                                        ...item,
                                        points: item.points.map((candidate, candidateIndex) =>
                                          candidateIndex === pointIndex
                                            ? { ...candidate, label: event.target.value }
                                            : candidate,
                                        ),
                                      }
                                    : item,
                                ),
                              )
                            }
                            className="border-glass-border bg-background/70 text-foreground min-w-0 rounded-lg border px-2.5 py-2 text-xs outline-none"
                          />
                          <input
                            aria-label={`Series ${groupIndex + 1} point ${pointIndex + 1} value`}
                            inputMode="decimal"
                            type="number"
                            value={String(point.value ?? 0)}
                            onChange={(event) =>
                              setDraftGroups((current) =>
                                current.map((item, index) =>
                                  index === groupIndex
                                    ? {
                                        ...item,
                                        points: item.points.map((candidate, candidateIndex) =>
                                          candidateIndex === pointIndex
                                            ? {
                                                ...candidate,
                                                value:
                                                  event.target.value === ""
                                                    ? 0
                                                    : Number(event.target.value),
                                              }
                                            : candidate,
                                        ),
                                      }
                                    : item,
                                ),
                              )
                            }
                            className="border-glass-border bg-background/70 text-foreground rounded-lg border px-2.5 py-2 text-xs outline-none"
                          />
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
            <div className="mb-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
              <div>
                <label
                  htmlFor={`equation-${block.id}`}
                  className="text-foreground/55 mb-1 block text-[10px] font-semibold tracking-[0.12em] uppercase"
                >
                  Live equation (x → y)
                </label>
                <input
                  id={`equation-${block.id}`}
                  value={equationInput}
                  onChange={(event) => setEquationInput(event.target.value)}
                  placeholder="y = 2*x + 1"
                  className="border-glass-border bg-background/70 text-foreground focus:ring-primary/30 w-full rounded-lg border px-2.5 py-2 text-xs outline-none focus:ring-2"
                />
                {equationError ? (
                  <p className="mt-1 text-[11px] text-rose-500">{equationError}</p>
                ) : (
                  <p className="text-foreground/45 mt-1 text-[10px]">
                    Supports +, −, ×, ÷, powers, parentheses and x.
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={() => {
                  const expression = equationInput.trim();
                  if (!expression) {
                    setEquationError(null);
                    setDraftState((current) => ({ ...current, blockId: block.id, equation: null }));
                    setManualView("chart");
                    setSaveError(null);
                    return;
                  }
                  const nextSeries = draftSeries.map((point, index) => {
                    const x = toNumber(point.x ?? point.label);
                    return {
                      ...point,
                      value: evaluateEquation(expression, Number.isFinite(x) ? x : index),
                    };
                  });
                  if (nextSeries.some((point) => !Number.isFinite(point.value))) {
                    setEquationError("Use a safe numeric equation such as y = 2*x + 1.");
                    return;
                  }
                  setEquationError(null);
                  setDraftState({ blockId: block.id, series: nextSeries, equation: expression });
                  setManualView("chart");
                  setSaveError(null);
                }}
                className="visual-block-action self-end rounded-lg px-3 py-2 text-[11px]"
              >
                Recalculate
              </button>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {draftSeries.map((point, index) => (
                <div
                  key={`${index}-${String(point.label)}`}
                  className="grid grid-cols-[minmax(0,1fr)_7rem] gap-2"
                >
                  <input
                    aria-label={`Chart point ${index + 1} label`}
                    value={String(point.label ?? "")}
                    onChange={(event) => updatePoint(index, "label", event.target.value)}
                    className="border-glass-border bg-background/70 text-foreground focus:ring-primary/30 min-w-0 rounded-lg border px-2.5 py-2 text-xs outline-none focus:ring-2"
                  />
                  <input
                    aria-label={`Chart point ${index + 1} value`}
                    inputMode="decimal"
                    type="number"
                    value={String(point.value ?? 0)}
                    onChange={(event) => updatePoint(index, "value", event.target.value)}
                    className="border-glass-border bg-background/70 text-foreground focus:ring-primary/30 rounded-lg border px-2.5 py-2 text-xs outline-none focus:ring-2"
                  />
                </div>
              ))}
            </div>
          </div>
        ) : null}
        <div ref={chartAreaRef} className="relative min-w-0" data-chart-tooltip-boundary>
          {view === "payload" && hasPayload ? (
            <div className="bg-background/55 rounded-[1.3rem] border border-black/5 p-4 dark:border-white/8">
              <div className="text-foreground/55 mb-3 flex items-center gap-2 border-b border-black/5 pb-2 text-xs dark:border-white/8">
                <FileJson className="h-4 w-4" />
                <span>{block.is_streaming ? "Streaming payload" : "Raw payload"}</span>
              </div>
              <pre className="text-foreground/76 overflow-auto text-[11px] leading-6 break-words whitespace-pre-wrap">
                {activeBlock.raw_payload}
              </pre>
            </div>
          ) : (
            <ChartRenderer block={activeBlock} onHover={handlePointHover} onChange={onChange} />
          )}

          <AnimatePresence initial={false}>
            {activePoint ? (
              <motion.div
                ref={tooltipRef}
                initial={{ opacity: 0, scale: 0.98, y: 4 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.98, y: 2 }}
                transition={{ duration: 0.14, ease: "easeOut" }}
                role="tooltip"
                className="averqel-tooltip-surface pointer-events-none absolute z-50 flex max-w-[calc(100%-1rem)] min-w-[140px] flex-col rounded-xl border p-3"
                style={{
                  left: tooltipPosition?.left ?? 0,
                  top: tooltipPosition?.top ?? 0,
                  visibility: tooltipPosition ? "visible" : "hidden",
                  transition: "left 120ms ease-out, top 120ms ease-out",
                }}
              >
                <p className="text-foreground/60 border-glass-border mb-2 border-b pb-1 text-[10px] font-bold tracking-[0.15em] break-words uppercase">
                  {activePoint.label}
                </p>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-8">
                    <span className="text-foreground/70 flex items-center gap-1.5 font-mono text-[10px]">
                      <span
                        className="h-1.5 w-1.5 rounded-full"
                        style={{ backgroundColor: activePoint.color }}
                      />
                      Value:
                    </span>
                    <span className="text-primary font-mono text-sm font-bold">
                      {formatNumber(activePoint.value)}
                    </span>
                  </div>

                  {activePoint.z !== undefined ? (
                    <div className="border-glass-border mt-1.5 flex items-center justify-between border-t pt-1.5">
                      <span className="text-foreground/60 font-mono text-[9px] tracking-tighter uppercase">
                        Magnitude (Z):
                      </span>
                      <span className="text-foreground/70 font-mono text-xs">{activePoint.z}</span>
                    </div>
                  ) : null}
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
        {activeBlock.equation ? (
          <div className="border-glass-border bg-background/45 text-foreground/75 mt-5 rounded-xl border px-4 py-3 font-mono text-sm">
            <span className="text-foreground/45 mr-2 text-[10px] font-semibold tracking-[0.14em] uppercase">
              Equation
            </span>
            {activeBlock.equation}
          </div>
        ) : null}
      </div>

      <div className="text-foreground/52 border-t border-black/5 px-5 py-3 text-[11px] sm:px-6 dark:border-white/8">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="inline-flex items-center gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5" />
            {typeof block.confidence === "number"
              ? `Confidence ${Math.round(block.confidence * 100)}%`
              : "Confidence not provided"}
          </span>
          {block.fields && block.fields.length > 0 ? (
            <span className="truncate">Fields: {block.fields.join(", ")}</span>
          ) : null}
        </div>
      </div>
    </section>
  );
});

export default ChartBlock;

const ChartRenderer = memo(function ChartRenderer({
  block,
  onHover,
  onChange,
}: {
  block: StreamChartBlock;
  onHover: (
    point: { label: string; value: number; color: string; x: number; y: number } | null,
  ) => void;
  onChange?: (block: StreamChartBlock) => void | boolean | Promise<void | boolean>;
}) {
  const points = normalizePoints(block);
  const groups = normalizeSeriesGroups(block);
  if (points.length === 0 && groups.length === 0) {
    return (
      <div className="text-foreground/45 flex h-[280px] items-center justify-center rounded-[1.3rem] border border-dashed border-black/10 text-sm dark:border-white/10">
        Empty dataset
      </div>
    );
  }

  if (groups.length > 1 && block.chart_type !== "pie") {
    return (
      <MultiSeriesChart
        block={block}
        groups={groups}
        mode={block.chart_type}
        onHover={onHover}
        onChange={onChange}
      />
    );
  }

  switch (block.chart_type) {
    case "line":
      return <CartesianSvgChart block={block} points={points} mode="line" onHover={onHover} />;
    case "area":
      return <CartesianSvgChart block={block} points={points} mode="area" onHover={onHover} />;
    case "scatter":
      return <CartesianSvgChart block={block} points={points} mode="scatter" onHover={onHover} />;
    case "pie":
      return <PieVisual block={block} points={points} onHover={onHover} />;
    case "bar":
      return <CartesianSvgChart block={block} points={points} mode="bar" onHover={onHover} />;
    default:
      return <CartesianSvgChart block={block} points={points} mode="line" onHover={onHover} />;
  }
});

type NormalizedSeries = {
  name: string;
  points: NormalizedPoint[];
  color: string;
  axis: "left" | "right";
  visible?: boolean;
};

function MultiSeriesChart({
  block,
  groups,
  mode,
  onHover,
  onChange,
}: {
  block: StreamChartBlock;
  groups: NormalizedSeries[];
  mode: StreamChartBlock["chart_type"];
  onHover: (point: HoverPoint | null) => void;
  onChange?: (block: StreamChartBlock) => void | boolean | Promise<void | boolean>;
}) {
  const [hidden, setHidden] = useState<Set<string>>(
    () => new Set(groups.filter((group) => group.visible === false).map((group) => group.name)),
  );
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savingVisibility, setSavingVisibility] = useState(false);
  const chartId = useId().replace(/:/g, "");
  const svgRef = useRef<SVGSVGElement>(null);
  const width = 680;
  const height = 320;
  const padding = { top: 34, right: 58, bottom: 54, left: 58 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const visibleGroups = groups.filter((group) => !hidden.has(group.name));
  const labels = Array.from(
    new Set(groups.flatMap((group) => group.points.map((point) => point.label))),
  );
  const leftValues = visibleGroups
    .filter((group) => group.axis === "left")
    .flatMap((group) => group.points.map((point) => point.value));
  const rightValues = visibleGroups
    .filter((group) => group.axis === "right")
    .flatMap((group) => group.points.map((point) => point.value));
  const toggleSeriesGroup = async (groupName: string) => {
    if (savingVisibility) return;
    const previousHidden = hidden;
    const nextHidden = new Set(hidden);
    if (nextHidden.has(groupName)) nextHidden.delete(groupName);
    else nextHidden.add(groupName);
    setHidden(nextHidden);
    setSaveError(null);
    setSavingVisibility(true);
    try {
      const saved = await onChange?.({
        ...block,
        series_groups: (block.series_groups ?? []).map((item) =>
          item.name === groupName ? { ...item, visible: !nextHidden.has(groupName) } : item,
        ),
        revision: (block.revision ?? 0) + 1,
      });
      if (saved === false) throw new Error("Chart visibility could not be saved. Try again.");
    } catch (caught) {
      setHidden(previousHidden);
      setSaveError(
        caught instanceof Error
          ? caught.message
          : "Chart visibility could not be saved. Try again.",
      );
    } finally {
      setSavingVisibility(false);
    }
  };
  const leftMax = Math.max(...leftValues, mode === "bar" ? 0 : 1);
  const leftMin = Math.min(...leftValues, 0);
  const leftSpan = Math.max(leftMax - leftMin, 0.1);
  const rightMax = Math.max(...rightValues, mode === "bar" ? 0 : 1);
  const rightMin = Math.min(...rightValues, 0);
  const rightSpan = Math.max(rightMax - rightMin, 0.1);
  const xFor = (index: number) =>
    padding.left + (labels.length <= 1 ? plotWidth / 2 : (index / (labels.length - 1)) * plotWidth);
  const barXFor = (index: number) =>
    padding.left + ((index + 0.5) / Math.max(labels.length, 1)) * plotWidth;
  const categoryXFor = mode === "bar" ? barXFor : xFor;
  const barWidth = Math.min(
    ((plotWidth / Math.max(labels.length, 1)) * 0.72) / Math.max(visibleGroups.length, 1),
    40,
  );
  const yFor = (value: number, axis: "left" | "right") => {
    const min = axis === "right" ? rightMin : leftMin;
    const span = axis === "right" ? rightSpan : leftSpan;
    return padding.top + plotHeight - ((value - min) / span) * plotHeight;
  };
  const ticks = Array.from({ length: 4 }, (_, index) => {
    const value = leftMin + ((3 - index) / 3) * leftSpan;
    return { value, y: padding.top + (index / 3) * plotHeight };
  });
  const pointFor = (group: NormalizedSeries, point: NormalizedPoint) => {
    const index = labels.indexOf(point.label);
    const groupOffset =
      mode === "bar"
        ? (visibleGroups.indexOf(group) - (visibleGroups.length - 1) / 2) * barWidth
        : 0;
    return {
      ...point,
      x: categoryXFor(Math.max(index, 0)) + groupOffset,
      y: yFor(point.value, group.axis),
    };
  };
  const hover = (group: NormalizedSeries, point: ReturnType<typeof pointFor>) => {
    const svg = svgRef.current;
    const parent = svg?.closest("[data-chart-tooltip-boundary]");
    const matrix = svg?.getScreenCTM();
    if (!svg || !parent || !matrix) return;
    const svgPoint = svg.createSVGPoint();
    svgPoint.x = point.x;
    svgPoint.y = point.y;
    const screen = svgPoint.matrixTransform(matrix);
    const rect = parent.getBoundingClientRect();
    onHover({
      label: `${group.name} · ${point.label}`,
      value: point.value,
      color: group.color,
      x: screen.x - rect.left,
      y: screen.y - rect.top,
      z: point.z,
    });
  };

  return (
    <div className="min-w-0 space-y-4">
      <div className="bg-background/55 relative min-w-0 overflow-x-auto rounded-[1.3rem] border border-black/5 p-4 dark:border-white/8">
        <div className="h-[360px] w-full">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${width} ${height}`}
            className="h-full w-full"
            role="img"
            aria-label={block.title ?? "Chart"}
          >
            <defs>
              <filter id={`${chartId}-glow`} x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="3.5" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
            </defs>
            {ticks.map((tick, index) => (
              <g key={`${block.id}-multi-tick-${index}`}>
                <line
                  x1={padding.left}
                  x2={width - padding.right}
                  y1={tick.y}
                  y2={tick.y}
                  stroke="currentColor"
                  strokeOpacity="0.08"
                  strokeDasharray={index === 3 ? "0" : "4 4"}
                />
                <text
                  x={padding.left - 10}
                  y={tick.y + 4}
                  textAnchor="end"
                  className="fill-current text-[10px]"
                  opacity="0.5"
                >
                  {formatNumber(tick.value)}
                </text>
                {rightValues.length > 0 ? (
                  <text
                    x={width - padding.right + 10}
                    y={tick.y + 4}
                    className="fill-current text-[10px]"
                    opacity="0.5"
                  >
                    {formatNumber(rightMin + ((3 - index) / 3) * rightSpan)}
                  </text>
                ) : null}
              </g>
            ))}
            <line
              x1={padding.left}
              x2={padding.left}
              y1={padding.top}
              y2={padding.top + plotHeight}
              stroke="currentColor"
              strokeOpacity="0.2"
            />
            {rightValues.length > 0 ? (
              <line
                x1={width - padding.right}
                x2={width - padding.right}
                y1={padding.top}
                y2={padding.top + plotHeight}
                stroke="currentColor"
                strokeOpacity="0.2"
              />
            ) : null}
            <line
              x1={padding.left}
              x2={width - padding.right}
              y1={padding.top + plotHeight}
              y2={padding.top + plotHeight}
              stroke="currentColor"
              strokeOpacity="0.2"
            />
            {visibleGroups.map((group) => {
              const coords = group.points.map((point) => pointFor(group, point));
              const polyline = coords.map((point) => `${point.x},${point.y}`).join(" ");
              if (mode === "bar") {
                const groupIndex = visibleGroups.indexOf(group);
                return coords.map((point) => {
                  const labelIndex = labels.indexOf(point.label);
                  const x =
                    categoryXFor(labelIndex) +
                    (groupIndex - (visibleGroups.length - 1) / 2) * barWidth;
                  const baseline = yFor(0, group.axis);
                  return (
                    <rect
                      key={`${group.name}-${point.label}`}
                      x={x - barWidth / 2}
                      y={Math.min(point.y, baseline)}
                      width={barWidth}
                      height={Math.abs(baseline - point.y)}
                      rx="4"
                      fill={group.color}
                      fillOpacity="0.78"
                      onMouseEnter={() => hover(group, point)}
                      onMouseLeave={() => onHover(null)}
                      className="cursor-pointer hover:opacity-80"
                    />
                  );
                });
              }
              return (
                <g key={group.name}>
                  {mode === "area" ? (
                    <path
                      d={[
                        `M ${coords[0]?.x ?? padding.left} ${padding.top + plotHeight}`,
                        ...coords.map((point) => `L ${point.x} ${point.y}`),
                        `L ${coords.at(-1)?.x ?? padding.left} ${padding.top + plotHeight}`,
                        "Z",
                      ].join(" ")}
                      fill={group.color}
                      fillOpacity="0.12"
                    />
                  ) : null}
                  <polyline
                    points={polyline}
                    fill="none"
                    stroke={group.color}
                    strokeWidth="3"
                    strokeLinejoin="round"
                    strokeLinecap="round"
                  />
                  {coords.map((point) => (
                    <circle
                      key={`${group.name}-point-${point.label}`}
                      cx={point.x}
                      cy={point.y}
                      r={
                        mode === "scatter" ? 6 + Math.min(Math.abs(point.z ?? point.value), 14) : 5
                      }
                      fill={group.color}
                      stroke="white"
                      strokeWidth="2"
                      filter={mode === "scatter" ? `url(#${chartId}-glow)` : undefined}
                      onMouseEnter={() => hover(group, point)}
                      onMouseLeave={() => onHover(null)}
                      className="cursor-pointer"
                    />
                  ))}
                </g>
              );
            })}
            {labels.map((label, index) => (
              <text
                key={`${block.id}-multi-label-${label}`}
                x={categoryXFor(index)}
                y={padding.top + plotHeight + 22}
                textAnchor="middle"
                className="fill-current text-[10px]"
                opacity="0.6"
              >
                {truncateLabel(label)}
              </text>
            ))}
            {block.annotations?.map((annotation) => {
              const index = labels.indexOf(String(annotation.x));
              if (index < 0) return null;
              const x = categoryXFor(index);
              return (
                <g key={`${block.id}-annotation-${annotation.label}-${annotation.x}`}>
                  <line
                    x1={x}
                    x2={x}
                    y1={padding.top}
                    y2={padding.top + plotHeight}
                    stroke={annotation.color ?? "currentColor"}
                    strokeDasharray="3 3"
                    opacity="0.5"
                  />
                  <text
                    x={x + 5}
                    y={padding.top + 12}
                    className="fill-current text-[10px]"
                    opacity="0.75"
                  >
                    {annotation.label}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>
      {saveError ? (
        <p className="mb-3 text-xs text-rose-600 dark:text-rose-300" role="alert">
          {saveError}
        </p>
      ) : null}
      {block.legend !== false ? (
        <div className="flex flex-wrap gap-2">
          {groups.map((group) => (
            <button
              key={group.name}
              type="button"
              onClick={() => void toggleSeriesGroup(group.name)}
              disabled={savingVisibility}
              aria-busy={savingVisibility}
              className={`visual-block-action inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-xs ${hidden.has(group.name) ? "opacity-40" : ""}`}
            >
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: group.color }} />
              {group.name}
              {group.axis === "right" ? " · right axis" : ""}
            </button>
          ))}
        </div>
      ) : null}
      {block.secondary_y_label && rightValues.length > 0 ? (
        <p className="text-foreground/50 text-xs">Secondary axis: {block.secondary_y_label}</p>
      ) : null}
    </div>
  );
}

// BarVisual was horizontal HTML bars.
// We now use CartesianSvgChart for vertical 'Premium' SVG bars.

function CartesianSvgChart({
  block,
  points,
  mode,
  onHover,
}: {
  block: StreamChartBlock;
  points: NormalizedPoint[];
  mode: "line" | "area" | "scatter" | "bar";
  onHover: (p: HoverPoint | null) => void;
}) {
  const chartId = useId().replace(/:/g, "");
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const width = 680;
  const height = 300;
  const padding = { top: 30, right: 30, bottom: 50, left: 55 };
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const xAxisLabel = block.x_label?.trim() || "Timeline / Category";
  const yAxisLabel = block.y_label?.trim() || "Metric";

  const maxValue = Math.max(...points.map((p) => p.value), mode === "bar" ? 0 : 1);
  const minValue = Math.min(...points.map((p) => p.value), 0);
  const valueSpan = Math.max(maxValue - minValue, 0.1); // Prevent division by zero
  const maxZ = Math.max(...points.map((p) => p.z ?? 0), 0.1);

  const coords = points.map((point, index) => {
    const x =
      mode === "bar"
        ? padding.left + ((index + 0.5) / Math.max(points.length, 1)) * plotWidth
        : padding.left +
          (points.length === 1 ? plotWidth / 2 : (index / (points.length - 1)) * plotWidth);
    const y = padding.top + plotHeight - ((point.value - minValue) / valueSpan) * plotHeight;
    const radius =
      mode === "scatter"
        ? 6 + (((point.z ?? point.value) / Math.max(maxZ, maxValue)) * 14 || 0)
        : 6;
    return { ...point, x, y, radius };
  });

  const polyline = coords.map((p) => `${p.x},${p.y}`).join(" ");
  const areaPath = [
    `M ${coords[0]?.x ?? padding.left} ${padding.top + plotHeight}`,
    ...coords.map((p) => `L ${p.x} ${p.y}`),
    `L ${coords[coords.length - 1]?.x ?? padding.left} ${padding.top + plotHeight}`,
    "Z",
  ].join(" ");

  const yTicks = Array.from({ length: 4 }, (_, index) => {
    const value = minValue + ((3 - index) / 3) * valueSpan;
    const y = padding.top + (index / 3) * plotHeight;
    return { value, y };
  });

  // Precise mapping from SVG coordinate to ChartBlock container coordinate
  const handlePointHover = (point: (typeof coords)[0], index: number) => {
    if (svgRef.current && containerRef.current) {
      const svg = svgRef.current;
      const chartContainer = containerRef.current.closest("[data-chart-tooltip-boundary]");
      if (!chartContainer) return;

      const containerRect = chartContainer.getBoundingClientRect();
      const pointInSvg = svg.createSVGPoint();
      pointInSvg.x = point.x;
      pointInSvg.y = point.y;

      const screenPoint = pointInSvg.matrixTransform(svg.getScreenCTM()!);

      onHover({
        label: point.label,
        value: point.value,
        color: CHART_COLORS[index % CHART_COLORS.length],
        x: screenPoint.x - containerRect.left,
        y: screenPoint.y - containerRect.top,
        z: point.z,
      });
    }
  };

  return (
    <div className="min-w-0 space-y-5">
      <div
        ref={containerRef}
        className="bg-background/55 relative min-w-0 overflow-x-auto rounded-[1.3rem] border border-black/5 p-4 dark:border-white/8"
      >
        <div className="h-[340px] w-full">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${width} ${height}`}
            className="h-full w-full"
            role="img"
            aria-label={block.title ?? "Chart"}
          >
            <defs>
              <linearGradient id={`${chartId}-area`} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={CHART_COLORS[1]} stopOpacity="0.45" />
                <stop offset="100%" stopColor={CHART_COLORS[2]} stopOpacity="0.05" />
              </linearGradient>
              <linearGradient id={`${chartId}-bar`} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor={CHART_COLORS[0]} stopOpacity="0.8" />
                <stop offset="100%" stopColor={CHART_COLORS[0]} stopOpacity="0.1" />
              </linearGradient>
              <filter id={`${chartId}-glow`} x="-20%" y="-20%" width="140%" height="140%">
                <feGaussianBlur stdDeviation="3.5" result="blur" />
                <feComposite in="SourceGraphic" in2="blur" operator="over" />
              </filter>
            </defs>

            {/* Y-Axis Grid Lines */}
            {yTicks.map((tick, index) => (
              <g key={`${block.id}-ytick-${index}`}>
                <line
                  x1={padding.left}
                  x2={width - padding.right}
                  y1={tick.y}
                  y2={tick.y}
                  stroke="currentColor"
                  strokeOpacity="0.08"
                  strokeDasharray={index === 3 ? "0" : "4 4"}
                />
                <text
                  x={padding.left - 12}
                  y={tick.y + 4}
                  textAnchor="end"
                  className="fill-current text-[10px] font-medium"
                  opacity="0.48"
                >
                  {formatNumber(tick.value)}
                </text>
              </g>
            ))}

            {/* Actual Axis Lines */}
            <line
              x1={padding.left}
              x2={padding.left}
              y1={padding.top}
              y2={padding.top + plotHeight}
              stroke="currentColor"
              strokeOpacity="0.2"
              strokeWidth="1.5"
            />
            <line
              x1={padding.left}
              x2={width - padding.right}
              y1={padding.top + plotHeight}
              y2={padding.top + plotHeight}
              stroke="currentColor"
              strokeOpacity="0.2"
              strokeWidth="1.5"
            />

            {/* Axis Titles */}
            <text
              data-axis-label="y"
              x={15}
              y={padding.top + plotHeight / 2}
              transform={`rotate(-90 15 ${padding.top + plotHeight / 2})`}
              className="fill-primary/60 text-[9px] font-bold tracking-widest uppercase"
              textAnchor="middle"
            >
              {yAxisLabel}
            </text>
            <text
              data-axis-label="x"
              x={padding.left + plotWidth / 2}
              y={height - 5}
              className="fill-primary/60 text-[9px] font-bold tracking-widest uppercase"
              textAnchor="middle"
            >
              {xAxisLabel}
            </text>

            {mode === "area" && (
              <motion.path
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.8 }}
                d={areaPath}
                fill={`url(#${chartId}-area)`}
              />
            )}

            {mode === "bar" && (
              <g>
                {coords.map((point, index) => {
                  const categoryWidth = plotWidth / Math.max(points.length, 1);
                  const barWidth = Math.min(categoryWidth * 0.68, 48);
                  const baseline =
                    padding.top + plotHeight - ((0 - minValue) / valueSpan) * plotHeight;
                  const barY = Math.min(point.y, baseline);
                  const barHeight = Math.abs(baseline - point.y);
                  return (
                    <rect
                      key={`bar-${index}`}
                      x={point.x - barWidth / 2}
                      y={barY}
                      width={barWidth}
                      height={barHeight}
                      fill={`url(#${chartId}-bar)`}
                      rx={4}
                      onMouseEnter={() => handlePointHover(point, index)}
                      onMouseLeave={() => onHover(null)}
                      className="cursor-pointer transition-opacity hover:opacity-80"
                    />
                  );
                })}
              </g>
            )}

            {mode !== "scatter" && mode !== "bar" && (
              <motion.polyline
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={{ duration: 1.2, ease: "easeOut" }}
                fill="none"
                points={polyline}
                stroke={CHART_COLORS[0]}
                strokeWidth="3.5"
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            )}

            {mode !== "bar" &&
              coords.map((point, index) => (
                <motion.g
                  key={`${block.id}-point-${index}`}
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: index * 0.04, duration: 0.3 }}
                  onMouseEnter={() => handlePointHover(point, index)}
                  onMouseLeave={() => onHover(null)}
                  className="cursor-pointer"
                >
                  {/* Larger invisible hit-box for easier hovering */}
                  <circle cx={point.x} cy={point.y} r={20} fill="transparent" />
                  <circle
                    cx={point.x}
                    cy={point.y}
                    r={mode === "scatter" ? point.radius : 6}
                    fill={CHART_COLORS[index % CHART_COLORS.length]}
                    className="transition-all"
                    stroke="white"
                    strokeOpacity="0.9"
                    strokeWidth="2.5"
                    filter={mode === "scatter" ? `url(#${chartId}-glow)` : undefined}
                  />
                </motion.g>
              ))}

            {coords.map((point, index) => (
              <text
                key={`${block.id}-label-${index}`}
                x={point.x}
                y={padding.top + plotHeight + 18}
                textAnchor="middle"
                className="fill-current text-[10px] font-medium"
                opacity="0.6"
              >
                {truncateLabel(point.label)}
              </text>
            ))}
          </svg>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {points.map((point, index) => (
          <div
            key={`${block.id}-legend-${index}`}
            className="bg-background/55 group hover:border-primary/30 rounded-2xl border border-black/5 p-4 transition-all hover:shadow-lg dark:border-white/8 dark:hover:bg-white/5"
          >
            <div className="text-foreground/50 mb-1 text-[9px] font-bold tracking-[0.1em] uppercase">
              {point.label}
            </div>
            <div className="flex items-center gap-2.5">
              <span
                className="h-2.5 w-2.5 rounded-full ring-2 ring-white/10"
                style={{ backgroundColor: CHART_COLORS[index % CHART_COLORS.length] }}
              />
              <span className="text-foreground text-base font-extrabold tracking-tight">
                {formatNumber(point.value)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function PieVisual({
  block,
  points,
  onHover,
}: {
  block: StreamChartBlock;
  points: NormalizedPoint[];
  onHover: (p: HoverPoint | null) => void;
}) {
  const chartId = useId().replace(/:/g, "");
  const svgRef = useRef<SVGSVGElement>(null);
  const total = points.reduce((sum, p) => sum + Math.max(p.value, 0), 0);
  const slices = points.reduce<
    Array<
      NormalizedPoint & {
        color: string;
        path: string;
        midAngle: number;
        share: number;
      }
    >
  >((acc, p, index) => {
    const startAngle =
      index === 0
        ? -Math.PI / 2
        : acc[index - 1]!.midAngle + (acc[index - 1]!.share / 100) * Math.PI;
    const portion = total <= 0 ? 1 / points.length : Math.max(p.value, 0) / total;
    const endAngle = startAngle + portion * Math.PI * 2;
    acc.push({
      ...p,
      color: CHART_COLORS[index % CHART_COLORS.length],
      path: describeArc(120, 120, 78, 40, startAngle, endAngle),
      midAngle: startAngle + (endAngle - startAngle) / 2,
      share: portion * 100,
    });
    return acc;
  }, []);

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,300px)_1fr] lg:items-center">
      <div className="bg-background/55 relative flex justify-center rounded-[1.3rem] border border-black/5 p-5 dark:border-white/8">
        <svg
          ref={svgRef}
          viewBox="0 0 240 240"
          className="h-[260px] w-full max-w-[280px]"
          role="img"
          aria-label={block.title ?? "Chart"}
        >
          {slices.map((slice, index) => (
            <motion.path
              key={`${block.id}-${slice.label}`}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: index * 0.1, duration: 0.5 }}
              d={slice.path}
              fill={slice.color}
              stroke="white"
              strokeOpacity="0.8"
              strokeWidth="2.5"
              className="cursor-pointer transition-transform hover:scale-[1.02]"
              filter={`url(#${chartId}-glow)`}
              onMouseEnter={() => {
                if (svgRef.current) {
                  const svg = svgRef.current;
                  const chartContainer = svg.closest("[data-chart-tooltip-boundary]");
                  if (!chartContainer) return;
                  const containerRect = chartContainer.getBoundingClientRect();

                  const r = 85;
                  const centerX = 120;
                  const centerY = 120;
                  const x = centerX + r * Math.cos(slice.midAngle);
                  const y = centerY + r * Math.sin(slice.midAngle);

                  const p = svg.createSVGPoint();
                  p.x = x;
                  p.y = y;
                  const screenP = p.matrixTransform(svg.getScreenCTM()!);

                  onHover({
                    label: slice.label,
                    value: slice.value,
                    color: slice.color,
                    x: screenP.x - containerRect.left,
                    y: screenP.y - containerRect.top,
                  });
                }
              }}
              onMouseLeave={() => onHover(null)}
            />
          ))}
        </svg>
      </div>

      <div className="grid gap-3.5">
        {slices.map((slice) => (
          <div
            key={`${block.id}-slice-${slice.label}`}
            className="bg-background/55 group hover:bg-primary/5 flex items-center justify-between rounded-2xl border border-black/5 px-5 py-4 transition-all dark:border-white/8 dark:hover:bg-white/5"
          >
            <div className="flex items-center gap-4">
              <span
                className="h-4 w-4 rounded-full ring-2 ring-white/10"
                style={{ backgroundColor: slice.color }}
              />
              <div>
                <div className="text-foreground text-[14px] font-bold tracking-tight">
                  {slice.label}
                </div>
                <div className="text-primary text-[9px] font-black tracking-[0.15em] uppercase">
                  {slice.share.toFixed(1)}% weight share
                </div>
              </div>
            </div>
            <div className="text-foreground text-xl font-black tracking-tighter tabular-nums drop-shadow-sm">
              {formatNumber(slice.value)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function normalizePoints(block: StreamChartBlock): NormalizedPoint[] {
  const xKey = block.x_key ?? "label";
  const yKey = block.y_key ?? "value";
  const zKey = block.z_key ?? "z";

  return block.series.flatMap((point) => {
    const labelCandidate = point[xKey] ?? point.label;
    const valueCandidate = point[yKey] ?? point.value;
    const zCandidate = point[zKey] ?? point.z;
    const value = toNumber(valueCandidate);
    if (typeof labelCandidate !== "string" && typeof labelCandidate !== "number") {
      return [];
    }
    if (!Number.isFinite(value)) {
      return [];
    }
    return [
      {
        label: String(labelCandidate),
        value,
        z: Number.isFinite(toNumber(zCandidate)) ? toNumber(zCandidate) : undefined,
      },
    ];
  });
}

function normalizeSeriesGroups(block: StreamChartBlock): NormalizedSeries[] {
  const groups = block.series_groups ?? [];
  if (groups.length === 0) return [];
  return groups
    .map((group, index) => ({
      name: group.name,
      points: group.points.flatMap((point) => normalizePoint(point, block)),
      color: group.color ?? CHART_COLORS[index % CHART_COLORS.length]!,
      axis: group.axis ?? "left",
      visible: group.visible !== false,
    }))
    .filter((group) => group.points.length > 0);
}

function normalizePoint(point: StreamChartPoint, block: StreamChartBlock): NormalizedPoint[] {
  const labelCandidate = point[block.x_key ?? "label"] ?? point.label;
  const valueCandidate = point[block.y_key ?? "value"] ?? point.value;
  const zCandidate = point[block.z_key ?? "z"] ?? point.z;
  const value = toNumber(valueCandidate);
  if (
    (typeof labelCandidate !== "string" && typeof labelCandidate !== "number") ||
    !Number.isFinite(value)
  )
    return [];
  return [
    {
      label: String(labelCandidate),
      value,
      z: Number.isFinite(toNumber(zCandidate)) ? toNumber(zCandidate) : undefined,
    },
  ];
}

function getChartIcon(chartType: StreamChartBlock["chart_type"]) {
  switch (chartType) {
    case "line":
      return <LineChartIcon className="h-5 w-5" />;
    case "pie":
      return <PieChartIcon className="h-5 w-5" />;
    case "scatter":
      return <ScatterChartIcon className="h-5 w-5" />;
    case "area":
      return <Activity className="h-5 w-5" />;
    case "bar":
    default:
      return <BarChart3 className="h-5 w-5" />;
  }
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat(undefined, {
    maximumFractionDigits: Math.abs(value) >= 100 ? 0 : 2,
  }).format(value);
}

function truncateLabel(label: string): string {
  return label.length > 14 ? `${label.slice(0, 13)}…` : label;
}

function toNumber(value: unknown): number {
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value.replace(/,/g, ""));
    return Number.isFinite(parsed) ? parsed : Number.NaN;
  }
  return Number.NaN;
}

/** Evaluate the deliberately small chart equation language without eval(). */
function evaluateEquation(source: string, x: number): number {
  const expression = source
    .replace(/^\s*y\s*=\s*/i, "")
    .replace(/×/g, "*")
    .replace(/÷/g, "/");
  const tokens = expression.match(/(?:\d*\.\d+|\d+\.?\d*|x|[()+\-*/^])/gi);
  if (!tokens || tokens.join("") !== expression.replace(/\s+/g, "")) return Number.NaN;
  let cursor = 0;
  const peek = () => tokens[cursor];
  const consume = () => tokens[cursor++];
  const parsePrimary = (): number => {
    const token = consume();
    if (!token) return Number.NaN;
    if (token.toLowerCase() === "x") return x;
    if (token === "(") {
      const value = parseAdditive();
      if (consume() !== ")") return Number.NaN;
      return value;
    }
    const parsed = Number(token);
    return Number.isFinite(parsed) ? parsed : Number.NaN;
  };
  const parsePower = (): number => {
    const left = parsePrimary();
    if (peek() === "^") {
      consume();
      return Math.pow(left, parsePower());
    }
    return left;
  };
  const parseMultiplicative = (): number => {
    let value = parsePower();
    while (peek() === "*" || peek() === "/") {
      const operator = consume();
      const right = parsePower();
      value = operator === "*" ? value * right : value / right;
    }
    return value;
  };
  const parseAdditive = (): number => {
    let value = parseMultiplicative();
    while (peek() === "+" || peek() === "-") {
      const operator = consume();
      const right = parseMultiplicative();
      value = operator === "+" ? value + right : value - right;
    }
    return value;
  };
  const result = parseAdditive();
  return cursor === tokens.length && Number.isFinite(result) ? result : Number.NaN;
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80);
}

function describeArc(
  cx: number,
  cy: number,
  outerRadius: number,
  innerRadius: number,
  startAngle: number,
  endAngle: number,
): string {
  const largeArcFlag = endAngle - startAngle > Math.PI ? 1 : 0;
  const outerStart = polarToCartesian(cx, cy, outerRadius, endAngle);
  const outerEnd = polarToCartesian(cx, cy, outerRadius, startAngle);
  const innerStart = polarToCartesian(cx, cy, innerRadius, startAngle);
  const innerEnd = polarToCartesian(cx, cy, innerRadius, endAngle);

  return [
    `M ${outerStart.x} ${outerStart.y}`,
    `A ${outerRadius} ${outerRadius} 0 ${largeArcFlag} 0 ${outerEnd.x} ${outerEnd.y}`,
    `L ${innerStart.x} ${innerStart.y}`,
    `A ${innerRadius} ${innerRadius} 0 ${largeArcFlag} 1 ${innerEnd.x} ${innerEnd.y}`,
    "Z",
  ].join(" ");
}

function polarToCartesian(cx: number, cy: number, radius: number, angle: number) {
  return {
    x: cx + radius * Math.cos(angle),
    y: cy + radius * Math.sin(angle),
  };
}

interface NormalizedPoint {
  label: string;
  value: number;
  z?: number;
}

function resolveChartView({
  canRenderVisual,
  hasPayload,
  isStreaming,
  manualView,
}: {
  canRenderVisual: boolean;
  hasPayload: boolean;
  isStreaming: boolean;
  manualView: "chart" | "payload" | null;
}): "chart" | "payload" {
  if (isStreaming && !canRenderVisual && hasPayload) {
    return "payload";
  }
  if (manualView === "payload" && hasPayload) {
    return "payload";
  }
  if (manualView === "chart" && canRenderVisual) {
    return "chart";
  }
  if (canRenderVisual) {
    return "chart";
  }
  if (hasPayload) {
    return "payload";
  }
  return "chart";
}
