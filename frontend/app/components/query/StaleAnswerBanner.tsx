"use client";

import React from "react";

interface StaleAnswerBannerProps {
  onRerun: () => void;
  documentName?: string;
}

export default function StaleAnswerBanner({ onRerun, documentName }: StaleAnswerBannerProps) {
  return (
    <div
      style={{
        padding: "10px 16px",
        borderRadius: "10px",
        border: "1px solid rgba(245, 158, 11, 0.3)",
        background: "rgba(245, 158, 11, 0.08)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "12px",
        marginBottom: "12px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <span style={{ fontSize: "16px" }}>⚠️</span>
        <span style={{ fontSize: "13px", color: "rgba(245, 158, 11, 0.9)", fontWeight: 500 }}>
          {documentName
            ? `"${documentName}" has been updated since this answer was generated.`
            : "Source documents have been updated since this answer was generated."}
        </span>
      </div>
      <button
        onClick={onRerun}
        style={{
          padding: "6px 14px",
          borderRadius: "8px",
          border: "1px solid rgba(245, 158, 11, 0.4)",
          background: "rgba(245, 158, 11, 0.15)",
          color: "#f59e0b",
          fontSize: "12px",
          fontWeight: 600,
          cursor: "pointer",
          whiteSpace: "nowrap",
          transition: "all 0.2s ease",
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = "rgba(245, 158, 11, 0.25)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = "rgba(245, 158, 11, 0.15)";
        }}
      >
        Re-run Query
      </button>
    </div>
  );
}
