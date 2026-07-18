"use client";

import React from "react";
import ConfidenceBar from "./ConfidenceBar";

interface ProvenanceFooterProps {
  confidenceScore: number;
  searchStrategySummary: string;
  traceId: string;
  chunksEvaluated?: number;
}

export default function ProvenanceFooter({
  confidenceScore,
  searchStrategySummary,
  traceId,
  chunksEvaluated,
}: ProvenanceFooterProps) {
  return (
    <div
      style={{
        padding: "10px 16px",
        borderRadius: "10px",
        border: "1px solid rgba(255, 255, 255, 0.06)",
        background: "rgba(255, 255, 255, 0.02)",
        display: "flex",
        alignItems: "center",
        gap: "16px",
        marginTop: "12px",
        flexWrap: "wrap",
      }}
    >
      {/* Confidence Bar */}
      <div style={{ flex: "1 1 200px", minWidth: "150px" }}>
        <ConfidenceBar score={confidenceScore} showLabel={true} />
      </div>

      {/* Search Strategy */}
      <div
        style={{
          fontSize: "11px",
          color: "rgba(255, 255, 255, 0.45)",
          display: "flex",
          alignItems: "center",
          gap: "6px",
          whiteSpace: "nowrap",
        }}
      >
        <span style={{ opacity: 0.5 }}>🔎</span>
        {searchStrategySummary}
      </div>

      {/* Chunks evaluated */}
      {chunksEvaluated !== undefined && (
        <div
          style={{
            fontSize: "11px",
            color: "rgba(255, 255, 255, 0.35)",
            whiteSpace: "nowrap",
          }}
        >
          {chunksEvaluated} chunks
        </div>
      )}

      {/* Trace ID */}
      <div
        style={{
          fontSize: "10px",
          color: "rgba(255, 255, 255, 0.25)",
          fontFamily: "monospace",
          whiteSpace: "nowrap",
          marginLeft: "auto",
        }}
      >
        {traceId.slice(0, 12)}…
      </div>
    </div>
  );
}
