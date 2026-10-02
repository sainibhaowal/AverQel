import { ChevronDown } from "lucide-react";
import { useEffect, useId, useState } from "react";

type ToolDescription = {
  name: string;
  description?: string | null;
};

const SUMMARY_LIMIT = 180;

function compactText(value: string): string {
  return value
    .replace(/<example[\s\S]*$/i, "")
    .replace(/<\/?[a-z][^>]*>/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function summarizeToolDescription(description?: string | null): string {
  const text = compactText(description || "");
  if (!text) return "No short description provided. Open details for the provider documentation.";

  const firstSentence = text.match(/^.*?[.!?](?:\s|$)/)?.[0]?.trim() || text;
  if (firstSentence.length <= SUMMARY_LIMIT) return firstSentence;
  return `${firstSentence.slice(0, SUMMARY_LIMIT - 1).trimEnd()}…`;
}

export default function MCPToolDescription({ tool }: { tool: ToolDescription }) {
  const [expanded, setExpanded] = useState(false);
  const [renderDetails, setRenderDetails] = useState(false);
  const detailsId = useId();
  const description = tool.description?.trim() || "";

  useEffect(() => {
    if (expanded) return;
    const timeout = window.setTimeout(() => setRenderDetails(false), 160);
    return () => window.clearTimeout(timeout);
  }, [expanded]);

  return (
    <div className="min-w-0">
      <div className="flex items-start gap-3">
        <button
          type="button"
          aria-expanded={expanded}
          aria-controls={detailsId}
          aria-label={`${expanded ? "Hide" : "Show"} full details for ${tool.name}`}
          onClick={() => {
            if (!expanded) setRenderDetails(true);
            setExpanded((current) => !current);
          }}
          className="mcp-tool-toggle mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-white/10 bg-white/[0.03] text-white/45 transition hover:border-cyan-300/30 hover:bg-cyan-300/10 hover:text-cyan-100 focus-visible:ring-2 focus-visible:ring-cyan-300/60 focus-visible:outline-none"
        >
          <ChevronDown
            className={`h-3.5 w-3.5 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
            aria-hidden="true"
          />
        </button>
        <div className="min-w-0">
          <p className="truncate font-mono text-sm text-emerald-200" title={tool.name}>
            {tool.name}
          </p>
          <p className="mt-1 text-xs leading-5 text-white/50">
            {summarizeToolDescription(tool.description)}
          </p>
        </div>
      </div>
      {renderDetails ? (
        <div
          id={detailsId}
          aria-hidden={!expanded}
          className={`mcp-tool-details ${expanded ? "mcp-tool-details-open" : ""}`}
        >
          <div className="mcp-tool-details-inner">
            <div className="mcp-tool-docs mt-3 max-h-72 overflow-y-auto rounded-xl border border-cyan-300/10 bg-black/20 p-3 shadow-inner shadow-black/20">
              <p className="mcp-tool-docs-label mb-2 text-[10px] font-semibold tracking-[0.16em] text-cyan-200/60 uppercase">
                Provider documentation
              </p>
              <p className="text-xs leading-5 break-words whitespace-pre-wrap text-white/65">
                {description || "No additional documentation is available for this tool."}
              </p>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
