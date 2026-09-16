"use client";

import ExcelJS from "exceljs";
import {
  Archive,
  ChevronLeft,
  ChevronRight,
  FileWarning,
  Maximize2,
  Minus,
  Music2,
  Plus,
  RotateCcw,
  RotateCw,
  Table2,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent,
  type ReactNode,
  type WheelEvent,
} from "react";

import DeepSpaceMarkdownRenderer from "./DeepSpaceMarkdownRenderer";
import { fetchWithAuth } from "@/lib/api";
import type { LibraryFileKind } from "./DeepSpaceLibraryFormats";

type DiffRow = {
  left: string;
  right: string;
  leftKind: "context" | "removed" | "empty";
  rightKind: "context" | "added" | "empty";
};

type ArchiveEntry = { name: string; directory: boolean; compressedSize: number; size: number };

function dataUrl(value: string, contentType: string) {
  const trimmed = value.trim();
  if (trimmed.startsWith("data:")) return trimmed;
  if (!trimmed) return null;
  const type = contentType || "application/octet-stream";
  // Binary Library payloads are represented as base64 data URLs by the import/agent APIs.
  if (/^[A-Za-z0-9+/=\s]+$/.test(trimmed) && trimmed.length > 64) {
    return `data:${type};base64,${trimmed.replace(/\s+/g, "")}`;
  }
  return null;
}

function decodeBase64(value: string) {
  const encoded = value.replace(/^data:[^,]+,/, "").replace(/\s+/g, "");
  try {
    const binary = atob(encoded);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return bytes;
  } catch {
    return null;
  }
}

export const CSV_PREVIEW_MAX_ROWS = 200;
export const CSV_PREVIEW_MAX_COLUMNS = 50;
export const CSV_PREVIEW_MAX_CHARS = 512 * 1024;

export function parseCsvPreview(value: string): { rows: string[][]; truncated: boolean } {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  const limit = Math.min(value.length, CSV_PREVIEW_MAX_CHARS);
  for (let index = 0; index < limit; index += 1) {
    const character = value[index];
    const next = value[index + 1];
    if (character === '"' && quoted && next === '"') {
      cell += '"';
      index += 1;
    } else if (character === '"') quoted = !quoted;
    else if (character === "," && !quoted) {
      row.push(cell);
      cell = "";
    } else if ((character === "\n" || character === "\r") && !quoted) {
      if (character === "\r" && next === "\n") index += 1;
      row.push(cell);
      if (row.some((part) => part.length > 0)) rows.push(row.slice(0, CSV_PREVIEW_MAX_COLUMNS));
      row = [];
      cell = "";
      if (rows.length >= CSV_PREVIEW_MAX_ROWS) {
        return { rows, truncated: true };
      }
    } else cell += character;
  }
  if (cell || row.length) {
    row.push(cell);
    rows.push(row.slice(0, CSV_PREVIEW_MAX_COLUMNS));
  }
  return { rows, truncated: limit < value.length };
}

function parseDiff(value: string): DiffRow[] {
  const rows: DiffRow[] = [];
  for (const line of value.split(/\r?\n/)) {
    if (!line || line.startsWith("diff ") || line.startsWith("index ") || line.startsWith("@@"))
      continue;
    if (line.startsWith("---") || line.startsWith("+++")) continue;
    if (line.startsWith("-"))
      rows.push({ left: line.slice(1), right: "", leftKind: "removed", rightKind: "empty" });
    else if (line.startsWith("+"))
      rows.push({ left: "", right: line.slice(1), leftKind: "empty", rightKind: "added" });
    else
      rows.push({
        left: line.startsWith(" ") ? line.slice(1) : line,
        right: line.startsWith(" ") ? line.slice(1) : line,
        leftKind: "context",
        rightKind: "context",
      });
  }
  return rows;
}

function parseArchive(value: string): ArchiveEntry[] {
  const bytes = decodeBase64(value);
  if (!bytes) return [];
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const entries: ArchiveEntry[] = [];
  for (let offset = 0; offset + 46 <= bytes.length; offset += 1) {
    if (view.getUint32(offset, true) !== 0x02014b50) continue;
    const flags = view.getUint16(offset + 8, true);
    const compressedSize = view.getUint32(offset + 20, true);
    const size = view.getUint32(offset + 24, true);
    const nameLength = view.getUint16(offset + 28, true);
    const extraLength = view.getUint16(offset + 30, true);
    const commentLength = view.getUint16(offset + 32, true);
    const nameBytes = bytes.slice(offset + 46, offset + 46 + nameLength);
    const name = new TextDecoder().decode(nameBytes);
    entries.push({ name, directory: name.endsWith("/"), compressedSize, size });
    offset += 45 + nameLength + extraLength + commentLength;
    if (flags & 0x01) continue;
  }
  return entries;
}

function spreadsheetRows(workbook: ExcelJS.Workbook): string[][] {
  const worksheet = workbook.worksheets[0];
  if (!worksheet) return [];
  const rows: string[][] = [];
  worksheet.eachRow({ includeEmpty: false }, (row) => {
    if (rows.length >= CSV_PREVIEW_MAX_ROWS) return;
    const values = Array.isArray(row.values) ? row.values.slice(1) : [];
    rows.push(
      values.slice(0, CSV_PREVIEW_MAX_COLUMNS).map((value) => {
        if (value === null || value === undefined) return "";
        if (value instanceof Date) return value.toISOString();
        if (typeof value === "object") {
          if ("text" in value && typeof value.text === "string") return value.text;
          if ("result" in value && value.result !== undefined) return String(value.result);
          return JSON.stringify(value);
        }
        return String(value);
      }),
    );
  });
  return rows;
}

function Table({ rows, notice }: { rows: string[][]; notice?: string | null }) {
  const columns = Math.max(1, ...rows.map((row) => row.length));
  return (
    <div className="custom-scrollbar h-full overflow-auto">
      {notice ? (
        <p className="border-primary/25 bg-primary/8 text-foreground/70 sticky top-0 z-10 border-b px-3 py-2 text-[11px]">
          {notice}
        </p>
      ) : null}
      <table className="min-w-full border-collapse text-left text-xs">
        <thead className="bg-surface-1/80 sticky top-0">
          <tr>
            {Array.from({ length: columns }, (_, index) => (
              <th
                key={index}
                className="border-glass-border text-muted-foreground border-b px-3 py-2 font-semibold"
              >
                {rows[0]?.[index] || `Column ${index + 1}`}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.slice(1).map((row, rowIndex) => (
            <tr key={rowIndex} className="hover:bg-surface-1/60">
              {Array.from({ length: columns }, (_, columnIndex) => (
                <td
                  key={columnIndex}
                  className="border-glass-border text-foreground/75 border-b px-3 py-2 align-top whitespace-pre-wrap"
                >
                  {row[columnIndex] ?? ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Fixed-height grid virtualization for server-paged data.  At most the visible
 * rows plus a small overscan exist in the DOM, even when a future page size is
 * increased.  It never attempts to load the original file in the browser.
 */
function VirtualizedTable({ rows, notice }: { rows: string[][]; notice?: string | null }) {
  const rowHeight = 34;
  const overscan = 8;
  const [scrollTop, setScrollTop] = useState(0);
  const columns = Math.max(1, ...rows.map((row) => row.length));
  const body = rows.slice(1);
  const first = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
  const visibleCount = 24 + overscan * 2;
  const visible = body.slice(first, first + visibleCount);
  return (
    <div
      className="custom-scrollbar h-full overflow-auto"
      onScroll={(event) => setScrollTop(event.currentTarget.scrollTop)}
    >
      {notice ? (
        <p className="border-primary/25 bg-primary/8 text-foreground/70 sticky top-0 z-20 border-b px-3 py-2 text-[11px]">
          {notice}
        </p>
      ) : null}
      <div
        className="bg-surface-1/80 sticky top-0 z-10 grid min-w-max"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(10rem, 1fr))` }}
      >
        {Array.from({ length: columns }, (_, index) => (
          <div key={index} className="border-glass-border border-b px-3 py-2 text-xs font-semibold">
            {rows[0]?.[index] || `Column ${index + 1}`}
          </div>
        ))}
      </div>
      <div className="relative min-w-max" style={{ height: body.length * rowHeight }}>
        <div
          className="absolute inset-x-0 grid"
          style={{
            transform: `translateY(${first * rowHeight}px)`,
            gridTemplateColumns: `repeat(${columns}, minmax(10rem, 1fr))`,
          }}
        >
          {visible.flatMap((row, rowIndex) =>
            Array.from({ length: columns }, (_, columnIndex) => (
              <div
                key={`${first + rowIndex}-${columnIndex}`}
                className="border-glass-border text-foreground/75 hover:bg-surface-1/60 overflow-hidden border-b px-3 py-2 text-xs text-ellipsis whitespace-nowrap"
                style={{ height: rowHeight }}
              >
                {row[columnIndex] ?? ""}
              </div>
            )),
          )}
        </div>
      </div>
    </div>
  );
}

function SpreadsheetTable({ value, previewUrl }: { value: string; previewUrl?: string | null }) {
  const [rows, setRows] = useState<string[][]>([]);
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const buffer = previewUrl
          ? await fetch(previewUrl).then((response) => response.arrayBuffer())
          : decodeBase64(value);
        if (!buffer) {
          if (!cancelled) setRows([]);
          return;
        }
        const workbook = new ExcelJS.Workbook();
        // ExcelJS accepts ArrayBuffer/Uint8Array in the browser; its bundled
        // declaration currently exposes the Node Buffer overload only.
        await workbook.xlsx.load(buffer as unknown as Parameters<typeof workbook.xlsx.load>[0]);
        if (!cancelled) setRows(spreadsheetRows(workbook));
      } catch {
        if (!cancelled) setRows([]);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [previewUrl, value]);
  if (rows.length) return <Table rows={rows} />;
  if (value.trim()) {
    return (
      <pre className="text-foreground/75 h-full overflow-auto text-xs leading-5 whitespace-pre-wrap">
        {value}
      </pre>
    );
  }
  return (
    <EmptyPreview
      icon={<Table2 size={18} />}
      text="This spreadsheet is empty or its binary payload is unavailable."
    />
  );
}

function CsvPreviewTable({
  value,
  contentTruncated,
  sizeBytes,
  pageUrl,
}: {
  value: string;
  contentTruncated: boolean;
  sizeBytes?: number;
  pageUrl?: string | null;
}) {
  const preview = useMemo(() => parseCsvPreview(value), [value]);
  const limited = preview.truncated || contentTruncated;
  const [page, setPage] = useState<{
    columns: string[];
    rows: string[][];
    offset: number;
    limit: number;
    has_more: boolean;
  } | null>(null);
  const [loadingPage, setLoadingPage] = useState(false);
  const loadPage = async (offset: number) => {
    if (!pageUrl) return;
    setLoadingPage(true);
    try {
      const response = (await fetchWithAuth(
        `${pageUrl}?offset=${offset}&limit=${CSV_PREVIEW_MAX_ROWS}`,
        { timeoutMs: 30_000 },
      )) as Response;
      if (response.ok) setPage((await response.json()) as typeof page);
    } finally {
      setLoadingPage(false);
    }
  };
  useEffect(() => {
    if (pageUrl) queueMicrotask(() => void loadPage(0));
  }, [pageUrl]); // eslint-disable-line react-hooks/exhaustive-deps
  const displayedRows = page ? [page.columns, ...page.rows] : preview.rows;
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1">
        <VirtualizedTable
          rows={displayedRows}
          notice={
            limited
              ? `Showing ${page ? `rows ${page.offset + 1}–${page.offset + page.rows.length}` : `the first ${CSV_PREVIEW_MAX_ROWS} rows`} / ${CSV_PREVIEW_MAX_COLUMNS} columns. The browser renders one page at a time; the original ${
                  sizeBytes ? `${Math.ceil(sizeBytes / 1024 / 1024)} MB ` : ""
                }file stays private and can be downloaded or analyzed in the sandbox.`
              : null
          }
        />
      </div>
      {pageUrl ? (
        <div className="border-glass-border flex shrink-0 items-center justify-between border-t px-3 py-2 text-[11px]">
          <button
            type="button"
            disabled={loadingPage || !page?.offset}
            onClick={() => void loadPage(Math.max(0, (page?.offset ?? 0) - CSV_PREVIEW_MAX_ROWS))}
            className="inline-flex items-center gap-1 disabled:opacity-40"
          >
            <ChevronLeft size={13} /> Previous
          </button>
          <span className="text-foreground/55">
            {loadingPage ? "Loading rows…" : "Paged table view"}
          </span>
          <button
            type="button"
            disabled={loadingPage || !page?.has_more}
            onClick={() => void loadPage((page?.offset ?? 0) + CSV_PREVIEW_MAX_ROWS)}
            className="inline-flex items-center gap-1 disabled:opacity-40"
          >
            Next <ChevronRight size={13} />
          </button>
        </div>
      ) : null}
    </div>
  );
}

function EmptyPreview({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <div className="text-muted-foreground flex h-full min-h-40 items-center justify-center gap-2 p-6 text-center text-xs">
      {icon}
      {text}
    </div>
  );
}

export function InteractiveImagePreview({
  source,
  alt = "Image preview",
}: {
  source: string;
  alt?: string;
}) {
  const [scale, setScale] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [rotation, setRotation] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [dragging, setDragging] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    originX: number;
    originY: number;
  } | null>(null);

  const clampPan = (x: number, y: number, targetScale = scale) => {
    const viewport = viewportRef.current;
    if (!viewport) return { x, y };
    // Keep the image reachable while allowing generous movement at high zoom.
    // The bound is based on the viewport rather than the source dimensions so
    // tiny images cannot disappear and huge images remain pannable.
    const maxX = Math.max(0, (viewport.clientWidth * (targetScale - 1)) / 2 + 48);
    const maxY = Math.max(0, (viewport.clientHeight * (targetScale - 1)) / 2 + 48);
    return {
      x: Math.max(-maxX, Math.min(maxX, x)),
      y: Math.max(-maxY, Math.min(maxY, y)),
    };
  };

  const resetView = () => {
    setScale(1);
    setPan({ x: 0, y: 0 });
    setRotation(0);
    setFlipped(false);
  };

  const changeScale = (nextScale: number, focalPoint?: { x: number; y: number }) => {
    const boundedScale = Math.max(0.25, Math.min(5, nextScale));
    setPan((current) => {
      if (!focalPoint || scale === boundedScale)
        return clampPan(current.x, current.y, boundedScale);
      // Preserve the point under the pointer while zooming. Translation is
      // measured in viewport pixels and therefore uses the scale delta.
      return clampPan(
        current.x + focalPoint.x * (scale - boundedScale),
        current.y + focalPoint.y * (scale - boundedScale),
        boundedScale,
      );
    });
    setScale(boundedScale);
  };

  const handleWheel = (event: WheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    changeScale(scale * (event.deltaY < 0 ? 1.1 : 1 / 1.1), {
      x: event.clientX - rect.left - rect.width / 2,
      y: event.clientY - rect.top - rect.height / 2,
    });
  };

  const handlePointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: pan.x,
      originY: pan.y,
    };
  };

  const handlePointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    setPan(
      clampPan(
        drag.originX + event.clientX - drag.startX,
        drag.originY + event.clientY - drag.startY,
      ),
    );
  };

  const stopDragging = (event: PointerEvent<HTMLDivElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  };

  return (
    <div className="flex h-full min-h-40 flex-col overflow-hidden">
      <div className="border-glass-border bg-surface-1/60 text-foreground/70 flex shrink-0 flex-wrap items-center justify-end gap-1 border-b px-2 py-1 text-[10px]">
        <button
          type="button"
          title="Zoom out"
          aria-label="Zoom out"
          onClick={() => changeScale(scale - 0.25)}
          className="rounded p-1 hover:bg-white/10"
        >
          <Minus size={12} />
        </button>
        <span className="min-w-10 text-center">{Math.round(scale * 100)}%</span>
        <button
          type="button"
          title="Zoom in"
          aria-label="Zoom in"
          onClick={() => changeScale(scale + 0.25)}
          className="rounded p-1 hover:bg-white/10"
        >
          <Plus size={12} />
        </button>
        <button
          type="button"
          title="Reset zoom"
          aria-label="Reset zoom"
          onClick={() => setScale(1)}
          className="rounded p-1 hover:bg-white/10"
        >
          <RotateCcw size={12} />
        </button>
        <button
          type="button"
          title="Rotate left"
          aria-label="Rotate left"
          onClick={() => setRotation((value) => value - 90)}
          className="rounded p-1 hover:bg-white/10"
        >
          <RotateCcw size={12} />
        </button>
        <button
          type="button"
          title="Rotate right"
          aria-label="Rotate right"
          onClick={() => setRotation((value) => value + 90)}
          className="rounded p-1 hover:bg-white/10"
        >
          <RotateCw size={12} />
        </button>
        <button
          type="button"
          title="Flip horizontally"
          aria-label="Flip horizontally"
          aria-pressed={flipped}
          onClick={() => setFlipped((value) => !value)}
          className={`rounded px-1.5 py-1 ${flipped ? "bg-primary/15 text-primary" : "hover:bg-white/10"}`}
        >
          Flip
        </button>
        <button
          type="button"
          title="Fit image to preview"
          aria-label="Fit image to preview"
          onClick={resetView}
          className="rounded p-1 hover:bg-white/10"
        >
          <Maximize2 size={12} />
        </button>
      </div>
      <div
        ref={viewportRef}
        role="application"
        tabIndex={0}
        aria-label="Interactive image preview. Use the mouse wheel to zoom and drag to pan."
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={stopDragging}
        onPointerCancel={stopDragging}
        onDoubleClick={resetView}
        onKeyDown={(event) => {
          if (event.key === "+" || event.key === "=") changeScale(scale + 0.25);
          else if (event.key === "-" || event.key === "_") changeScale(scale - 0.25);
          else if (event.key === "0") resetView();
          else if (event.key === "ArrowLeft") setPan((value) => clampPan(value.x + 32, value.y));
          else if (event.key === "ArrowRight") setPan((value) => clampPan(value.x - 32, value.y));
          else if (event.key === "ArrowUp") setPan((value) => clampPan(value.x, value.y + 32));
          else if (event.key === "ArrowDown") setPan((value) => clampPan(value.x, value.y - 32));
        }}
        className={`flex min-h-0 flex-1 items-center justify-center overflow-hidden p-6 ${dragging ? "cursor-grabbing" : "cursor-grab"}`}
        style={{ touchAction: "none" }}
      >
        {/* Private Library object URL; next/image cannot optimize it. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={source}
          alt={alt}
          draggable={false}
          onDragStart={(event) => event.preventDefault()}
          className="max-h-full max-w-full object-contain transition-transform duration-100 ease-out select-none"
          style={{
            transform: `translate3d(${pan.x}px, ${pan.y}px, 0) scale(${scale}) rotate(${rotation}deg) scaleX(${flipped ? -1 : 1})`,
            transformOrigin: "center center",
          }}
        />
      </div>
    </div>
  );
}

export function LibraryPreview({
  kind,
  contentType,
  value,
  previewUrl,
  archiveEntries,
  onArchiveEntrySelect,
  contentTruncated = false,
  sizeBytes,
  csvPageUrl,
}: {
  kind: LibraryFileKind;
  contentType: string;
  value: string;
  previewUrl?: string | null;
  archiveEntries?: ArchiveEntry[] | null;
  onArchiveEntrySelect?: (entry: ArchiveEntry) => void;
  contentTruncated?: boolean;
  sizeBytes?: number;
  csvPageUrl?: string | null;
}) {
  if (kind === "markdown") return <DeepSpaceMarkdownRenderer content={value} />;
  if (kind === "csv")
    return (
      <CsvPreviewTable
        value={value}
        contentTruncated={contentTruncated}
        sizeBytes={sizeBytes}
        pageUrl={csvPageUrl}
      />
    );
  if (kind === "spreadsheet") return <SpreadsheetTable value={value} previewUrl={previewUrl} />;
  if (kind === "diff") {
    return (
      <div className="custom-scrollbar h-full overflow-auto font-mono text-[11px]">
        {parseDiff(value).map((row, index) => (
          <div key={index} className="grid grid-cols-2">
            <div
              className={`border-glass-border min-w-0 border-b px-3 py-1 whitespace-pre-wrap ${row.leftKind === "removed" ? "bg-rose-400/10 text-rose-200" : "text-foreground/70"}`}
            >
              {row.left}
            </div>
            <div
              className={`border-glass-border min-w-0 border-b border-l px-3 py-1 whitespace-pre-wrap ${row.rightKind === "added" ? "bg-emerald-400/10 text-emerald-200" : "text-foreground/70"}`}
            >
              {row.right}
            </div>
          </div>
        ))}
      </div>
    );
  }
  if (kind === "archive") {
    const entries = archiveEntries?.length ? archiveEntries : parseArchive(value);
    return entries.length ? (
      <div className="custom-scrollbar h-full overflow-auto p-3 text-xs">
        {entries.map((entry) => (
          <button
            key={entry.name}
            type="button"
            onClick={() => onArchiveEntrySelect?.(entry)}
            className="border-glass-border text-foreground/75 flex items-center justify-between gap-3 border-b px-2 py-2"
          >
            <span className="truncate">
              {entry.directory ? "📁" : "📄"} {entry.name}
            </span>
            <span className="text-muted-foreground shrink-0">
              {entry.directory ? "folder" : `${entry.size.toLocaleString()} B`}
            </span>
          </button>
        ))}
      </div>
    ) : (
      <EmptyPreview
        icon={<Archive size={18} />}
        text="Archive listing needs a valid ZIP payload."
      />
    );
  }
  if (["image", "svg", "video", "audio", "pdf", "docx", "pptx"].includes(kind)) {
    // Browsers do not natively render Office Open XML. Never iframe the
    // download response: it produces a blank pane or forces a download.
    // Office files are rendered from the bounded extracted text above.
    if ((kind === "docx" || kind === "pptx") && !value.trim()) {
      return (
        <EmptyPreview
          icon={<FileWarning size={18} />}
          text="No readable text was extracted for an in-app Office preview. Download the original file to open it in your Office application."
        />
      );
    }
    const source =
      previewUrl ||
      (kind === "svg" && value.trim().startsWith("<svg")
        ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(value)}`
        : dataUrl(value, contentType));
    if ((kind === "docx" || kind === "pptx") && value.trim()) {
      return <DeepSpaceMarkdownRenderer content={value} />;
    }
    if (!source)
      return (
        <EmptyPreview
          icon={<FileWarning size={18} />}
          text="This file has no browser-previewable payload yet."
        />
      );
    if (kind === "image" || kind === "svg") {
      return <InteractiveImagePreview key={source} source={source} alt="Library file preview" />;
    }
    if (kind === "video")
      return (
        <div className="flex h-full items-center justify-center p-6">
          <video controls className="max-h-full max-w-full" src={source} />
        </div>
      );
    if (kind === "audio")
      return (
        <div className="flex h-full items-center justify-center p-6">
          <div className="flex w-full max-w-lg flex-col items-center gap-4">
            <Music2 className="text-primary" size={28} />
            <audio controls className="w-full" src={source} />
          </div>
        </div>
      );
    if (kind === "pdf")
      return (
        <iframe title="PDF preview" src={source} className="h-full min-h-96 w-full border-0" />
      );
    return (
      <iframe title="Document preview" src={source} className="h-full min-h-96 w-full border-0" />
    );
  }
  return (
    <pre className="text-foreground/75 h-full overflow-auto p-4 font-mono text-xs whitespace-pre-wrap">
      {value}
    </pre>
  );
}
