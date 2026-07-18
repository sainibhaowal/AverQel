"use client";

import { motion } from "framer-motion";
import { FileText, ExternalLink, ChevronDown, ChevronUp } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

interface CitationCardProps {
  rank: number;
  documentName: string;
  documentId: string;
  snippet: string;
  score: number;
  sourceType: string;
  sectionHeader?: string;
  pageNumber?: number;
}

export default function CitationCard({
  rank,
  documentName,
  documentId,
  snippet,
  score,
  sourceType,
  sectionHeader,
  pageNumber,
}: CitationCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: rank * 0.1 }}
      id={`citation-${rank}`}
      className="glass-card group hover:border-primary/40 hover:shadow-primary/5 p-5 transition-all hover:shadow-lg"
    >
      <div className="mb-4 flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="border-primary/20 bg-primary/10 text-primary flex h-6 w-6 items-center justify-center rounded-full border text-[10px] font-bold">
            {rank}
          </div>
          <Link
            href={`/dashboard/documents/${documentId}`}
            className="text-muted-foreground hover:text-primary flex items-center gap-2 text-xs font-bold tracking-widest uppercase transition-colors"
          >
            <FileText size={14} />
            <span className="max-w-[150px] truncate">{documentName}</span>
            {pageNumber && <span className="opacity-50">Pg {pageNumber}</span>}
            <ExternalLink size={10} />
          </Link>
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-3">
            <span
              className={`rounded-full border px-2 py-0.5 text-[8px] font-bold tracking-wider uppercase ${
                sourceType === "vision"
                  ? "border-purple-500/20 bg-purple-500/10 text-purple-400"
                  : sourceType === "ocr"
                    ? "border-amber-500/20 bg-amber-500/10 text-amber-400"
                    : "border-primary/20 bg-primary/10 text-primary"
              } `}
            >
              {sourceType}
            </span>
            <div className="text-muted-foreground font-mono text-[10px] opacity-60">
              {(score * 100).toFixed(1)}% Match
            </div>
          </div>
          {sectionHeader && (
            <div className="text-primary/80 max-w-[180px] truncate text-[9px] font-bold tracking-widest uppercase">
              {sectionHeader.replace(/^#+\s*/, "")}
            </div>
          )}
        </div>
      </div>

      <div className="relative">
        <div className="bg-primary/30 absolute top-0 bottom-0 left-0 w-0.5 rounded-full" />
        <p
          className={`text-foreground/80 pl-4 text-sm leading-relaxed italic ${isExpanded ? "" : "line-clamp-4"}`}
        >
          &quot;{snippet}&quot;
        </p>
        {snippet.length > 150 && (
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-primary mt-2 ml-4 flex items-center gap-1 text-[10px] font-bold tracking-wider uppercase transition-colors hover:brightness-110"
          >
            {isExpanded ? "Show Less" : "Show More"}
            {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        )}
      </div>

      <div className="border-glass-border mt-4 border-t pt-4">
        <div className="bg-muted border-glass-border/30 h-1 w-full overflow-hidden rounded-full border">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${score * 100}%` }}
            transition={{ duration: 1, ease: "easeOut" }}
            className={`h-full rounded-full ${score > 0.8 ? "bg-success" : score > 0.5 ? "bg-primary" : "bg-danger"}`}
          />
        </div>
      </div>
    </motion.div>
  );
}
