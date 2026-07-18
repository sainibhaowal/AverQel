"use client";

interface InlineCitationProps {
  index: number;
  onClick?: () => void;
}

export default function InlineCitation({ index, onClick }: InlineCitationProps) {
  return (
    <button
      onClick={(e) => {
        e.preventDefault();
        if (onClick) {
          onClick();
          return;
        }
        const el = document.getElementById(`citation-${index}`);
        if (el) {
          el.scrollIntoView({ behavior: "smooth", block: "center" });
          // Add temporary emphasis classes
          el.classList.add("ring-2", "ring-primary/50", "bg-primary/5");
          setTimeout(() => {
            el.classList.remove("ring-2", "ring-primary/50", "bg-primary/5");
          }, 3000);
        }
      }}
      className="bg-primary/10 text-primary hover:bg-primary hover:text-primary-foreground mx-1 inline-flex h-4 w-4 cursor-pointer items-center justify-center rounded-full align-super text-[10px] font-bold tracking-tighter transition-colors"
      aria-label={`Go to citation ${index}`}
    >
      {index}
    </button>
  );
}

/**
 * Helper to process text containing [N] citations
 * and replace them with React components.
 */
import React from "react";

export function renderTextWithCitations(text: string) {
  if (typeof text !== "string") {
    return <React.Fragment>{String(text)}</React.Fragment>;
  }
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/\[(\d+)\]/);
    if (match) {
      return <InlineCitation key={i} index={parseInt(match[1])} />;
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}
