"use client";

import ExcelJS from "exceljs";
import { Archive, FileWarning, Music2, Table2 } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import DeepSpaceMarkdownRenderer from "./DeepSpaceMarkdownRenderer";
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

function parseCsv(value: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  for (let index = 0; index < value.length; index += 1) {
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
      if (row.some((part) => part.length > 0)) rows.push(row);
      row = [];
      cell = "";
    } else cell += character;
  }
  if (cell || row.length) {
    row.push(cell);
    rows.push(row);
  }
  return rows;
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
    const values = Array.isArray(row.values) ? row.values.slice(1) : [];
    rows.push(
      values.map((value) => {
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

function Table({ rows }: { rows: string[][] }) {
  const columns = Math.max(1, ...rows.map((row) => row.length));
  return (
    <div className="custom-scrollbar h-full overflow-auto">
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
        await workbook.xlsx.load(
          buffer as unknown as Parameters<typeof workbook.xlsx.load>[0],
        );
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
  return rows.length ? (
    <Table rows={rows} />
  ) : (
    <EmptyPreview
      icon={<Table2 size={18} />}
      text="This spreadsheet is empty or its binary payload is unavailable."
    />
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

export function LibraryPreview({
  kind,
  contentType,
  value,
  previewUrl,
  archiveEntries,
  onArchiveEntrySelect,
}: {
  kind: LibraryFileKind;
  contentType: string;
  value: string;
  previewUrl?: string | null;
  archiveEntries?: ArchiveEntry[] | null;
  onArchiveEntrySelect?: (entry: ArchiveEntry) => void;
}) {
  if (kind === "markdown") return <DeepSpaceMarkdownRenderer content={value} />;
  if (kind === "csv") return <Table rows={parseCsv(value)} />;
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
  if (["image", "svg", "video", "audio", "pdf", "docx"].includes(kind)) {
    const source =
      previewUrl ||
      (kind === "svg" && value.trim().startsWith("<svg")
        ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(value)}`
        : dataUrl(value, contentType));
    if (kind === "docx" && value.trim()) return <DeepSpaceMarkdownRenderer content={value} />;
    if (!source)
      return (
        <EmptyPreview
          icon={<FileWarning size={18} />}
          text="This file has no browser-previewable payload yet."
        />
      );
    if (kind === "image" || kind === "svg")
      return (
        <div className="flex h-full items-center justify-center overflow-auto p-6">
          {/* Data URLs are private Library payloads; next/image cannot optimize them. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={source}
            alt="Library file preview"
            className="max-h-full max-w-full object-contain"
          />
        </div>
      );
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
