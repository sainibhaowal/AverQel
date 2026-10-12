"use client";

import { ExternalLink, FileText, Table2 } from "lucide-react";

interface Citation {
  document_id: string;
  filename?: string;
  page_number?: number;
  source_type?: string;
  source_row_numbers?: number[];
  matched_row_count?: number | null;
}

interface ReferenceTilesProps {
  citations: Citation[];
  onTileClick: (citation: Citation) => void;
}

export default function ReferenceTiles({ citations, onTileClick }: ReferenceTilesProps) {
  if (!citations || citations.length === 0) return null;

  const uniqueCitations = citations.reduce((acc: Citation[], current) => {
    const found = acc.find(
      (item) =>
        item.document_id === current.document_id &&
        item.page_number === current.page_number &&
        item.source_type === current.source_type &&
        (item.source_row_numbers || []).join(",") === (current.source_row_numbers || []).join(","),
    );
    if (!found) {
      return acc.concat([current]);
    }
    return acc;
  }, []);

  return (
    <section className="theme-panel p-4">
      <div className="text-primary/80 mb-4 flex items-center gap-2.5 text-[11px] font-bold tracking-[0.25em] uppercase">
        <FileText size={15} className="stroke-[2.5]" />
        Verification References
      </div>
      <div className="space-y-1.5">
        {uniqueCitations.map((citation, idx) => (
          <button
            key={`${citation.document_id}-${idx}`}
            type="button"
            onClick={() => onTileClick(citation)}
            className="group hover-yellow flex w-full items-center justify-between gap-4 rounded-xl px-2.5 py-2.5 transition-all"
          >
            <div className="flex min-w-0 items-center gap-3">
              <div className="border-primary/30 bg-primary/10 text-primary group-hover:bg-primary/20 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border transition">
                {citation.source_type === "dataset" ? (
                  <Table2 size={14} className="stroke-[2.5]" />
                ) : (
                  <FileText size={14} className="stroke-[2.5]" />
                )}
              </div>
              <div className="min-w-0">
                <div className="text-foreground/90 group-hover:text-primary truncate text-[14px] font-bold tracking-tight transition-colors">
                  {citation.filename || "Security Document"}
                </div>
                <div className="text-foreground/40 mt-0.5 text-[11px] font-medium">
                  {citation.source_type === "dataset"
                    ? `${citation.matched_row_count?.toLocaleString() ?? 0} matching rows · source rows ${
                        citation.source_row_numbers?.slice(0, 5).join(", ") || "available in table"
                      }${(citation.source_row_numbers?.length ?? 0) > 5 ? "…" : ""}`
                    : citation.page_number
                      ? `Located on Page ${citation.page_number}`
                      : "Full document access"}
                </div>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {citation.source_type === "dataset" ? (
                <span className="theme-pill !border-primary/30 !bg-primary/10 !text-primary !px-2 !text-[10px] font-bold">
                  ROWS
                </span>
              ) : citation.page_number ? (
                <span className="theme-pill !border-primary/30 !bg-primary/10 !text-primary !px-2 !text-[10px] font-bold">
                  P.{citation.page_number}
                </span>
              ) : null}
              <ExternalLink
                size={14}
                className="text-muted-foreground/40 group-hover:text-primary stroke-[2.5] transition-colors"
              />
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}
