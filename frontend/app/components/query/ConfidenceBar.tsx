"use client";

import React from "react";

interface ConfidenceBarProps {
  score: number; // 0.0 to 1.0
  showLabel?: boolean;
}

export default function ConfidenceBar({ score, showLabel = true }: ConfidenceBarProps) {
  const percentage = Math.round(score * 100);

  // Color gradient: red → amber → green
  const getColor = (s: number) => {
    if (s >= 0.8)
      return { bg: "rgba(34, 197, 94, 0.15)", fill: "#22c55e", label: "High Confidence" };
    if (s >= 0.5)
      return { bg: "rgba(245, 158, 11, 0.15)", fill: "#f59e0b", label: "Medium Confidence" };
    return { bg: "rgba(239, 68, 68, 0.15)", fill: "#ef4444", label: "Low Confidence" };
  };

  const colors = getColor(score);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "10px", width: "100%" }}>
      <div
        style={{
          flex: 1,
          height: "6px",
          borderRadius: "3px",
          background: colors.bg,
          overflow: "hidden",
          position: "relative",
        }}
      >
        <div
          style={{
            width: `${percentage}%`,
            height: "100%",
            borderRadius: "3px",
            background: `linear-gradient(90deg, ${colors.fill}88, ${colors.fill})`,
            transition: "width 0.8s cubic-bezier(0.4, 0, 0.2, 1)",
          }}
        />
      </div>
      {showLabel && (
        <span
          style={{
            fontSize: "12px",
            fontWeight: 600,
            color: colors.fill,
            whiteSpace: "nowrap",
            letterSpacing: "0.02em",
          }}
        >
          {percentage}% — {colors.label}
        </span>
      )}
    </div>
  );
}
