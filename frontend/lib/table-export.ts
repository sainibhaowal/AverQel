"use client";

import ExcelJS from "exceljs";

import { downloadBlob, safeExportName } from "./client-export";

export function tableToTsv(rows: string[][]): string {
  return rows.map((row) => row.join("\t")).join("\n");
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
