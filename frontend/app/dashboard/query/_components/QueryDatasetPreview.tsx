"use client";

import { AlertCircle, LoaderCircle, Search, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { fetchWithAuth } from "@/lib/api";

interface DatasetRowWindow {
  filename: string;
  columns: string[];
  omitted_column_count: number;
  rows: Array<Record<string, unknown> & { source_row_number: number }>;
  truncated_cells: number;
  start_row: number;
  limit: number;
  has_more: boolean;
  row_count: number;
}

interface QueryDatasetPreviewProps {
  documentId: string;
  documentName: string;
  initialRow?: number;
  matchedRowCount?: number;
  onClose: () => void;
}

function displayCell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function QueryDatasetPreview({
  documentId,
  documentName,
  initialRow = 2,
  matchedRowCount,
  onClose,
}: QueryDatasetPreviewProps) {
  const [startRow, setStartRow] = useState(Math.max(2, initialRow));
  const [rowInput, setRowInput] = useState(String(Math.max(2, initialRow)));
  const [windowData, setWindowData] = useState<DatasetRowWindow | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadRows = useCallback(
    async (row: number, signal?: AbortSignal) => {
      try {
        const params = new URLSearchParams({ start_row: String(row), limit: "100" });
        const response = (await fetchWithAuth(`/queries/datasets/${documentId}/rows?${params}`, {
          signal,
          timeoutMs: 30_000,
        })) as Response;
        if (!response.ok) {
          const payload = (await response.json().catch(() => ({}))) as {
            detail?: { message?: string } | string;
            error?: { message?: string };
          };
          throw new Error(
            typeof payload.detail === "string"
              ? payload.detail
              : payload.detail?.message ||
                  payload.error?.message ||
                  `Table preview failed (HTTP ${response.status}).`,
          );
        }
        setWindowData((await response.json()) as DatasetRowWindow);
      } catch (loadError) {
        if (!signal?.aborted) {
          setError(loadError instanceof Error ? loadError.message : "Could not load table rows.");
        }
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [documentId],
  );

  useEffect(() => {
    const controller = new AbortController();
    const request = window.setTimeout(() => {
      void loadRows(startRow, controller.signal);
    }, 0);
    return () => {
      window.clearTimeout(request);
      controller.abort();
    };
  }, [loadRows, startRow]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const jumpToRow = () => {
    const parsed = Number.parseInt(rowInput, 10);
    if (!Number.isFinite(parsed) || parsed < 2 || parsed > 1_000_001) {
      setError("Enter a source row from 2 to 1,000,001. Row 1 contains the column names.");
      return;
    }
    setError(null);
    if (parsed !== startRow) setLoading(true);
    setStartRow(parsed);
  };

  const navigateToRow = (row: number) => {
    setError(null);
    if (row !== startRow) setLoading(true);
    setStartRow(row);
    setRowInput(String(row));
  };

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/65 p-2 backdrop-blur-sm sm:p-6"
      role="presentation"
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-label={`Table preview: ${documentName}`}
        className="border-glass-border bg-surface-1 flex max-h-[92vh] w-full max-w-7xl flex-col overflow-hidden rounded-2xl border shadow-2xl"
      >
        <header className="border-glass-border flex items-start justify-between gap-4 border-b px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <h2 className="text-foreground truncate text-sm font-semibold">{documentName}</h2>
            <p className="text-foreground/55 mt-1 text-xs">
              {windowData
                ? `${windowData.row_count.toLocaleString()} data rows · source row 1 is the header`
                : "Loading indexed table…"}
              {matchedRowCount !== undefined
                ? ` · ${matchedRowCount.toLocaleString()} matching rows used in the calculation`
                : ""}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close table preview"
            className="text-foreground/55 hover:text-foreground rounded-lg p-2"
          >
            <X size={18} />
          </button>
        </header>

        <div className="border-glass-border flex flex-wrap items-end gap-2 border-b px-4 py-3 sm:px-6">
          <label className="text-foreground/55 text-[11px]" htmlFor="query-dataset-row-jump">
            Jump to source row
          </label>
          <div className="flex items-center gap-1.5">
            <input
              id="query-dataset-row-jump"
              inputMode="numeric"
              value={rowInput}
              onChange={(event) => setRowInput(event.target.value.replace(/[^0-9]/g, ""))}
              onKeyDown={(event) => {
                if (event.key === "Enter") jumpToRow();
              }}
              className="border-glass-border bg-surface-0 text-foreground focus:border-primary w-28 rounded-lg border px-2.5 py-1.5 text-xs outline-none"
            />
            <button
              type="button"
              onClick={jumpToRow}
              className="bg-primary/15 text-primary hover:bg-primary/25 flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium"
            >
              <Search size={13} /> Go
            </button>
          </div>
          <span className="text-foreground/40 ml-auto text-[10px]">
            Showing up to 100 rows per request
          </span>
        </div>

        {error ? (
          <div role="alert" className="text-danger flex items-center gap-2 px-5 py-3 text-xs">
            <AlertCircle size={15} />
            {error}
          </div>
        ) : null}
        <div className="min-h-0 flex-1 overflow-auto">
          {loading && !windowData ? (
            <div
              role="status"
              className="text-foreground/55 flex h-48 items-center justify-center gap-2 text-xs"
            >
              <LoaderCircle size={16} className="animate-spin" /> Loading indexed rows…
            </div>
          ) : windowData?.rows.length ? (
            <table className="w-full border-collapse text-left text-xs">
              <thead className="bg-surface-0 text-foreground/65 sticky top-0 z-10">
                <tr>
                  <th className="border-glass-border bg-surface-0 sticky left-0 px-3 py-2 font-semibold">
                    Source row
                  </th>
                  {windowData.columns.map((column) => (
                    <th
                      key={column}
                      className="border-glass-border max-w-64 border-b px-3 py-2 font-semibold"
                    >
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {windowData.rows.map((row) => (
                  <tr key={row.source_row_number} className="hover:bg-primary/[0.04]">
                    <td className="border-glass-border bg-surface-1 text-primary sticky left-0 border-b px-3 py-2 font-mono tabular-nums">
                      {row.source_row_number.toLocaleString()}
                    </td>
                    {windowData.columns.map((column) => {
                      const value = displayCell(row[column]);
                      return (
                        <td
                          key={column}
                          title={value}
                          className="border-glass-border text-foreground/75 max-w-64 truncate border-b px-3 py-2 align-top"
                        >
                          {value}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : windowData ? (
            <div className="text-foreground/55 flex h-40 items-center justify-center text-xs">
              No data rows at this source row.
            </div>
          ) : null}
          {windowData?.truncated_cells || windowData?.omitted_column_count ? (
            <p className="text-foreground/45 p-3 text-[10px]">
              {windowData.truncated_cells
                ? `${windowData.truncated_cells} long cell values are shortened to keep the preview responsive. `
                : ""}
              {windowData.omitted_column_count
                ? `Showing the first ${windowData.columns.length} columns; ${windowData.omitted_column_count} additional columns are omitted from this preview.`
                : ""}
            </p>
          ) : null}
        </div>

        <footer className="border-glass-border flex items-center justify-between border-t px-4 py-3 sm:px-6">
          <button
            type="button"
            disabled={loading || startRow <= 2}
            onClick={() => navigateToRow(Math.max(2, startRow - 100))}
            className="border-glass-border text-foreground/70 rounded-lg border px-3 py-1.5 text-xs disabled:opacity-40"
          >
            Previous 100
          </button>
          <span className="text-foreground/45 text-[10px]">
            Starting at source row{" "}
            {windowData?.start_row.toLocaleString() ?? startRow.toLocaleString()}
          </span>
          <button
            type="button"
            disabled={loading || !windowData?.has_more}
            onClick={() => navigateToRow(startRow + 100)}
            className="border-glass-border text-foreground/70 rounded-lg border px-3 py-1.5 text-xs disabled:opacity-40"
          >
            Next 100
          </button>
        </footer>
      </section>
    </div>
  );
}
