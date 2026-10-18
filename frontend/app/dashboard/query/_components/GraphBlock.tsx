"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  Copy,
  Download,
  Move,
  Pencil,
  Plus,
  Redo2,
  RotateCcw,
  Undo2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

import type { StreamDiagramBlock } from "../_lib/stream-protocol";

interface GraphBlockProps {
  block: StreamDiagramBlock & { graph: NonNullable<StreamDiagramBlock["graph"]> };
  onChange?: (block: StreamDiagramBlock) => void | Promise<void>;
}

type Graph = NonNullable<StreamDiagramBlock["graph"]> & {
  drawings?: Array<{ d: string; color?: string; width?: number }>;
};
type PositionedNode = Graph["nodes"][number] & {
  x: number;
  y: number;
  width: number;
  height: number;
};

const SVG_WIDTH = 720;
const SVG_HEIGHT = 360;
const DEFAULT_NODE_WIDTH = 148;
const DEFAULT_NODE_HEIGHT = 52;

/** Portable diagram canvas with movable/resizable nodes, connectors, grouping,
 * alignment, zoom and freehand paths. The graph JSON remains exportable and
 * can be embedded in both chat and the note editor. */
export default function GraphBlock({ block, onChange }: GraphBlockProps) {
  const graph = block.graph as Graph;
  const [draft, setDraft] = useState<Graph>(() => cloneGraph(graph));
  const [editing, setEditing] = useState(false);
  const [selectedNode, setSelectedNode] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [drawing, setDrawing] = useState(false);
  const [activePath, setActivePath] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [history, setHistory] = useState<Graph[]>([]);
  const [future, setFuture] = useState<Graph[]>([]);
  const [importError, setImportError] = useState<string | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const importInputRef = useRef<HTMLInputElement>(null);
  const dragRef = useRef<{ kind: "move" | "resize"; id: string; dx: number; dy: number } | null>(
    null,
  );

  useEffect(() => {
    queueMicrotask(() => {
      setDraft(cloneGraph(graph));
      setSelectedNode(null);
      setActivePath(null);
      setHistory([]);
      setFuture([]);
    });
  }, [block.id, graph]);

  const positions = useMemo(() => computeLayout(draft, SVG_WIDTH, SVG_HEIGHT), [draft]);
  const positionMap = useMemo(() => new Map(positions.map((node) => [node.id, node])), [positions]);
  const selected = selectedNode ? positionMap.get(selectedNode) : undefined;
  const updateGraph = (updater: (current: Graph) => Graph) =>
    setDraft((current) => {
      const next = updater(current);
      if (JSON.stringify(next) === JSON.stringify(current)) return current;
      setHistory((previous) => [...previous, cloneGraph(current)].slice(-40));
      setFuture([]);
      return next;
    });

  const undo = () => {
    setHistory((previous) => {
      const prior = previous.at(-1);
      if (!prior) return previous;
      setDraft((current) => {
        setFuture((next) => [cloneGraph(current), ...next].slice(0, 40));
        return cloneGraph(prior);
      });
      return previous.slice(0, -1);
    });
  };

  const redo = () => {
    setFuture((previous) => {
      const next = previous[0];
      if (!next) return previous;
      setDraft((current) => {
        setHistory((prior) => [...prior, cloneGraph(current)].slice(-40));
        return cloneGraph(next);
      });
      return previous.slice(1);
    });
  };

  const startPointer = (
    event: React.PointerEvent<SVGElement>,
    id: string,
    kind: "move" | "resize",
  ) => {
    if (!editing || drawing) return;
    event.stopPropagation();
    const node = positionMap.get(id);
    if (!node || !svgRef.current) return;
    const point = toSvgPoint(svgRef.current, event.clientX, event.clientY);
    dragRef.current = { kind, id, dx: point.x - node.x, dy: point.y - node.y };
    setSelectedNode(id);
    svgRef.current.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!svgRef.current) return;
    if (drawing && activePath !== null) {
      const point = toSvgPoint(svgRef.current, event.clientX, event.clientY);
      setActivePath((current) =>
        current ? `${current} L ${point.x.toFixed(1)} ${point.y.toFixed(1)}` : current,
      );
      return;
    }
    const drag = dragRef.current;
    if (!drag) return;
    const point = toSvgPoint(svgRef.current, event.clientX, event.clientY);
    updateGraph((current) => ({
      ...current,
      nodes: current.nodes.map((node) => {
        if (node.id !== drag.id) return node;
        if (drag.kind === "resize") {
          const currentPosition = positionMap.get(node.id);
          return {
            ...node,
            width: clamp(Math.abs(point.x - (currentPosition?.x ?? point.x)) * 2, 90, 280),
            height: clamp(Math.abs(point.y - (currentPosition?.y ?? point.y)) * 2, 42, 180),
          };
        }
        return {
          ...node,
          x: clamp(point.x - drag.dx, 30, SVG_WIDTH - 30),
          y: clamp(point.y - drag.dy, 30, SVG_HEIGHT - 30),
        };
      }),
    }));
  };

  const finishPointer = (event: React.PointerEvent<SVGSVGElement>) => {
    if (drawing && activePath) {
      updateGraph((current) => ({
        ...current,
        drawings: [...(current.drawings ?? []), { d: activePath, color: "currentColor", width: 2 }],
      }));
      setActivePath(null);
    }
    dragRef.current = null;
    if (svgRef.current?.hasPointerCapture(event.pointerId))
      svgRef.current.releasePointerCapture(event.pointerId);
  };

  const startDrawing = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!editing || !drawing || !svgRef.current) return;
    if (event.target instanceof Element && event.target.closest("[data-graph-node]")) return;
    const point = toSvgPoint(svgRef.current, event.clientX, event.clientY);
    setActivePath(`M ${point.x.toFixed(1)} ${point.y.toFixed(1)}`);
    svgRef.current.setPointerCapture(event.pointerId);
  };

  const addNode = () => {
    const nextIndex = draft.nodes.length + 1;
    updateGraph((current) => ({
      ...current,
      nodes: [
        ...current.nodes,
        {
          id: `node-${nextIndex}`,
          label: `Node ${nextIndex}`,
          category: "component",
          x: SVG_WIDTH / 2,
          y: 70 + ((nextIndex - 1) % 4) * 70,
          width: DEFAULT_NODE_WIDTH,
          height: DEFAULT_NODE_HEIGHT,
        },
      ],
    }));
  };

  const addEdge = () => {
    if (draft.nodes.length < 2) return;
    const source = draft.nodes[draft.nodes.length - 2]!.id;
    const target = draft.nodes[draft.nodes.length - 1]!.id;
    updateGraph((current) => ({
      ...current,
      edges: current.edges.some((edge) => edge.source === source && edge.target === target)
        ? current.edges
        : [...current.edges, { source, target, label: "", style: "solid" }],
    }));
  };

  const alignSelected = (axis: "x" | "y") => {
    if (!selectedNode) return;
    const selectedPosition = positionMap.get(selectedNode);
    if (!selectedPosition) return;
    updateGraph((current) => ({
      ...current,
      nodes: current.nodes.map((node) => ({ ...node, [axis]: selectedPosition[axis] })),
    }));
  };

  const groupSelected = () => {
    if (!selectedNode) return;
    updateGraph((current) => ({
      ...current,
      nodes: current.nodes.map((node) => ({
        ...node,
        group_id: node.group_id || `group-${selectedNode}`,
      })),
    }));
  };

  const downloadGraph = () => {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(draft, null, 2)], { type: "application/json" }),
    );
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${slugify(block.title ?? "diagram") || "diagram"}.draw.json`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const importGraph = async (file?: File) => {
    if (!file) return;
    setImportError(null);
    if (file.size > 2_000_000) {
      setImportError("Diagram files must be smaller than 2 MB.");
      return;
    }
    try {
      const parsed = JSON.parse(await file.text()) as unknown;
      const candidate =
        parsed && typeof parsed === "object" && "graph" in parsed
          ? (parsed as { graph: unknown }).graph
          : parsed;
      const imported = normalizeImportedGraph(candidate);
      updateGraph(() => imported);
      setEditing(true);
    } catch {
      setImportError("That file is not a valid DeepSpace .draw.json graph.");
    } finally {
      if (importInputRef.current) importInputRef.current.value = "";
    }
  };

  const copyGraph = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(draft, null, 2));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1400);
    } catch {
      setCopied(false);
    }
  };

  const toggleEditing = () => {
    if (!editing) {
      const laidOut = computeLayout(draft, SVG_WIDTH, SVG_HEIGHT);
      updateGraph((current) => ({
        ...current,
        nodes: current.nodes.map((node) => {
          const position = laidOut.find((candidate) => candidate.id === node.id);
          return position
            ? {
                ...node,
                x: position.x,
                y: position.y,
                width: node.width ?? position.width,
                height: node.height ?? position.height,
              }
            : node;
        }),
      }));
    }
    if (editing) {
      void onChange?.({
        ...block,
        source: "graph_json",
        syntax: JSON.stringify(draft),
        graph: draft,
        revision: ((block as StreamDiagramBlock & { revision?: number }).revision ?? 0) + 1,
      });
    }
    setEditing((current) => !current);
  };

  return (
    <section
      className="theme-code-surface min-w-0 overflow-hidden rounded-[1.45rem] p-4"
      aria-label={block.title ?? "Architecture graph"}
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-foreground/70 flex items-center gap-2 text-xs font-semibold tracking-[0.12em] uppercase">
          <Move className="h-3.5 w-3.5" /> {editing ? "Canvas editor" : "Diagram canvas"}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => setZoom((current) => clamp(current - 0.1, 0.7, 1.6))}
            className="visual-block-action rounded-lg p-2"
            aria-label="Zoom out"
          >
            <ZoomOut size={14} />
          </button>
          <span className="text-foreground/55 min-w-12 text-center text-[11px] tabular-nums">
            {Math.round(zoom * 100)}%
          </span>
          <button
            type="button"
            onClick={() => setZoom((current) => clamp(current + 0.1, 0.7, 1.6))}
            className="visual-block-action rounded-lg p-2"
            aria-label="Zoom in"
          >
            <ZoomIn size={14} />
          </button>
          <button
            type="button"
            onClick={toggleEditing}
            className={`visual-block-action inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px] ${editing ? "visual-block-action--active" : ""}`}
          >
            <Pencil size={13} /> {editing ? "Done" : "Edit canvas"}
          </button>
          <button
            type="button"
            onClick={downloadGraph}
            className="visual-block-action rounded-lg p-2"
            aria-label="Download diagram JSON"
          >
            <Download size={14} />
          </button>
          <button
            type="button"
            onClick={() => importInputRef.current?.click()}
            className="visual-block-action rounded-lg px-2.5 py-1.5 text-[11px]"
            aria-label="Import diagram file"
          >
            Import .draw.json
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept=".draw,.json,application/json"
            className="hidden"
            aria-label="Select DeepSpace draw file"
            onChange={(event) => void importGraph(event.currentTarget.files?.[0])}
          />
          <button
            type="button"
            onClick={() => void copyGraph()}
            className="visual-block-action rounded-lg p-2"
            aria-label="Copy diagram JSON"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />}
          </button>
          {editing ? (
            <>
              <button
                type="button"
                onClick={undo}
                disabled={!history.length}
                className="visual-block-action rounded-lg p-2 disabled:opacity-40"
                aria-label="Undo diagram edit"
              >
                <Undo2 size={14} />
              </button>
              <button
                type="button"
                onClick={redo}
                disabled={!future.length}
                className="visual-block-action rounded-lg p-2 disabled:opacity-40"
                aria-label="Redo diagram edit"
              >
                <Redo2 size={14} />
              </button>
            </>
          ) : null}
        </div>
      </div>
      {importError ? (
        <p className="text-xs text-rose-400" role="alert">
          {importError}
        </p>
      ) : null}
      {editing ? (
        <div className="bg-background/40 mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-black/5 p-2 text-[11px] dark:border-white/8">
          <button
            type="button"
            onClick={addNode}
            className="visual-block-action inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5"
          >
            <Plus size={13} /> Node
          </button>
          <button
            type="button"
            onClick={addEdge}
            className="visual-block-action inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5"
          >
            ↗ Edge
          </button>
          <button
            type="button"
            onClick={() => setDrawing((current) => !current)}
            className={`visual-block-action inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 ${drawing ? "visual-block-action--active" : ""}`}
          >
            ✎ Freehand
          </button>
          <button
            type="button"
            onClick={() => alignSelected("x")}
            disabled={!selectedNode}
            className="visual-block-action rounded-lg px-2.5 py-1.5 disabled:opacity-40"
          >
            Align X
          </button>
          <button
            type="button"
            onClick={() => alignSelected("y")}
            disabled={!selectedNode}
            className="visual-block-action rounded-lg px-2.5 py-1.5 disabled:opacity-40"
          >
            Align Y
          </button>
          <button
            type="button"
            onClick={groupSelected}
            disabled={!selectedNode}
            className="visual-block-action rounded-lg px-2.5 py-1.5 disabled:opacity-40"
          >
            Group
          </button>
          <button
            type="button"
            onClick={() => {
              setDraft(cloneGraph(graph));
              setHistory([]);
              setFuture([]);
            }}
            className="visual-block-action inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5"
          >
            <RotateCcw size={13} /> Reset
          </button>
          {selected ? (
            <span className="text-foreground/55 ml-auto">Selected: {selected.label}</span>
          ) : null}
        </div>
      ) : null}
      <div className="bg-background/30 overflow-x-auto rounded-xl border border-black/5 dark:border-white/8">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
          className="mx-auto h-auto w-full min-w-[560px]"
          role="img"
          aria-label={block.title ?? "Architecture graph"}
          onPointerDown={startDrawing}
          onPointerMove={handlePointerMove}
          onPointerUp={finishPointer}
          onPointerCancel={finishPointer}
        >
          <defs>
            <marker
              id={`arrow-${block.id}`}
              markerWidth="10"
              markerHeight="10"
              refX="8"
              refY="3"
              orient="auto"
              markerUnits="strokeWidth"
            >
              <path d="M0,0 L0,6 L9,3 z" fill="currentColor" className="text-primary/80" />
            </marker>
            <pattern id={`grid-${block.id}`} width="24" height="24" patternUnits="userSpaceOnUse">
              <path d="M 24 0 L 0 0 0 24" fill="none" stroke="currentColor" strokeOpacity="0.055" />
            </pattern>
          </defs>
          <rect
            width={SVG_WIDTH}
            height={SVG_HEIGHT}
            fill={`url(#grid-${block.id})`}
            pointerEvents={drawing ? "all" : "none"}
          />
          <g
            transform={`translate(${(SVG_WIDTH * (1 - zoom)) / 2} ${(SVG_HEIGHT * (1 - zoom)) / 2}) scale(${zoom})`}
          >
            {(draft.drawings ?? []).map((path, index) => (
              <path
                key={`drawing-${index}`}
                d={path.d}
                fill="none"
                stroke={path.color ?? "currentColor"}
                strokeWidth={path.width ?? 2}
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-primary/70"
              />
            ))}
            {activePath ? (
              <path
                d={activePath}
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                className="text-primary/80"
              />
            ) : null}
            {draft.edges.map((edge, index) => {
              const source = positionMap.get(edge.source);
              const target = positionMap.get(edge.target);
              if (!source || !target) return null;
              return (
                <g key={`${edge.source}-${edge.target}-${index}`}>
                  <line
                    x1={source.x}
                    y1={source.y}
                    x2={target.x}
                    y2={target.y}
                    stroke="currentColor"
                    className="text-primary/65"
                    strokeWidth="2"
                    strokeDasharray={
                      edge.style === "dashed" ? "7 5" : edge.style === "dotted" ? "2 5" : undefined
                    }
                    markerEnd={`url(#arrow-${block.id})`}
                  />
                  {edge.label ? (
                    <text
                      x={(source.x + target.x) / 2}
                      y={(source.y + target.y) / 2 - 8}
                      textAnchor="middle"
                      fill="currentColor"
                      className="text-primary/85"
                      fontSize="11"
                    >
                      {edge.label}
                    </text>
                  ) : null}
                </g>
              );
            })}
            {positions.map((node) => {
              const width = node.width;
              const height = node.height;
              const isSelected = selectedNode === node.id;
              return (
                <g
                  key={node.id}
                  transform={`translate(${node.x - width / 2}, ${node.y - height / 2})`}
                  onPointerDown={(event) => startPointer(event, node.id, "move")}
                  onClick={() => setSelectedNode(node.id)}
                  className={editing ? "cursor-move" : undefined}
                  data-graph-node="true"
                >
                  <rect
                    width={width}
                    height={height}
                    rx="16"
                    fill="color-mix(in srgb, var(--primary) 12%, var(--surface-0))"
                    stroke={
                      isSelected
                        ? "var(--primary)"
                        : "color-mix(in srgb, var(--primary) 24%, var(--glass-border))"
                    }
                    strokeWidth={isSelected ? 2.5 : 1}
                  />
                  {node.group_id ? (
                    <rect
                      x="3"
                      y="3"
                      width={width - 6}
                      height={height - 6}
                      rx="13"
                      fill="none"
                      stroke="currentColor"
                      strokeDasharray="4 4"
                      className="text-primary/30"
                    />
                  ) : null}
                  {node.category ? (
                    <text
                      x={width / 2}
                      y={height / 2 - 5}
                      textAnchor="middle"
                      fill="currentColor"
                      className="text-primary/72"
                      fontSize="9"
                      letterSpacing="1.2"
                    >
                      {node.category.toUpperCase()}
                    </text>
                  ) : null}
                  <text
                    x={width / 2}
                    y={node.category ? height / 2 + 12 : height / 2 + 4}
                    textAnchor="middle"
                    fill="currentColor"
                    className="text-foreground"
                    fontSize="12"
                    fontWeight="600"
                  >
                    {node.label}
                  </text>
                  {editing && isSelected ? (
                    <rect
                      x={width - 10}
                      y={height - 10}
                      width="12"
                      height="12"
                      rx="3"
                      fill="var(--primary)"
                      onPointerDown={(event) => startPointer(event, node.id, "resize")}
                      aria-label={`Resize ${node.label}`}
                    />
                  ) : null}
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </section>
  );
}

function normalizeImportedGraph(value: unknown): Graph {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid graph object.");
  }
  const raw = value as Record<string, unknown>;
  if (!Array.isArray(raw.nodes) || !Array.isArray(raw.edges)) {
    throw new Error("Graph nodes and edges are required.");
  }
  if (raw.nodes.length > 200 || raw.edges.length > 500) {
    throw new Error("This graph contains too many elements.");
  }
  const nodes = raw.nodes.map((value, index) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error("Invalid graph node.");
    }
    const node = value as Record<string, unknown>;
    if (typeof node.id !== "string" || typeof node.label !== "string") {
      throw new Error("Graph nodes need text IDs and labels.");
    }
    const numberOrUndefined = (candidate: unknown) =>
      typeof candidate === "number" && Number.isFinite(candidate) ? candidate : undefined;
    return {
      id: node.id.slice(0, 160) || `node-${index + 1}`,
      label: node.label.slice(0, 500),
      ...(typeof node.category === "string" ? { category: node.category.slice(0, 64) } : {}),
      ...(typeof node.group_id === "string" ? { group_id: node.group_id.slice(0, 160) } : {}),
      ...(numberOrUndefined(node.x) === undefined ? {} : { x: numberOrUndefined(node.x) }),
      ...(numberOrUndefined(node.y) === undefined ? {} : { y: numberOrUndefined(node.y) }),
      ...(numberOrUndefined(node.width) === undefined
        ? {}
        : { width: clamp(numberOrUndefined(node.width)!, 48, 800) }),
      ...(numberOrUndefined(node.height) === undefined
        ? {}
        : { height: clamp(numberOrUndefined(node.height)!, 32, 800) }),
    };
  });
  const nodeIds = new Set(nodes.map((node) => node.id));
  const edges = raw.edges.map((value) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error("Invalid graph edge.");
    }
    const edge = value as Record<string, unknown>;
    if (
      typeof edge.source !== "string" ||
      typeof edge.target !== "string" ||
      !nodeIds.has(edge.source) ||
      !nodeIds.has(edge.target)
    ) {
      throw new Error("Graph edges must connect existing nodes.");
    }
    return {
      source: edge.source,
      target: edge.target,
      ...(typeof edge.label === "string" ? { label: edge.label.slice(0, 300) } : {}),
      ...(edge.style === "dashed" || edge.style === "dotted" ? { style: edge.style } : {}),
    };
  });
  const drawings = Array.isArray(raw.drawings)
    ? raw.drawings.slice(0, 200).flatMap((value) => {
        if (!value || typeof value !== "object" || Array.isArray(value)) return [];
        const drawing = value as Record<string, unknown>;
        if (typeof drawing.d !== "string" || drawing.d.length > 8_000) return [];
        return [
          {
            d: drawing.d.replace(/[^MmLlHhVvCcSsQqTtAaZz0-9.,+\-\s]/g, ""),
            ...(typeof drawing.color === "string" && /^#[\da-f]{3,8}$/i.test(drawing.color)
              ? { color: drawing.color }
              : {}),
            ...(typeof drawing.width === "number" && Number.isFinite(drawing.width)
              ? { width: clamp(drawing.width, 1, 24) }
              : {}),
          },
        ];
      })
    : [];
  return {
    layout: raw.layout === "vertical" ? "vertical" : "horizontal",
    nodes,
    edges,
    drawings,
  } as Graph;
}

function computeLayout(graph: Graph, width: number, height: number): PositionedNode[] {
  if (!graph.nodes.length) return [];
  const hasCoordinates = graph.nodes.some(
    (node) => Number.isFinite(node.x) && Number.isFinite(node.y),
  );
  if (hasCoordinates)
    return graph.nodes.map((node, index) => ({
      ...node,
      x: Number.isFinite(node.x) ? Number(node.x) : width / 2,
      y: Number.isFinite(node.y) ? Number(node.y) : 60 + index * 60,
      width: node.width ?? DEFAULT_NODE_WIDTH,
      height: node.height ?? DEFAULT_NODE_HEIGHT,
    }));
  return graph.nodes.map((node, index) => {
    if (graph.layout === "radial") {
      const centerX = width / 2;
      const centerY = height / 2;
      const radius = Math.min(width, height) * 0.28;
      if (index === 0)
        return {
          ...node,
          x: centerX,
          y: centerY,
          width: node.width ?? DEFAULT_NODE_WIDTH,
          height: node.height ?? DEFAULT_NODE_HEIGHT,
        };
      const angle = ((index - 1) / Math.max(graph.nodes.length - 1, 1)) * Math.PI * 2;
      return {
        ...node,
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * radius,
        width: node.width ?? DEFAULT_NODE_WIDTH,
        height: node.height ?? DEFAULT_NODE_HEIGHT,
      };
    }
    if (graph.layout === "vertical")
      return {
        ...node,
        x: width / 2,
        y: (height / (graph.nodes.length + 1)) * (index + 1),
        width: node.width ?? DEFAULT_NODE_WIDTH,
        height: node.height ?? DEFAULT_NODE_HEIGHT,
      };
    return {
      ...node,
      x: (width / (graph.nodes.length + 1)) * (index + 1),
      y: height / 2,
      width: node.width ?? DEFAULT_NODE_WIDTH,
      height: node.height ?? DEFAULT_NODE_HEIGHT,
    };
  });
}

function cloneGraph(graph: NonNullable<StreamDiagramBlock["graph"]>): Graph {
  return JSON.parse(JSON.stringify(graph)) as Graph;
}
function toSvgPoint(svg: SVGSVGElement, clientX: number, clientY: number) {
  const point = svg.createSVGPoint();
  point.x = clientX;
  point.y = clientY;
  const matrix = svg.getScreenCTM();
  if (!matrix) return { x: 0, y: 0 };
  const transformed = point.matrixTransform(matrix.inverse());
  return { x: transformed.x, y: transformed.y };
}
function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}
function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80);
}
