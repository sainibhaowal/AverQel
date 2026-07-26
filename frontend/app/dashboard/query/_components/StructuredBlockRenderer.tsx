"use client";

import type { StructuredBlock } from "../_lib/stream-protocol";

import ChartBlock from "./ChartBlock";
import DiagramBlock from "./DiagramBlock";
import TableBlock from "./TableBlock";

interface StructuredBlockRendererProps {
  blocks: StructuredBlock[];
  isStreaming?: boolean;
}

export default function StructuredBlockRenderer({
  blocks,
  isStreaming = false,
}: StructuredBlockRendererProps) {
  const additiveBlocks = blocks.filter(
    (block) =>
      block.type === "table" ||
      block.type === "chart" ||
      (block.type === "diagram" && !(isStreaming && block.source !== "graph_json")),
  );

  if (additiveBlocks.length === 0) {
    return null;
  }

  return (
    <div className="space-y-5 sm:space-y-6">
      {additiveBlocks.map((block) => {
        switch (block.type) {
          case "table":
            return (
              <TableBlock
                key={block.id}
                block={{
                  ...block,
                  title: block.title ?? undefined,
                }}
                isStreaming={isStreaming}
              />
            );
          case "chart":
            return <ChartBlock key={block.id} block={block} />;
          case "diagram":
            return <DiagramBlock key={block.id} block={block} isStreaming={isStreaming} />;
          default:
            return null;
        }
      })}
    </div>
  );
}
