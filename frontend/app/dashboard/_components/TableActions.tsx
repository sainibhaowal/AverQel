"use client";

import { useState } from "react";
import { Check, ChevronDown, Copy, Download } from "lucide-react";

import { exportTableCsv, exportTableExcel, tableToTsv } from "@/lib/table-export";

interface TableActionsProps {
  rows: string[][];
  title?: string | null;
}

export default function TableActions({ rows, title }: TableActionsProps) {
  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const disabled = rows.length === 0;

  const copy = async () => {
    if (disabled) return;
    try {
      await navigator.clipboard.writeText(tableToTsv(rows));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  const exportExcel = async () => {
    if (disabled || exporting) return;
    setExporting(true);
    try {
      await exportTableExcel(rows, title);
      setExportOpen(false);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="flex items-center gap-1" aria-label="Table actions">
      <button
        type="button"
        onClick={() => void copy()}
        disabled={disabled}
        className="theme-chip text-foreground/72 hover:text-foreground hover:border-primary/40 inline-flex h-8 w-8 items-center justify-center rounded-full transition disabled:cursor-not-allowed disabled:opacity-40"
        aria-label="Copy table"
        title={copied ? "Copied" : "Copy table"}
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
      <div className="relative">
        <button
          type="button"
          onClick={() => setExportOpen((current) => !current)}
          disabled={disabled}
          className="theme-chip text-foreground/72 hover:text-foreground hover:border-primary/40 inline-flex h-8 items-center gap-1 rounded-full px-3 text-xs transition disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Export table"
          aria-expanded={exportOpen}
          title="Export table"
        >
          <Download size={14} /> Export <ChevronDown size={13} />
        </button>
        {exportOpen ? (
          <div className="theme-panel absolute top-9 right-0 z-20 grid min-w-28 gap-1 rounded-xl p-1 shadow-xl">
            <button
              type="button"
              onClick={() => {
                exportTableCsv(rows, title);
                setExportOpen(false);
              }}
              className="rounded-lg px-3 py-2 text-left text-xs hover:bg-white/10"
            >
              CSV
            </button>
            <button
              type="button"
              onClick={() => void exportExcel()}
              disabled={exporting}
              className="rounded-lg px-3 py-2 text-left text-xs hover:bg-white/10 disabled:opacity-40"
            >
              {exporting ? "Excel…" : "Excel (.xlsx)"}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
