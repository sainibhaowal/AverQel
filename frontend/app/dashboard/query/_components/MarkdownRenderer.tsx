"use client";

import { useRef, useEffect, useMemo, useState } from "react";

import {
  parseStreamingDocument,
  resetNormCache,
} from "@/app/dashboard/query/_lib/streaming-document-parser";
import type {
  StreamingChartNode,
  StreamingCodeNode,
  StreamingDocumentNode,
  StreamingFootnoteNode,
  StreamingImageNode,
  StreamingListNode,
  StreamingTableNode,
} from "@/app/dashboard/query/_lib/streaming-document-types";

import StreamingDocumentRenderer from "./streaming-document/StreamingDocumentRenderer";

interface MarkdownRendererProps {
  content: string;
  streaming?: boolean;
  messageId?: string;
  enableRichPreview?: boolean;
}

// ─────────────────────────────────────────────────────────────────────────────
// TABLE NODE IDENTITY STABILISER
//
// Problem: parseStreamingDocument runs on every delta token and always returns
// brand-new object references. For table nodes this causes TableBlock to
// re-render on every single character token — even mid-cell characters that
// change nothing visible. This produces the "ghost rows" / shimmer flicker
// seen in picture 2.
//
// This function stabilises table node object identity. After parsing, it
// replaces any table node that is structurally identical to the previous
// parse's table node with the PREVIOUS object reference. React.memo on
// TableBlock then sees the same reference → skips the re-render entirely.
//
// All other node types (heading, paragraph, list, code, rule) are returned
// as-is with their new references — they update on every token as before,
// which is correct because mid-word characters DO change what those nodes
// display (the text content grows character by character).
//
// The stabilisation only suppresses re-renders when nothing structurally
// changed in the table. A re-render IS allowed through when:
//   • row count changes          (new completed row arrived)
//   • column count changes       (separator row locked columns)
//   • header content changes     (header text still arriving on first ticks)
//   • last row content changes   (final row gaining cells)
//   • incomplete flag changes    (separator row just arrived)
//   • title changes              (rare)
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// STRUCTURED NODE IDENTITY STABILISER  (tables + charts)
//
// Problem: parseStreamingDocument runs on every delta token and always returns
// brand-new object references. For structured nodes (tables, charts) this
// causes their React components to re-render on every single character token —
// even tokens that change nothing visible inside the block.
//
// This function stabilises structured node object identity. After parsing, it
// replaces any node that is structurally identical to the previous parse with
// the PREVIOUS object reference. React.memo on TableBlock / ChartBlock then
// sees the same reference → skips the re-render entirely.
//
// TABLE re-renders are allowed when:
//   • row/column count changes, header content changes, last row changes,
//     incomplete flag changes, or title changes.
//
// CHART re-renders are allowed when:
//   • raw_payload changes  (more JSON has streamed in)
//   • incomplete flag changes  (fence just closed — this is the moment the
//     chart should render, so the re-render IS needed exactly once)
//   • chart_type or title changes (rare, but allowed through)
//
// Critically: once the fence closes (incomplete: false) and raw_payload is
// stable, every subsequent token that adds more TEXT after the chart returns
// the PREVIOUS chart object → ChartBlock skips re-render → no flicker/flash.
// ─────────────────────────────────────────────────────────────────────────────

function stabiliseStructuredNodes(
  nextNodes: StreamingDocumentNode[],
  prevNodes: StreamingDocumentNode[],
): StreamingDocumentNode[] {
  // ── Tables ──────────────────────────────────────────────────────────────
  const prevTables: StreamingTableNode[] = [];
  for (const node of prevNodes) {
    if (node.type === "table") prevTables.push(node);
  }

  // ── Charts ──────────────────────────────────────────────────────────────
  const prevCharts: StreamingChartNode[] = [];
  for (const node of prevNodes) {
    if (node.type === "chart") prevCharts.push(node as StreamingChartNode);
  }

  const prevImages: StreamingImageNode[] = [];
  const prevFootnotes: StreamingFootnoteNode[] = [];
  const prevLists: StreamingListNode[] = [];
  for (const node of prevNodes) {
    if (node.type === "image") prevImages.push(node as StreamingImageNode);
    if (node.type === "footnote") prevFootnotes.push(node as StreamingFootnoteNode);
    if (node.type === "list") prevLists.push(node as StreamingListNode);
  }

  if (
    prevTables.length === 0 &&
    prevCharts.length === 0 &&
    prevImages.length === 0 &&
    prevFootnotes.length === 0 &&
    prevLists.length === 0
  )
    return nextNodes;

  let tablesSeen = 0;
  let chartsSeen = 0;
  let imagesSeen = 0;
  let footnotesSeen = 0;
  let listsSeen = 0;
  let anySubstituted = false;
  const result: StreamingDocumentNode[] = [];

  for (const node of nextNodes) {
    // ── Table stabilisation ───────────────────────────────────────────────
    if (node.type === "table") {
      const next = node as StreamingTableNode;
      const prev = prevTables[tablesSeen] as StreamingTableNode | undefined;
      tablesSeen++;

      if (!prev) {
        result.push(next);
        continue;
      }

      const structurallyIdentical =
        prev.title === next.title &&
        prev.incomplete === next.incomplete &&
        prev.headers.length === next.headers.length &&
        prev.rows.length === next.rows.length &&
        prev.headers.join("\x00") === next.headers.join("\x00") &&
        (prev.rows[prev.rows.length - 1]?.join("\x00") ?? "") ===
          (next.rows[next.rows.length - 1]?.join("\x00") ?? "");

      if (structurallyIdentical) {
        result.push(prev);
        anySubstituted = true;
      } else {
        result.push(next);
      }
      continue;
    }

    // ── Code/Mermaid stabilisation ────────────────────────────────────────
    if (node.type === "code") {
      const next = node as StreamingCodeNode;
      if (next.incomplete) {
        result.push(next);
        continue;
      }
      const prev = prevNodes.find(
        (p) => p.type === "code" && (p as StreamingCodeNode).value === next.value,
      ) as StreamingCodeNode | undefined;
      if (prev) {
        result.push(prev);
        anySubstituted = true;
      } else {
        result.push(next);
      }
      continue;
    }

    // ── Chart stabilisation ───────────────────────────────────────────────
    if (node.type === "chart") {
      const next = node as StreamingChartNode;
      const prev = prevCharts[chartsSeen] as StreamingChartNode | undefined;
      chartsSeen++;

      if (!prev) {
        result.push(next);
        continue;
      }

      const structurallyIdentical =
        prev.incomplete === next.incomplete &&
        prev.chart_type === next.chart_type &&
        prev.title === next.title &&
        (next.incomplete === true ? false : prev.raw_payload === next.raw_payload);

      if (structurallyIdentical) {
        result.push(prev);
        anySubstituted = true;
      } else {
        result.push(next);
      }
      continue;
    }

    if (node.type === "image") {
      const next = node as StreamingImageNode;
      const prev = prevImages[imagesSeen] as StreamingImageNode | undefined;
      imagesSeen++;

      if (prev && prev.src === next.src && prev.alt === next.alt && prev.title === next.title) {
        result.push(prev);
        anySubstituted = true;
      } else {
        result.push(next);
      }
      continue;
    }

    if (node.type === "footnote") {
      const next = node as StreamingFootnoteNode;
      const prev = prevFootnotes[footnotesSeen] as StreamingFootnoteNode | undefined;
      footnotesSeen++;

      if (prev && prev.identifier === next.identifier && prev.content === next.content) {
        result.push(prev);
        anySubstituted = true;
      } else {
        result.push(next);
      }
      continue;
    }

    if (node.type === "list") {
      const next = node as StreamingListNode;
      const prev = prevLists[listsSeen] as StreamingListNode | undefined;
      listsSeen++;

      if (prev && listFingerprint(prev) === listFingerprint(next)) {
        result.push(prev);
        anySubstituted = true;
      } else {
        result.push(next);
      }
      continue;
    }

    result.push(node);
  }

  return anySubstituted ? result : nextNodes;
}

function listFingerprint(node: StreamingListNode): string {
  return [
    node.ordered ? "1" : "0",
    ...node.items.map((item) => {
      const base = [item.task ? "t" : "n", item.checked ? "1" : "0", item.content].join(":");
      if (!item.children || item.children.length === 0) return base;
      return `${base}[${item.children.map((child) => listFingerprint(child)).join("|")}]`;
    }),
  ].join("\u001f");
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPONENT
// ─────────────────────────────────────────────────────────────────────────────

export default function MarkdownRenderer({
  content,
  streaming = false,
  messageId,
  enableRichPreview = true,
}: MarkdownRendererProps) {
  // Persistent NormCache ref — lives for the lifetime of this component.
  // Memoises the stable prefix so only the last ~40 lines re-normalise per token.
  const normCacheRef = useRef({
    stablePrefix: "",
    stablePrefixRaw: "",
    stableLineCount: 0,
  });

  // State to track if we were previously streaming to handle resets
  const [wasStreaming, setWasStreaming] = useState(false);

  // Reset cache when message changes (new stream / new message).
  useEffect(() => {
    resetNormCache(normCacheRef.current);
  }, [messageId]);

  // Handle retry scenario or stream restart
  useEffect(() => {
    if (streaming && !wasStreaming) {
      resetNormCache(normCacheRef.current);
    }
    setWasStreaming(streaming);
  }, [streaming, wasStreaming]);

  const contentWithLinks = content.replace(/\[(\d+)\]/g, "[$1](#citation-$1)");

  // Ref holding the previous render's node array.
  // Used by stabiliseTableNodes to reuse table node objects when structurally
  // unchanged, so React.memo on TableBlock can skip re-renders.
  const prevNodesRef = useRef<StreamingDocumentNode[]>([]);

  const nodes = useMemo(() => {
    // Always parse on every token — this keeps headings, paragraphs, bullet
    // points, code blocks, and lists updating character by character as before.
    // The stabiliser only affects TABLE node object identity, not parse frequency.

    const parsed = parseStreamingDocument(contentWithLinks, streaming, normCacheRef.current);

    // During streaming: stabilise table node object references so that
    // TableBlock's React.memo comparator can skip mid-cell re-renders.
    // During non-streaming (final render): skip stabilisation — always use
    // the fresh parse result.

    const stabilised = streaming ? stabiliseStructuredNodes(parsed, prevNodesRef.current) : parsed;

    prevNodesRef.current = stabilised;
    return stabilised;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contentWithLinks, streaming, messageId]);
  // normCacheRef intentionally excluded — stable ref, mutations must not
  // trigger re-renders.

  return (
    <div
      className={`chat-message-container ${streaming ? "is-streaming" : ""} prose text-foreground/90 prose-p:my-0 prose-headings:my-0 prose-table:my-0 prose-code:before:hidden prose-code:after:hidden dark:prose-invert max-w-none text-[15px] leading-8 sm:text-[15.5px] sm:leading-[2rem]`}
    >
      <StreamingDocumentRenderer
        nodes={nodes}
        isStreaming={streaming}
        enableRichPreview={enableRichPreview}
      />
      {streaming ? (
        <div className="text-foreground/35 mt-4 animate-pulse text-[11px] tracking-[0.18em] uppercase">
          Intelligence Streaming...
        </div>
      ) : null}
    </div>
  );
}
