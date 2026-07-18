"use client";

import React from "react";

interface SynthesisMatrixCell {
  finding: string;
  document: string;
  status: "supported" | "partial" | "not_found";
  evidence: string;
}

interface SynthesisMatrixProps {
  findings: string[];
  documents: string[];
  cells: SynthesisMatrixCell[];
}

const STATUS_ICONS: Record<string, { icon: string; color: string; bg: string }> = {
  supported: { icon: "✅", color: "#22c55e", bg: "rgba(34, 197, 94, 0.1)" },
  partial: { icon: "⚠️", color: "#f59e0b", bg: "rgba(245, 158, 11, 0.1)" },
  not_found: { icon: "❌", color: "#ef4444", bg: "rgba(239, 68, 68, 0.1)" },
};

export default function SynthesisMatrix({ findings, documents, cells }: SynthesisMatrixProps) {
  if (!findings.length || !documents.length) return null;

  const getCell = (finding: string, doc: string) =>
    cells.find((c) => c.finding === finding && c.document === doc);

  return (
    <div
      style={{
        borderRadius: "12px",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        background: "rgba(255, 255, 255, 0.02)",
        overflow: "hidden",
        marginTop: "16px",
      }}
    >
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
          fontSize: "13px",
          fontWeight: 600,
          color: "rgba(255, 255, 255, 0.8)",
          display: "flex",
          alignItems: "center",
          gap: "8px",
        }}
      >
        <span>📊</span> Cross-Document Synthesis
      </div>

      <div style={{ overflowX: "auto" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "12px",
          }}
        >
          <thead>
            <tr>
              <th
                style={{
                  padding: "10px 12px",
                  textAlign: "left",
                  color: "rgba(255, 255, 255, 0.5)",
                  fontWeight: 600,
                  borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
                  minWidth: "120px",
                }}
              >
                Finding
              </th>
              {documents.map((doc) => (
                <th
                  key={doc}
                  style={{
                    padding: "10px 12px",
                    textAlign: "center",
                    color: "rgba(167, 139, 250, 0.8)",
                    fontWeight: 600,
                    borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
                    maxWidth: "150px",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {doc}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {findings.map((finding, i) => (
              <tr key={i}>
                <td
                  style={{
                    padding: "10px 12px",
                    color: "rgba(255, 255, 255, 0.7)",
                    borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
                  }}
                >
                  {finding}
                </td>
                {documents.map((doc) => {
                  const cell = getCell(finding, doc);
                  const status = cell?.status || "not_found";
                  const info = STATUS_ICONS[status] || STATUS_ICONS.not_found;
                  return (
                    <td
                      key={doc}
                      title={cell?.evidence || ""}
                      style={{
                        padding: "10px 12px",
                        textAlign: "center",
                        borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
                        background: info.bg,
                        cursor: cell?.evidence ? "help" : "default",
                      }}
                    >
                      {info.icon}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
