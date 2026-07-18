"use client";

import type { StreamDiagramBlock } from "../_lib/stream-protocol";

interface GraphBlockProps {
  block: StreamDiagramBlock & {
    graph: NonNullable<StreamDiagramBlock["graph"]>;
  };
}

const SVG_WIDTH = 720;
const SVG_HEIGHT = 320;

export default function GraphBlock({ block }: GraphBlockProps) {
  const layout = computeLayout(block.graph, SVG_WIDTH, SVG_HEIGHT);
  const positions = new Map(layout.nodes.map((node) => [node.id, node]));

  return (
    <div className="theme-code-surface min-w-0 overflow-x-auto rounded-[1.45rem] p-4">
      <svg
        viewBox={`0 0 ${SVG_WIDTH} ${SVG_HEIGHT}`}
        className="mx-auto h-auto w-full max-w-full min-w-[320px] sm:min-w-[440px] lg:min-w-[640px]"
        role="img"
        aria-label={block.title ?? "Architecture graph"}
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
        </defs>

        {block.graph.edges.map((edge, index) => {
          const source = positions.get(edge.source);
          const target = positions.get(edge.target);
          if (!source || !target) {
            return null;
          }
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

        {layout.nodes.map((node) => (
          <g key={node.id} transform={`translate(${node.x - 74}, ${node.y - 26})`}>
            <rect
              width="148"
              height="52"
              rx="18"
              fill="color-mix(in srgb, var(--primary) 12%, var(--surface-0))"
              stroke="color-mix(in srgb, var(--primary) 24%, var(--glass-border))"
            />
            {node.category ? (
              <text
                x="74"
                y="16"
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
              x="74"
              y={node.category ? 32 : 29}
              textAnchor="middle"
              fill="currentColor"
              className="text-foreground"
              fontSize="12"
              fontWeight="600"
            >
              {node.label}
            </text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function computeLayout(
  graph: NonNullable<StreamDiagramBlock["graph"]>,
  width: number,
  height: number,
): { nodes: Array<{ id: string; label: string; category?: string | null; x: number; y: number }> } {
  if (graph.nodes.length === 0) {
    return { nodes: [] };
  }

  if (graph.layout === "vertical") {
    const gapY = height / (graph.nodes.length + 1);
    return {
      nodes: graph.nodes.map((node, index) => ({
        ...node,
        x: width / 2,
        y: gapY * (index + 1),
      })),
    };
  }

  if (graph.layout === "radial") {
    const centerX = width / 2;
    const centerY = height / 2;
    const radius = Math.min(width, height) * 0.28;
    return {
      nodes: graph.nodes.map((node, index) => {
        if (index === 0) {
          return { ...node, x: centerX, y: centerY };
        }
        const angle = ((index - 1) / Math.max(graph.nodes.length - 1, 1)) * Math.PI * 2;
        return {
          ...node,
          x: centerX + Math.cos(angle) * radius,
          y: centerY + Math.sin(angle) * radius,
        };
      }),
    };
  }

  const gapX = width / (graph.nodes.length + 1);
  return {
    nodes: graph.nodes.map((node, index) => ({
      ...node,
      x: gapX * (index + 1),
      y: height / 2,
    })),
  };
}
