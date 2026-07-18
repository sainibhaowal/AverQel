"use client";

import Link from "next/link";
import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";
import {
  Activity,
  Brain,
  Cable,
  Clock,
  ChevronRight,
  Database,
  GitBranch,
  Layers3,
  Minus,
  Plus,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Terminal,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import {
  landingContentClass,
  landingEyebrowClass,
  landingHeaderWrapClass,
  landingSectionLeadClass,
  landingSectionShellClass,
  landingSectionTitleClass,
  landingTitleGradientBySection,
} from "./landingType";
import { useVisibilityAwareInterval } from "@/app/hooks/useVisibilityAwareInterval";

type Lane = {
  title: string;
  text: string;
};

type TelemetryItem = {
  label: string;
  value: string;
  icon: LucideIcon;
  color: string;
  status: "active" | "processing" | "idle";
};

type NodeItem = {
  id: string;
  title: string;
  subtitle: string;
  detail: string;
  badge: string;
  icon: LucideIcon;
  x: number;
  y: number;
  color: string;
  latency: string;
  status: "active" | "processing" | "idle";
  isMain?: boolean;
};

type LogEntry = {
  time: string;
  msg: string;
};

const styles = `
  :root {
    --bg-base: #06080A;
    --bg-surface: #0E1116;
    --bg-surface-hover: #151921;
    --border-subtle: #1E2430;
    --border-focus: #2E3846;
    --text-muted: #8B949E;
    --text-main: #C9D1D9;
    --text-bright: #F0F6FC;
    --accent-core: #00F0FF;
    --accent-success: #3FB950;
    --accent-warn: #D29922;
    --accent-purple: #A371F7;
  }

  .blueprint-grid {
    background-size: 20px 20px;
    background-image:
      linear-gradient(to right, rgba(255, 255, 255, 0.02) 1px, transparent 1px),
      linear-gradient(to bottom, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
  }

  @keyframes dash-flow {
    to { stroke-dashoffset: -20; }
  }

  .path-flow {
    stroke-dasharray: 4 6;
    animation: dash-flow 0.8s linear infinite;
  }

  .path-flow-fast {
    stroke-dasharray: 4 6;
    animation: dash-flow 0.4s linear infinite;
  }

  .status-dot {
    position: relative;
  }

  .status-dot::after {
    content: '';
    position: absolute;
    top: -2px; left: -2px; right: -2px; bottom: -2px;
    border-radius: 50%;
    background: inherit;
    opacity: 0.4;
    animation: pulse-ring 2s cubic-bezier(0.215, 0.61, 0.355, 1) infinite;
  }

  @keyframes pulse-ring {
    0% { transform: scale(1); opacity: 0.5; }
    100% { transform: scale(2.5); opacity: 0; }
  }

  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border-focus); border-radius: 4px; }
`;

const lanes: Lane[] = [
  { title: "Dynamic task decomposition", text: "Objective to plan, lanes, and synthesis" },
  { title: "Parallel adaptive routing", text: "Research, analysis, execution, memory, connectors" },
  { title: "Stable mission topology", text: "Durable state transitions and mission history" },
];

const telemetry: TelemetryItem[] = [
  { label: "Status", value: "Visible", icon: ShieldCheck, color: "#3FB950", status: "active" },
  { label: "Missions", value: "Delegated", icon: Activity, color: "#00F0FF", status: "active" },
  { label: "Runtime", value: "Structured", icon: Clock, color: "#A371F7", status: "active" },
  {
    label: "Routing",
    value: "Policy-aware",
    icon: Workflow,
    color: "#F59E0B",
    status: "processing",
  },
];

const nodes: NodeItem[] = [
  {
    id: "registry",
    title: "Mission Registry",
    subtitle: "State, approvals, history",
    detail:
      "Durable storage for mission state, approvals, checkpoints, and resumable execution history.",
    badge: "Ledger",
    icon: Layers3,
    x: 410,
    y: 40,
    color: "#8B949E",
    latency: "4ms",
    status: "active",
  },
  {
    id: "planner",
    title: "Planner Lane",
    subtitle: "Policy-aware planning",
    detail: "Turns intent into structured tasks, sequencing, guardrails, and execution lanes.",
    badge: "Plan",
    icon: Sparkles,
    x: 40,
    y: 220,
    color: "#A371F7",
    latency: "12ms",
    status: "active",
  },
  {
    id: "openchat",
    title: "AverQel Core",
    subtitle: "Mission routing center",
    detail:
      "The core coordinates planning, subagents, memory, proactive jobs, and connectors from one mission surface.",
    badge: "Core",
    icon: Brain,
    x: 410,
    y: 220,
    color: "#00F0FF",
    latency: "2ms",
    isMain: true,
    status: "active",
  },
  {
    id: "swarm",
    title: "Subagent Swarm",
    subtitle: "Research, write, execute",
    detail: "Specialized parallel workers branch from the core and return results for synthesis.",
    badge: "Swarm",
    icon: GitBranch,
    x: 760,
    y: 130,
    color: "#3FB950",
    latency: "45ms",
    status: "processing",
  },
  {
    id: "memory",
    title: "Durable Memory",
    subtitle: "Persisted mission state",
    detail:
      "Context, artifacts, and prior decisions remain available across longer-running workflows.",
    badge: "State",
    icon: Database,
    x: 40,
    y: 390,
    color: "#58A6FF",
    latency: "8ms",
    status: "active",
  },
  {
    id: "proactive",
    title: "Proactive Workspace",
    subtitle: "Follow-up jobs",
    detail:
      "Background jobs continue after the live interaction for reminders, follow-ups, and scheduled tasks.",
    badge: "Work",
    icon: Workflow,
    x: 410,
    y: 400,
    color: "#D29922",
    latency: "--",
    status: "idle",
  },
  {
    id: "connectors",
    title: "Connector Mesh",
    subtitle: "Slack, Drive, GitHub, Gmail",
    detail:
      "External tools attach through a single connector layer so missions can read, write, and act outside the app.",
    badge: "Sync",
    icon: Cable,
    x: 760,
    y: 310,
    color: "#8957E5",
    latency: "112ms",
    status: "active",
  },
];

const drawPath = (startX: number, startY: number, endX: number, endY: number) => {
  const curvature = 0.5;
  const controlPointX1 = startX + (endX - startX) * curvature;
  const controlPointX2 = endX - (endX - startX) * curvature;
  return `M ${startX} ${startY} C ${controlPointX1} ${startY}, ${controlPointX2} ${endY}, ${endX} ${endY}`;
};

const CANVAS_WIDTH = 1100;
const CANVAS_HEIGHT = 560;
const MIN_SCALE = 0.38;
const MAX_SCALE = 1.35;

const getDefaultScale = (width: number) => {
  if (width < 640) return 0.44;
  if (width < 1024) return 0.62;
  return 1;
};

export default function GlobalOrchestrationShowcase() {
  const [activeId, setActiveId] = useState("openchat");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [viewport, setViewport] = useState({ x: 0, y: 0, scale: 1 });
  const [isDraggingCanvas, setIsDraggingCanvas] = useState(false);
  const [isPinchingCanvas, setIsPinchingCanvas] = useState(false);
  const logIndexRef = useRef(0);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const pointersRef = useRef(new Map<number, { x: number; y: number }>());
  const dragStartRef = useRef<{ x: number; y: number; originX: number; originY: number } | null>(
    null,
  );
  const pinchRef = useRef<{
    distance: number;
    scale: number;
    centerX: number;
    centerY: number;
  } | null>(null);

  const activeNode = nodes.find((node) => node.id === activeId) ?? nodes[2];

  const centerViewport = (scale: number) => {
    const container = canvasRef.current;
    if (!container) return { x: 0, y: 0, scale };
    const bounds = container.getBoundingClientRect();
    return {
      x: (bounds.width - CANVAS_WIDTH * scale) / 2,
      y: (bounds.height - CANVAS_HEIGHT * scale) / 2,
      scale,
    };
  };

  const logMessages = [
    "AverQel Core: routes the request into a visible mission.",
    "Planner Lane: shapes the objective into structured execution lanes.",
    "Subagent Swarm: specializes research, analysis, and execution work.",
    "Connector Mesh: provides external system access through safe boundaries.",
    "Durable Memory: preserves state across longer-running workflows.",
    "Mission Registry: records approvals, checkpoints, and resumable history.",
  ];

  useVisibilityAwareInterval(() => {
    const nextIndex = logIndexRef.current % logMessages.length;
    logIndexRef.current += 1;
    setLogs((prev) => {
      return [
        ...prev.slice(-3),
        {
          time: `STEP_${nextIndex + 1}`,
          msg: logMessages[nextIndex],
        },
      ];
    });
  }, 3000);

  useEffect(() => {
    const syncViewport = () => {
      const defaultScale = getDefaultScale(window.innerWidth);
      setViewport((current) => {
        const nextScale = current.scale === 1 ? defaultScale : current.scale;
        return centerViewport(nextScale);
      });
    };

    syncViewport();
    window.addEventListener("resize", syncViewport);
    return () => window.removeEventListener("resize", syncViewport);
  }, []);

  const clampViewport = (next: { x: number; y: number; scale: number }) => {
    const container = canvasRef.current;
    if (!container) return next;
    const bounds = container.getBoundingClientRect();
    const scaledWidth = CANVAS_WIDTH * next.scale;
    const scaledHeight = CANVAS_HEIGHT * next.scale;
    const minX = Math.min(0, bounds.width - scaledWidth);
    const minY = Math.min(0, bounds.height - scaledHeight);
    const maxX = Math.max(0, bounds.width - scaledWidth);
    const maxY = Math.max(0, bounds.height - scaledHeight);

    return {
      ...next,
      x: Math.min(maxX + 120, Math.max(minX - 120, next.x)),
      y: Math.min(maxY + 120, Math.max(minY - 120, next.y)),
    };
  };

  const updateScaleAtPoint = (nextScale: number, clientX: number, clientY: number) => {
    const container = canvasRef.current;
    if (!container) return;
    const bounds = container.getBoundingClientRect();

    setViewport((current) => {
      const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, nextScale));
      const offsetX = clientX - bounds.left;
      const offsetY = clientY - bounds.top;
      const worldX = (offsetX - current.x) / current.scale;
      const worldY = (offsetY - current.y) / current.scale;
      return clampViewport({
        scale,
        x: offsetX - worldX * scale,
        y: offsetY - worldY * scale,
      });
    });
  };

  const handleWheel = (event: ReactWheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const delta = event.deltaY < 0 ? 1.08 : 0.92;
    updateScaleAtPoint(viewport.scale * delta, event.clientX, event.clientY);
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    event.currentTarget.setPointerCapture(event.pointerId);

    if (pointersRef.current.size === 1) {
      dragStartRef.current = {
        x: event.clientX,
        y: event.clientY,
        originX: viewport.x,
        originY: viewport.y,
      };
      setIsDraggingCanvas(true);
    }

    if (pointersRef.current.size === 2) {
      setIsPinchingCanvas(true);
      const [a, b] = Array.from(pointersRef.current.values());
      pinchRef.current = {
        distance: Math.hypot(b.x - a.x, b.y - a.y),
        scale: viewport.scale,
        centerX: (a.x + b.x) / 2,
        centerY: (a.y + b.y) / 2,
      };
      dragStartRef.current = null;
    }
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!pointersRef.current.has(event.pointerId)) return;
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });

    if (pointersRef.current.size === 2 && pinchRef.current) {
      const [a, b] = Array.from(pointersRef.current.values());
      const distance = Math.hypot(b.x - a.x, b.y - a.y);
      const centerX = (a.x + b.x) / 2;
      const centerY = (a.y + b.y) / 2;
      const nextScale = pinchRef.current.scale * (distance / pinchRef.current.distance);
      updateScaleAtPoint(nextScale, centerX, centerY);
      return;
    }

    const dragStart = dragStartRef.current;
    if (dragStart && pointersRef.current.size === 1) {
      const deltaX = event.clientX - dragStart.x;
      const deltaY = event.clientY - dragStart.y;
      setViewport((current) =>
        clampViewport({
          ...current,
          x: dragStart.originX + deltaX,
          y: dragStart.originY + deltaY,
        }),
      );
    }
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    pointersRef.current.delete(event.pointerId);
    event.currentTarget.releasePointerCapture(event.pointerId);
    if (pointersRef.current.size < 2) {
      pinchRef.current = null;
      setIsPinchingCanvas(false);
    }
    if (pointersRef.current.size === 0) {
      dragStartRef.current = null;
      setIsDraggingCanvas(false);
    }
  };

  return (
    <section className={landingSectionShellClass}>
      <style>{styles}</style>

      <div className={`${landingContentClass} space-y-6`}>
        <header className="flex flex-col items-center justify-between gap-4 pb-3 2xl:flex-row 2xl:items-start 2xl:gap-8">
          <div className={`${landingHeaderWrapClass} mb-0 space-y-3`}>
            <div
              className={`${landingEyebrowClass} flex items-center justify-center gap-3 text-[#00F0FF]`}
            >
              <ShieldCheck size={14} />
              <span>GLOBAL_ORCHESTRATION_LAYER</span>
            </div>
            <h1
              className={`${landingSectionTitleClass} ${landingTitleGradientBySection.orchestration} max-w-4xl`}
            >
              One operator-grade mission brain for chat, subagents, proactive work, and connectors.
            </h1>
            <p className={`${landingSectionLeadClass} max-w-3xl text-[#8B949E] lg:max-w-2xl`}>
              AverQel exposes a federated orchestration layer that routes work across chat, planner
              lanes, subagents, durable memory, proactive tasks, connector handoffs, and approval
              gates. The same mission can be inspected inline inside DeepSpace or through the full
              orchestration control room without losing runtime clarity.
            </p>
            <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link
                href="/dashboard/orchestration"
                className="inline-flex items-center gap-2 rounded-full border border-[#00F0FF]/35 bg-[#00F0FF]/10 px-5 py-2.5 text-xs font-bold tracking-[0.18em] text-[#D9FBFF] uppercase transition hover:border-[#00F0FF]/60 hover:bg-[#00F0FF]/15"
              >
                Open Orchestration
                <ChevronRight size={14} />
              </Link>
              <Link
                href="/documentation/orchestration"
                className="inline-flex items-center gap-2 rounded-full border border-[#2E3846] bg-[#0E1116] px-5 py-2.5 text-xs font-bold tracking-[0.18em] text-[#C9D1D9] uppercase transition hover:border-[#8B949E] hover:text-white"
              >
                Read the Architecture
              </Link>
            </div>
          </div>
        </header>

        <div className="grid items-start gap-8 xl:grid-cols-[minmax(0,1.18fr)_minmax(320px,0.42fr)]">
          <section className="relative flex w-full flex-col overflow-hidden rounded-xl border border-[#1E2430] bg-[#0E1116] shadow-2xl">
            <div className="flex items-center justify-between border-b border-[#1E2430] bg-[#06080A] px-4 py-3">
              <div className="flex items-center gap-3">
                <Activity size={16} className="text-[#8B949E]" />
                <h3 className="text-xs font-semibold tracking-widest text-[#8B949E] uppercase">
                  Mission Control View
                </h3>
              </div>
              <div className="flex items-center gap-2">
                <div className="flex items-center gap-1 rounded-full border border-[#243245] bg-[#0d1520] p-1">
                  <button
                    type="button"
                    aria-label="Zoom out"
                    onClick={() =>
                      updateScaleAtPoint(
                        viewport.scale * 0.9,
                        window.innerWidth / 2,
                        window.innerHeight / 2,
                      )
                    }
                    className="flex h-7 w-7 items-center justify-center rounded-full text-[#8B949E] transition hover:bg-white/[0.06] hover:text-[#F0F6FC]"
                  >
                    <Minus size={12} />
                  </button>
                  <button
                    type="button"
                    aria-label="Reset canvas"
                    onClick={() => setViewport(centerViewport(getDefaultScale(window.innerWidth)))}
                    className="flex h-7 w-7 items-center justify-center rounded-full text-[#8B949E] transition hover:bg-white/[0.06] hover:text-[#F0F6FC]"
                  >
                    <RotateCcw size={12} />
                  </button>
                  <button
                    type="button"
                    aria-label="Zoom in"
                    onClick={() =>
                      updateScaleAtPoint(
                        viewport.scale * 1.1,
                        window.innerWidth / 2,
                        window.innerHeight / 2,
                      )
                    }
                    className="flex h-7 w-7 items-center justify-center rounded-full text-[#8B949E] transition hover:bg-white/[0.06] hover:text-[#F0F6FC]"
                  >
                    <Plus size={12} />
                  </button>
                </div>
                <div className="flex items-center gap-2 rounded-full bg-[#1E2430] px-3 py-1">
                  <div className="status-dot h-1.5 w-1.5 rounded-full bg-[#3FB950]" />
                  <span className="font-mono text-[9px] text-[#F0F6FC]">INTERACTIVE_MAP</span>
                </div>
              </div>
            </div>

            <div
              ref={canvasRef}
              className={`blueprint-grid relative h-[330px] w-full touch-none overflow-hidden sm:h-[430px] lg:h-[560px] ${isDraggingCanvas ? "cursor-grabbing" : "cursor-grab"}`}
              onWheel={handleWheel}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
            >
              <div
                className="absolute top-0 left-0 origin-top-left"
                style={{
                  width: `${CANVAS_WIDTH}px`,
                  height: `${CANVAS_HEIGHT}px`,
                  transform: `translate3d(${viewport.x}px, ${viewport.y}px, 0) scale(${viewport.scale})`,
                  transition:
                    isDraggingCanvas || isPinchingCanvas ? "none" : "transform 180ms ease-out",
                }}
              >
                <svg className="pointer-events-none absolute inset-0 z-0 h-full w-full">
                  {nodes.map((node) => {
                    if (node.id === "openchat") return null;

                    const coreNode = nodes.find((n) => n.id === "openchat")!;
                    const isLeft = node.x < coreNode.x;
                    const isTop = node.y < coreNode.y;
                    const isBottom = node.y > coreNode.y;
                    const nodeWidth = 280;
                    const nodeHeight = 80;

                    let startX = 0;
                    let startY = 0;
                    let endX = 0;
                    let endY = 0;

                    if (isLeft) {
                      startX = node.x + nodeWidth;
                      startY = node.y + nodeHeight / 2;
                      endX = coreNode.x;
                      endY = coreNode.y + nodeHeight / 2;
                    } else if (node.x > coreNode.x) {
                      startX = node.x;
                      startY = node.y + nodeHeight / 2;
                      endX = coreNode.x + nodeWidth;
                      endY = coreNode.y + nodeHeight / 2;
                    } else if (isTop) {
                      startX = node.x + nodeWidth / 2;
                      startY = node.y + nodeHeight;
                      endX = coreNode.x + nodeWidth / 2;
                      endY = coreNode.y;
                    } else if (isBottom) {
                      startX = node.x + nodeWidth / 2;
                      startY = node.y;
                      endX = coreNode.x + nodeWidth / 2;
                      endY = coreNode.y + nodeHeight;
                    }

                    const isActivePath = activeId === node.id || activeId === "openchat";

                    return (
                      <g key={`path-${node.id}`}>
                        <path
                          d={drawPath(startX, startY, endX, endY)}
                          fill="none"
                          stroke="#1E2430"
                          strokeWidth="2"
                        />
                        {(node.status === "active" || node.status === "processing") && (
                          <path
                            d={drawPath(startX, startY, endX, endY)}
                            fill="none"
                            stroke={node.color}
                            strokeWidth={isActivePath ? "3" : "1.5"}
                            opacity={isActivePath ? "0.8" : "0.3"}
                            className={
                              node.status === "processing" ? "path-flow-fast" : "path-flow"
                            }
                          />
                        )}
                      </g>
                    );
                  })}
                </svg>

                {nodes.map((node) => {
                  const Icon = node.icon;
                  const isHovered = activeId === node.id;

                  const nodeStyle = {
                    left: `${node.x}px`,
                    top: `${node.y}px`,
                    ["--tw-ring-color" as never]: node.color,
                  } as CSSProperties;

                  return (
                    <button
                      key={node.id}
                      type="button"
                      onMouseEnter={() => setActiveId(node.id)}
                      onMouseLeave={() => setActiveId("openchat")}
                      className={`absolute z-10 w-[280px] cursor-default rounded-lg border text-left transition-all duration-200 ${
                        node.isMain
                          ? "border-[#00F0FF]/40 bg-[#0A1017] shadow-[0_0_30px_rgba(0,240,255,0.05)]"
                          : "border-[#1E2430] bg-[#11141A] hover:border-[#2E3846]"
                      } ${isHovered ? "ring-1 ring-offset-2 ring-offset-[#06080A]" : ""}`}
                      style={nodeStyle}
                    >
                      <div className="flex h-full flex-col justify-between gap-3 p-4">
                        <div className="flex items-start justify-between">
                          <div className="flex items-center gap-2">
                            <div className="rounded border border-[#1E2430] bg-[#06080A] p-1.5">
                              <Icon size={16} color={node.color} />
                            </div>
                            <div>
                              <h4
                                className={`text-xs font-semibold ${node.isMain ? "text-[#00F0FF]" : "text-[#F0F6FC]"}`}
                              >
                                {node.title}
                              </h4>
                            </div>
                          </div>
                          <div className="rounded border border-[#1E2430] bg-[#06080A] px-2 py-0.5 font-mono text-[9px] font-bold tracking-widest text-[#8B949E] uppercase">
                            {node.badge}
                          </div>
                        </div>

                        <p className="pr-2 text-[11px] leading-relaxed text-[#8B949E]">
                          {node.subtitle}
                        </p>

                        <div className="mt-1 flex items-center justify-between border-t border-[#1E2430]/50 pt-2.5">
                          <div className="flex items-center gap-1.5">
                            <div
                              className={`h-1.5 w-1.5 rounded-full ${
                                node.status === "active"
                                  ? "status-dot bg-[#3FB950]"
                                  : node.status === "processing"
                                    ? "animate-pulse bg-[#D29922]"
                                    : "bg-[#484F58]"
                              }`}
                            />
                            <span className="font-mono text-[9px] text-[#8B949E] uppercase">
                              {node.status}
                            </span>
                          </div>
                          <div className="flex items-center gap-1 text-[#8B949E]">
                            <Clock size={10} />
                            <span className="font-mono text-[9px]">{node.latency}</span>
                          </div>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="mt-0 border-t border-[#1E2430] bg-[#06080A] p-4 sm:p-5">
              <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] font-bold tracking-wider text-[#8B949E] uppercase">
                      Active Lane Detail
                    </span>
                    <span className="rounded bg-[#1E2430] px-2 py-0.5 text-[9px] font-semibold text-[#00F0FF] uppercase">
                      {activeNode.badge}
                    </span>
                  </div>
                  <h4 className="text-sm font-semibold text-[#F0F6FC]">{activeNode.title}</h4>
                  <p className="max-w-4xl text-xs leading-relaxed text-[#8B949E]">
                    {activeNode.detail}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2 self-end md:self-center">
                  <span className="font-mono text-[10px] text-[#8B949E]">NODE_STATUS:</span>
                  <span className="font-mono text-xs font-bold" style={{ color: activeNode.color }}>
                    {activeNode.status.toUpperCase()}
                  </span>
                </div>
              </div>
            </div>
          </section>

          <aside className="space-y-6">
            <div className="space-y-4 rounded-xl border border-[#1E2430] bg-[#0E1116] p-5">
              <div className="flex items-center justify-between border-b border-[#1E2430] pb-3">
                <div className="flex items-center gap-2">
                  <Terminal size={14} className="text-[#00F0FF]" />
                  <span className="font-mono text-xs font-bold tracking-wider text-[#F0F6FC] uppercase">
                    System Event Log
                  </span>
                </div>
                <div className="status-dot h-1.5 w-1.5 rounded-full bg-[#3FB950]" />
              </div>

              <div className="h-[90px] space-y-2 overflow-y-auto font-mono text-[11px] text-[#8B949E]">
                {logs.length === 0 ? (
                  <div className="text-[#484F58]">Conceptual mission events appear here.</div>
                ) : (
                  logs.map((log, idx) => (
                    <div key={`${log.time}-${idx}`} className="flex gap-2">
                      <span className="shrink-0 text-[#484F58]">[{log.time}]</span>
                      <span className="break-all text-[#C9D1D9]">{log.msg}</span>
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className="space-y-3">
              <p className="px-1 font-mono text-[10px] font-bold tracking-widest text-[#8B949E] uppercase">
                Lanes Overview
              </p>
              {lanes.map((lane) => (
                <div
                  key={lane.title}
                  className="space-y-1 rounded-lg border border-[#1E2430] bg-[#0E1116] p-4 transition-colors hover:border-[#2E3846]"
                >
                  <div className="flex items-center justify-between">
                    <h5 className="text-xs font-semibold text-[#F0F6FC]">{lane.title}</h5>
                    <ChevronRight size={12} className="text-[#8B949E]" />
                  </div>
                  <p className="text-[11px] leading-relaxed text-[#8B949E]">{lane.text}</p>
                </div>
              ))}
            </div>

            <div className="grid w-full gap-0 overflow-hidden rounded-lg border border-[#1E2430] bg-[#0E1116] sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
              {telemetry.map((item, index) => {
                const Icon = item.icon;
                return (
                  <div
                    key={item.label}
                    className={`flex items-center justify-between gap-3 px-4 py-3 ${
                      index % 2 === 0
                        ? "sm:border-r sm:border-[#1E2430] xl:border-r-0 2xl:border-r 2xl:border-[#1E2430]"
                        : ""
                    } ${index < telemetry.length - 2 ? "border-b border-[#1E2430] xl:border-b xl:border-[#1E2430] 2xl:border-b-0" : ""}`}
                  >
                    <div className="space-y-1">
                      <div className="text-[9px] font-bold tracking-wider text-[#8B949E] uppercase">
                        {item.label}
                      </div>
                      <div
                        className="flex items-center gap-2 font-mono text-sm"
                        style={{ color: item.color }}
                      >
                        <div
                          className="status-dot h-1.5 w-1.5 rounded-full"
                          style={{ backgroundColor: item.color }}
                        />
                        {item.value}
                      </div>
                    </div>
                    <Icon size={13} className="shrink-0 opacity-90" style={{ color: item.color }} />
                  </div>
                );
              })}
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}
