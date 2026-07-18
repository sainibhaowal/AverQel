"use client";

import React from "react";

interface TableRendererProps {
  headers: string[];
  rows: string[][];
  pageNumber?: number;
  caption?: string;
}

export default function TableRenderer({ headers, rows, pageNumber, caption }: TableRendererProps) {
  if (!headers.length && !rows.length) return null;

  return (
    <div
      style={{
        borderRadius: "10px",
        border: "1px solid rgba(255, 255, 255, 0.08)",
        background: "rgba(255, 255, 255, 0.02)",
        overflow: "hidden",
        marginTop: "12px",
      }}
    >
      {(caption || pageNumber) && (
        <div
          style={{
            padding: "8px 14px",
            borderBottom: "1px solid rgba(255, 255, 255, 0.06)",
            fontSize: "12px",
            color: "rgba(255, 255, 255, 0.5)",
            display: "flex",
            alignItems: "center",
            gap: "8px",
          }}
        >
          <span>📋</span>
          {caption || "Extracted Table"}
          {pageNumber && (
            <span style={{ marginLeft: "auto", opacity: 0.6 }}>Page {pageNumber}</span>
          )}
        </div>
      )}

      <div style={{ overflowX: "auto" }}>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontSize: "12px",
          }}
        >
          {headers.length > 0 && (
            <thead>
              <tr>
                {headers.map((h, i) => (
                  <th
                    key={i}
                    style={{
                      padding: "8px 12px",
                      textAlign: "left",
                      color: "rgba(167, 139, 250, 0.8)",
                      fontWeight: 600,
                      borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {rows.map((row, ri) => (
              <tr
                key={ri}
                style={{
                  background: ri % 2 === 0 ? "transparent" : "rgba(255, 255, 255, 0.02)",
                }}
              >
                {row.map((cell, ci) => (
                  <td
                    key={ci}
                    style={{
                      padding: "7px 12px",
                      color: "rgba(255, 255, 255, 0.7)",
                      borderBottom: "1px solid rgba(255, 255, 255, 0.04)",
                    }}
                  >
                    {cell}
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
