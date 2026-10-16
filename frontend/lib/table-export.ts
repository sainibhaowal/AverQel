"use client";

import ExcelJS from "exceljs";

import { downloadBlob, safeExportName } from "./client-export";

export function tableToTsv(rows: string[][]): string {
  return rows.map((row) => row.join("\t")).join("\n");
}

export async function copyTextToClipboard(text: string): Promise<void> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch {
      // Fall through to the local selection-based copy path when permissions
      // or the current browser context block the Clipboard API.
    }
  }

  if (typeof document !== "undefined" && typeof document.execCommand === "function") {
    const previousFocus = document.activeElement;
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.setAttribute("aria-hidden", "true");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    textarea.style.pointerEvents = "none";
    document.body.appendChild(textarea);
    textarea.select();

    let copied = false;
    try {
      copied = document.execCommand("copy");
    } finally {
      textarea.remove();
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    }

    if (copied) return;
  }

  throw new Error("Clipboard access was blocked. Check browser permissions and try again.");
}

export function tableToCsv(rows: string[][]): string {
  return rows
    .map((row) => row.map((cell) => `"${String(cell).replaceAll('"', '""')}"`).join(","))
    .join("\r\n");
}

export function exportTableCsv(rows: string[][], title?: string | null): void {
  downloadBlob(
    new Blob([`\uFEFF${tableToCsv(rows)}`], { type: "text/csv;charset=utf-8" }),
    `${safeExportName(title ?? "table", "table")}.csv`,
  );
}

export async function exportTableExcel(rows: string[][], title?: string | null): Promise<void> {
  const workbook = new ExcelJS.Workbook();
  const worksheet = workbook.addWorksheet("Table");
  worksheet.addRows(rows);
  const buffer = await workbook.xlsx.writeBuffer();
  downloadBlob(
    new Blob([buffer], {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }),
    `${safeExportName(title ?? "table", "table")}.xlsx`,
  );
}
