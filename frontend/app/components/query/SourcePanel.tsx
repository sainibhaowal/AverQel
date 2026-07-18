"use client";

import { BookOpen } from "lucide-react";
import CitationCard from "./CitationCard";

interface Citation {
  document_id: string;
  chunk_id: string;
  filename?: string;
  snippet: string;
  similarity_score: number;
  source_type?: string;
  section_header?: string;
  page_number?: number;
}

interface SourcePanelProps {
  citations: Citation[];
}

export default function SourcePanel({ citations }: SourcePanelProps) {
  if (!citations || citations.length === 0) {
    return (
      <div className="bg-muted/5 border-glass-border/30 flex w-full shrink-0 flex-col items-center justify-center border-l p-6 text-center sm:w-[min(400px,100vw)]">
        <div className="bg-primary/10 text-primary/50 mb-4 flex h-12 w-12 items-center justify-center rounded-full">
          <BookOpen strokeWidth={1.5} />
        </div>
        <p className="text-muted-foreground/60 text-sm">
          No sources to display. Ask a question to see grounded evidence.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-muted/10 border-glass-border relative flex w-full shrink-0 flex-col border-l sm:w-[min(400px,100vw)]">
      <div className="border-glass-border bg-glass-bg/80 sticky top-0 z-10 flex items-center gap-2 border-b p-4 shadow-sm shadow-black/5 backdrop-blur-md">
        <BookOpen size={16} className="text-primary" />
        <h3 className="text-foreground text-sm font-bold tracking-wide uppercase">
          Grounded Evidence
        </h3>
        <span className="text-primary bg-primary/10 border-primary/20 ml-auto rounded-full border px-2.5 py-0.5 text-[10px] font-bold">
          {citations.length} Sources
        </span>
      </div>
      <div className="custom-scrollbar flex-1 space-y-4 overflow-y-auto p-4">
        {citations.map((cit, idx) => (
          <CitationCard
            key={cit.chunk_id || idx}
            rank={idx + 1}
            documentId={cit.document_id}
            documentName={cit.filename || `Doc-${cit.document_id.slice(0, 4)}`}
            snippet={cit.snippet}
            score={cit.similarity_score}
            sourceType={cit.source_type || "text"}
            sectionHeader={cit.section_header}
            pageNumber={cit.page_number}
          />
        ))}
      </div>
    </div>
  );
}
