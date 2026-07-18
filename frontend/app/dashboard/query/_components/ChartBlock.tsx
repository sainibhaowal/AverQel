import { AnimatePresence, motion } from "framer-motion";
import { memo, useId, useRef, useState } from "react";
import {
  Activity,
  BarChart3,
  CheckCircle2,
  FileJson,
  LineChart as LineChartIcon,
  PieChart as PieChartIcon,
  ScanSearch,
  ScatterChart as ScatterChartIcon,
  ShieldCheck,
} from "lucide-react";

import type { StreamChartBlock } from "../_lib/stream-protocol";

interface ChartBlockProps {
  block: StreamChartBlock;
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

// Re-defining the main component with Tooltip state
const ChartBlock = memo(function ChartBlock({ block }: ChartBlockProps) {
  const plottablePointCount = normalizePoints(block).length;
  const canRenderVisual = plottablePointCount > 1;
  const [manualView, setManualView] = useState<"chart" | "payload" | null>(null);
  const [activePoint, setActivePoint] = useState<HoverPoint | null>(null);
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

  return (
    <section className="theme-panel relative w-full min-w-0 overflow-hidden rounded-[1.8rem] shadow-[0_24px_70px_-44px_rgba(8,47,73,0.16)] dark:shadow-[0_24px_70px_-44px_rgba(8,47,73,0.82)]">
      <div className="border-b border-black/5 px-5 py-4 sm:px-6 dark:border-white/8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-3">
            <div className="bg-primary/10 text-primary border-primary/15 flex h-10 w-10 items-center justify-center rounded-2xl border">
              {icon}
            </div>
            <div className="space-y-1">
              <div className="flex flex-wrap items-center gap-2">
                <h4 className="text-foreground text-[15px] font-semibold tracking-[-0.015em]">
                  {chartTitle}
                </h4>
                <span className="theme-accent-pill rounded-full px-2.5 py-1 text-[10px] font-semibold tracking-[0.16em] uppercase">
                  {block.chart_type}
                </span>
                {block.is_streaming ? (
                  <span className="rounded-full border border-amber-500/20 bg-amber-500/10 px-2.5 py-1 text-[10px] font-semibold tracking-[0.16em] text-amber-700 uppercase dark:text-amber-200">
                    live
                  </span>
                ) : null}
              </div>
              <div className="text-foreground/60 flex flex-wrap items-center gap-3 text-xs">
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

          {hasPayload ? (
            <div className="bg-background/60 flex items-center gap-1 rounded-full border border-black/8 p-1 dark:border-white/10">
              <button
                type="button"
                onClick={() => setManualView("chart")}
                disabled={!canRenderVisual}
                className={`rounded-full px-3 py-1.5 text-[11px] font-medium transition ${
                  view === "chart"
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-foreground/60 hover:text-foreground"
                }`}
              >
                Visual
              </button>
              <button
                type="button"
                onClick={() => setManualView("payload")}
                className={`rounded-full px-3 py-1.5 text-[11px] font-medium transition ${
                  view === "payload"
                    ? "bg-primary text-primary-foreground shadow-sm"
                    : "text-foreground/60 hover:text-foreground"
                }`}
              >
                Payload
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <div className="min-w-0 px-4 py-4 sm:px-6">
        {view === "payload" && hasPayload ? (
          <div className="bg-background/55 rounded-[1.3rem] border border-black/5 p-4 dark:border-white/8">
            <div className="text-foreground/55 mb-3 flex items-center gap-2 border-b border-black/5 pb-2 text-xs dark:border-white/8">
              <FileJson className="h-4 w-4" />
              <span>{block.is_streaming ? "Streaming payload" : "Raw payload"}</span>
            </div>
            <pre className="text-foreground/76 overflow-auto text-[11px] leading-6 break-words whitespace-pre-wrap">
              {block.raw_payload}
            </pre>
          </div>
        ) : (
          <ChartRenderer block={block} onHover={setActivePoint} />
        )}
      </div>

      <AnimatePresence>
        {activePoint && (
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 5 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 5 }}
            className="pointer-events-none absolute z-50 flex min-w-[140px] flex-col rounded-lg border border-white/10 bg-[#09090b]/95 p-3 shadow-2xl ring-1 ring-white/5 backdrop-blur-xl"
            style={{
              left: activePoint.x,
              top: activePoint.y - 10, // Closer to the point
              transform: "translate(-50%, -100%)", // Proper anchoring above the point
            }}
          >
            {/* Header: Label */}
            <p className="mb-2 border-b border-white/5 pb-1 text-[10px] font-bold tracking-[0.15em] text-white/40 uppercase">
              {activePoint.label}
            </p>

            <div className="space-y-1.5">
              <div className="flex items-center justify-between gap-8">
                <span className="flex items-center gap-1.5 font-mono text-[10px] text-white/60">
                  <div
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ backgroundColor: activePoint.color }}
                  />
                  Value:
                </span>
                <span className="font-mono text-sm font-bold text-[#00e5ff]">
                  {formatNumber(activePoint.value)}
                </span>
              </div>

              {/* Optional: Magnitude/Z-Axis data */}
              {activePoint.z !== undefined && (
                <div className="mt-1.5 flex items-center justify-between border-t border-white/5 pt-1.5">
                  <span className="font-mono text-[9px] tracking-tighter text-white/30 uppercase">
                    Magnitude (Z):
                  </span>
                  <span className="font-mono text-xs text-white/60">{activePoint.z}</span>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

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

function ChartRenderer({
  block,
  onHover,
}: {
  block: StreamChartBlock;
  onHover: (
    point: { label: string; value: number; color: string; x: number; y: number } | null,
  ) => void;
}) {
  const points = normalizePoints(block);
  if (points.length === 0) {
    return (
      <div className="text-foreground/45 flex h-[280px] items-center justify-center rounded-[1.3rem] border border-dashed border-black/10 text-sm dark:border-white/10">
        Empty dataset
      </div>
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

  const maxValue = Math.max(...points.map((p) => p.value), 1);
  const minValue = Math.min(...points.map((p) => p.value), 0);
  const valueSpan = Math.max(maxValue - minValue, 0.1); // Prevent division by zero
  const maxZ = Math.max(...points.map((p) => p.z ?? 0), 0.1);

  const coords = points.map((point, index) => {
    const x =
      padding.left +
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
      const chartContainer = containerRef.current.closest("section"); // Get the relative parent
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
              x={5}
              y={padding.top - 10}
              className="fill-primary/60 text-[9px] font-bold tracking-widest uppercase"
              textAnchor="start"
            >
              Metric
            </text>
            <text
              x={width - 5}
              y={padding.top + plotHeight + 35}
              className="fill-primary/60 text-[9px] font-bold tracking-widest uppercase"
              textAnchor="end"
            >
              Timeline / Category
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
                  const barWidth = Math.min((plotWidth / (points.length || 1)) * 0.7, 40);
                  const barHeight = padding.top + plotHeight - point.y;
                  return (
                    <motion.rect
                      key={`bar-${index}`}
                      initial={{ height: 0, y: padding.top + plotHeight }}
                      animate={{ height: barHeight, y: point.y }}
                      transition={{ duration: 0.8, delay: index * 0.05 }}
                      x={point.x - barWidth / 2}
                      y={point.y}
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

            {coords.map((point, index) => (
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
                  const chartContainer = svg.closest("section");
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
