"use client";

import React from "react";

interface FollowUpChipsProps {
  suggestions: string[];
  onSelect: (query: string) => void;
}

export default function FollowUpChips({ suggestions, onSelect }: FollowUpChipsProps) {
  if (!suggestions || suggestions.length === 0) return null;

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "8px",
        marginTop: "12px",
      }}
    >
      <span
        style={{
          fontSize: "12px",
          color: "rgba(255, 255, 255, 0.4)",
          fontWeight: 500,
          alignSelf: "center",
        }}
      >
        Follow up:
      </span>
      {suggestions.map((suggestion, i) => (
        <button
          key={i}
          onClick={() => onSelect(suggestion)}
          style={{
            padding: "6px 14px",
            borderRadius: "20px",
            border: "1px solid rgba(139, 92, 246, 0.3)",
            background: "rgba(139, 92, 246, 0.08)",
            color: "rgba(167, 139, 250, 0.9)",
            fontSize: "12px",
            fontWeight: 500,
            cursor: "pointer",
            transition: "all 0.2s ease",
            whiteSpace: "nowrap",
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "rgba(139, 92, 246, 0.2)";
            e.currentTarget.style.borderColor = "rgba(139, 92, 246, 0.5)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "rgba(139, 92, 246, 0.08)";
            e.currentTarget.style.borderColor = "rgba(139, 92, 246, 0.3)";
          }}
        >
          {suggestion}
        </button>
      ))}
    </div>
  );
}
