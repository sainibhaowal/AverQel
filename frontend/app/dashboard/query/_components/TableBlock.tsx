"use client";

import { memo, useMemo } from "react";

import TableActions from "../../_components/TableActions";
import { InlineMarkdown } from "./InlineMarkdown";

type TableBlockData = {
  id?: string;
  type?: "table";
  title?: string | null;
  headers: string[];
  rows: string[][];
  incomplete?: boolean;
};

interface TableBlockProps {
  block: TableBlockData;
  isStreaming?: boolean;
}

function TableBlockInner({ block, isStreaming = false }: TableBlockProps) {
  const { hasRealHeaders, paddedRows, colCount } = useMemo(() => {
    const colCount = block.headers.length;

    const hasRealHeaders = block.headers.some(
      (h) => h.trim() && !/^:?-{2,}:?$/.test(h.trim().replace(/\s+/g, "")),
    );

    const paddedRows = block.rows.map((row) =>
      row.length < colCount
        ? [...row, ...new Array(colCount - row.length).fill("")]
        : row.length > colCount
          ? row.slice(0, colCount)
          : row,
    );

    return { hasRealHeaders, paddedRows, colCount };
  }, [block]);

  const tableMatrix = useMemo(() => {
    const rows: string[][] = [];
    if (hasRealHeaders && colCount > 0) {
      rows.push(block.headers);
    }
    rows.push(...paddedRows);
    return rows;
  }, [block.headers, colCount, hasRealHeaders, paddedRows]);

  return (
    // not-prose: prevents Tailwind's prose plugin from styling <td>, <th>,
    // <a>, <strong> inside the table with its own colors (link blue, etc).
    // Without this, prose-invert on the parent wrapper turns all inline
    // content inside table cells cyan/blue regardless of our own classes.
    <div className="not-prose table-wrapper theme-panel group relative w-full min-w-0 overflow-hidden rounded-[1.8rem] shadow-[0_24px_70px_-48px_rgba(15,23,42,0.12)] dark:shadow-[0_24px_70px_-48px_rgba(15,23,42,0.96)]">
      <div className="absolute top-3 right-3 z-10 opacity-0 transition group-focus-within:opacity-100 group-hover:opacity-100">
        <TableActions rows={tableMatrix} title={block.title} />
      </div>
      {block.title ? (
        <div
          role="heading"
          aria-level={3}
          className="border-glass-border/60 text-foreground border-b px-5 py-4 text-sm font-semibold tracking-[-0.015em] sm:px-6"
        >
          {block.title}
        </div>
      ) : null}

      <div className="min-w-0 overflow-x-auto">
        <table
          className={`chat-table w-full border-collapse text-left text-sm ${
            isStreaming ? "is-streaming" : ""
          }`}
          style={{ tableLayout: "fixed" }}
          aria-label={block.title ?? undefined}
        >
          {hasRealHeaders && colCount > 0 ? (
            <thead className="bg-foreground/[0.04] dark:bg-white/[0.045]">
              <tr>
                {block.headers.map((header, i) => (
                  <th
                    key={`h-${i}`}
                    className="border-glass-border/60 text-primary border-b px-5 py-3 text-[11px] font-semibold tracking-[0.18em] uppercase sm:px-6"
                  >
                    <InlineMarkdown content={header} />
                  </th>
                ))}
              </tr>
            </thead>
          ) : null}

          <tbody>
            {paddedRows.map((row, rowIndex) => (
              <tr
                key={`r-${rowIndex}`}
                className="odd:bg-foreground/[0.02] hover:bg-foreground/[0.04] transition-colors dark:odd:bg-white/[0.015] dark:hover:bg-white/[0.03]"
              >
                {row.map((cell, cellIndex) => (
                  <td
                    key={`c-${cellIndex}`}
                    className="border-glass-border/40 text-foreground/84 border-b px-5 py-3.5 align-top text-[14px] leading-7 sm:px-6"
                  >
                    <InlineMarkdown content={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function arePropsEqual(prev: TableBlockProps, next: TableBlockProps): boolean {
  if (prev.isStreaming !== next.isStreaming) return false;

  const pb = prev.block;
  const nb = next.block;

  if (pb.title !== nb.title) return false;
  if (pb.incomplete !== nb.incomplete) return false;
  if (pb.headers.length !== nb.headers.length) return false;
  if (pb.rows.length !== nb.rows.length) return false;
  if (pb.headers.join("\x00") !== nb.headers.join("\x00")) return false;

  const lastPrev = pb.rows[pb.rows.length - 1];
  const lastNext = nb.rows[nb.rows.length - 1];
  if ((lastPrev?.join("\x00") ?? "") !== (lastNext?.join("\x00") ?? "")) {
    return false;
  }

  return true;
}

const TableBlock = memo(TableBlockInner, arePropsEqual);
export default TableBlock;
