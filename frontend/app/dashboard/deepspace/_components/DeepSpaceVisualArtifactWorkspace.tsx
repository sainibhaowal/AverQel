"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import ChartBlock from "../../query/_components/ChartBlock";
import DiagramBlock from "../../query/_components/DiagramBlock";
import GalleryBlock from "../../query/_components/GalleryBlock";
import InfographicBlock from "../../query/_components/InfographicBlock";
import type { StructuredBlock } from "../_lib/deepspace-stream";

import { RichInfoCard } from "./DeepSpaceRichContent";
import VisualBlockExport from "./VisualBlockExport";

type VisualDocument = {
  block_id: string;
  schema_version: number;
  revision: number;
  kind: StructuredBlock["type"];
  data: StructuredBlock;
  source_markdown?: string | null;
  source_mermaid?: string | null;
  assets?: unknown[];
  history?: unknown[];
  undo?: Record<string, unknown>;
};

function parseVisualDocument(value: string): VisualDocument | null {
  try {
    const candidate = JSON.parse(value) as Partial<VisualDocument>;
    if (
      !candidate ||
      typeof candidate !== "object" ||
      typeof candidate.block_id !== "string" ||
      typeof candidate.kind !== "string" ||
      !candidate.data ||
      typeof candidate.data !== "object"
    ) {
      return null;
    }
    const data = candidate.data as StructuredBlock;
    if (data.id !== candidate.block_id || data.type !== candidate.kind) return null;
    return {
      block_id: candidate.block_id,
      schema_version: Number(candidate.schema_version ?? 1),
      revision: Number(candidate.revision ?? (data as { revision?: number }).revision ?? 0),
      kind: candidate.kind as StructuredBlock["type"],
      data,
      source_markdown: candidate.source_markdown ?? null,
      source_mermaid: candidate.source_mermaid ?? null,
      assets: candidate.assets ?? [],
      history: candidate.history ?? [],
      undo: candidate.undo ?? {},
    };
  } catch {
    return null;
  }
}

export function isVisualArtifactDocument(value: string): boolean {
  return parseVisualDocument(value) !== null;
}

export default function DeepSpaceVisualArtifactWorkspace({
  value,
  onChange,
  onBlockChange,
}: {
  value: string;
  onChange: (value: string) => void;
  onBlockChange: (block: StructuredBlock) => void | Promise<void>;
}) {
  const [error, setError] = useState<string | null>(null);
  const pendingBlockRef = useRef<StructuredBlock | null>(null);
  const syncingBlockRef = useRef(false);
  const onBlockChangeRef = useRef(onBlockChange);
  useEffect(() => {
    onBlockChangeRef.current = onBlockChange;
  }, [onBlockChange]);

  const document = parseVisualDocument(value);
  if (!document) return null;

  const flushBlockChanges = async () => {
    if (syncingBlockRef.current) return;
    syncingBlockRef.current = true;
    try {
      while (pendingBlockRef.current) {
        const pending = pendingBlockRef.current;
        pendingBlockRef.current = null;
        try {
          await onBlockChangeRef.current(pending);
          setError(null);
        } catch (caught) {
          setError(
            caught instanceof Error
              ? caught.message
              : "The visual artifact could not be synchronized.",
          );
        }
      }
    } finally {
      syncingBlockRef.current = false;
      if (pendingBlockRef.current) void flushBlockChanges();
    }
  };

  const withError = (content: ReactNode) => (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col">
      {content}
      {error ? (
        <p className="mt-2 text-xs text-rose-400" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );

  const update = (block: StructuredBlock) => {
    setError(null);
    const revision = (block as { revision?: number }).revision ?? document.revision + 1;
    const next = {
      ...document,
      revision,
      data: { ...block, id: document.block_id, block_id: document.block_id, revision },
      history: [
        ...(Array.isArray(document.history) ? document.history : []),
        { revision, source: "artifact-editor", at: new Date().toISOString() },
      ].slice(-100),
    };
    onChange(JSON.stringify(next, null, 2));
    pendingBlockRef.current = next.data;
    void flushBlockChanges();
  };

  switch (document.data.type) {
    case "chart":
      return withError(
        <VisualBlockExport block={document.data}>
          <ChartBlock
            block={document.data as never}
            onChange={(block) => update(block as StructuredBlock)}
          />
        </VisualBlockExport>,
      );
    case "card":
      return withError(
        <VisualBlockExport block={document.data}>
          <RichInfoCard block={document.data} onChange={update} />
        </VisualBlockExport>,
      );
    case "infographic":
      return withError(
        <VisualBlockExport block={document.data}>
          <InfographicBlock block={document.data} onChange={update} />
        </VisualBlockExport>,
      );
    case "diagram":
      return withError(
        <VisualBlockExport
          block={document.data}
          className="flex min-h-0 flex-1 flex-col"
          contentClassName="min-h-0 flex-1"
        >
          <DiagramBlock
            block={document.data as never}
            fillHeight
            onChange={(block) => update(block as StructuredBlock)}
          />
        </VisualBlockExport>,
      );
    case "gallery":
      return withError(
        <VisualBlockExport block={document.data}>
          <GalleryBlock
            payload={document.data}
            onChange={(gallery) =>
              update({
                ...document.data,
                ...gallery,
                id: document.block_id,
                block_id: document.block_id,
                type: "gallery",
              })
            }
          />
        </VisualBlockExport>,
      );
    default:
      return null;
  }
}
