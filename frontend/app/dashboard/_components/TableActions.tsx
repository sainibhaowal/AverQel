"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { Check, ChevronDown, Copy, Download, Save } from "lucide-react";
import { createPortal } from "react-dom";

import {
  copyTextToClipboard,
  exportTableCsv,
  exportTableExcel,
  tableToTsv,
} from "@/lib/table-export";

interface TableActionsProps {
  rows: string[][];
  title?: string | null;
  onSaveToLibrary?: () => void | Promise<void>;
}

const menuItemClassName =
  "text-foreground hover:bg-primary/10 hover:text-primary focus-visible:ring-primary/40 rounded-lg px-3 py-2 text-left text-xs transition-colors focus-visible:ring-2 focus-visible:outline-none";

export default function TableActions({ rows, title, onSaveToLibrary }: TableActionsProps) {
  const [copied, setCopied] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [menuPosition, setMenuPosition] = useState<{ top: number; right: number } | null>(null);
  const exportButtonRef = useRef<HTMLButtonElement>(null);
  const exportMenuRef = useRef<HTMLDivElement>(null);
  const disabled = rows.length === 0;

  useLayoutEffect(() => {
    if (!exportOpen) return;

    const positionMenu = () => {
      const button = exportButtonRef.current;
      if (!button) return;

      const buttonRect = button.getBoundingClientRect();
      const menuWidth = exportMenuRef.current?.getBoundingClientRect().width || 144;
      const viewportWidth = document.documentElement.clientWidth || window.innerWidth;
      const right = Math.max(
        8,
        Math.min(viewportWidth - buttonRect.right, viewportWidth - menuWidth - 8),
      );

      setMenuPosition({ top: buttonRect.bottom + 4, right });
    };

    positionMenu();
    window.addEventListener("resize", positionMenu);
    window.addEventListener("scroll", positionMenu, true);
    return () => {
      window.removeEventListener("resize", positionMenu);
      window.removeEventListener("scroll", positionMenu, true);
    };
  }, [exportOpen]);

  const closeMenu = () => {
    setExportOpen(false);
  };

  const copy = async () => {
    if (disabled) return;
    setError(null);
    try {
      await copyTextToClipboard(tableToTsv(rows));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch (caught) {
      setCopied(false);
      setError(caught instanceof Error ? caught.message : "The table could not be copied.");
    }
  };

  const exportCsv = () => {
    if (disabled) return;
    setError(null);
    try {
      exportTableCsv(rows, title);
      closeMenu();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "CSV export failed.");
    }
  };

  const exportExcel = async () => {
    if (disabled || exporting) return;
    setExporting(true);
    setError(null);
    try {
      await exportTableExcel(rows, title);
      closeMenu();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Excel export failed.");
    } finally {
      setExporting(false);
    }
  };

  const saveToLibrary = async () => {
    if (!onSaveToLibrary || disabled || saving) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await onSaveToLibrary();
      setSaved(true);
      window.setTimeout(() => setSaved(false), 2000);
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "The table could not be saved to Library.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1" role="group" aria-label="Table actions">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => void copy()}
          disabled={disabled}
          className="theme-chip text-foreground/72 hover:text-foreground hover:border-primary/40 inline-flex h-8 w-8 items-center justify-center rounded-lg transition disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Copy table"
          title={copied ? "Copied" : "Copy table"}
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
        {onSaveToLibrary ? (
          <button
            type="button"
            onClick={() => void saveToLibrary()}
            disabled={disabled || saving}
            className="visual-block-action inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs disabled:cursor-not-allowed disabled:opacity-40"
            aria-label={saved ? "Table saved to Library" : "Save table to Library"}
            title={saved ? "Saved to Library" : "Save table to Library"}
          >
            {saving ? <Save size={13} /> : saved ? <Check size={13} /> : <Save size={13} />}
            <span>{saving ? "Saving…" : saved ? "Saved" : "Save to Library"}</span>
          </button>
        ) : null}
        <button
          ref={exportButtonRef}
          type="button"
          onClick={() => {
            setMenuPosition(null);
            setExportOpen((current) => !current);
          }}
          disabled={disabled}
          className="theme-chip text-foreground/72 hover:text-foreground hover:border-primary/40 inline-flex h-8 items-center gap-1 rounded-lg px-3 text-xs transition disabled:cursor-not-allowed disabled:opacity-40"
          aria-label="Export table"
          aria-expanded={exportOpen}
        >
          <Download size={14} /> Export <ChevronDown size={13} />
        </button>
      </div>
      {exportOpen && typeof document !== "undefined"
        ? createPortal(
            <div
              ref={exportMenuRef}
              className="theme-panel fixed z-[1000] grid max-w-[calc(100vw-1rem)] min-w-28 gap-1 rounded-xl p-1 shadow-xl"
              data-table-export-menu
              style={{
                position: "fixed",
                top: menuPosition?.top ?? 0,
                right: menuPosition?.right ?? 0,
                zIndex: 1000,
                visibility: menuPosition ? "visible" : "hidden",
              }}
            >
              <button type="button" onClick={exportCsv} className={menuItemClassName}>
                CSV
              </button>
              <button
                type="button"
                onClick={() => void exportExcel()}
                disabled={exporting}
                className={`${menuItemClassName} disabled:cursor-not-allowed disabled:opacity-40`}
              >
                {exporting ? "Excel…" : "Excel (.xlsx)"}
              </button>
            </div>,
            document.body,
          )
        : null}
      <span className="sr-only" role="status" aria-live="polite">
        {copied ? "Table copied to clipboard." : saved ? "Table saved to Library." : ""}
      </span>
      {error ? (
        <p
          className="border-glass-border bg-surface-0 text-foreground max-w-[min(18rem,calc(100vw-2rem))] rounded-lg border px-2.5 py-2 text-left text-[11px] leading-4 shadow-lg"
          role="alert"
        >
          {error}
        </p>
      ) : null}
    </div>
  );
}
