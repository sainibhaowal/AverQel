"use client";

import { BrainCircuit } from "lucide-react";
import DeepSpaceMarkdownRenderer from "./DeepSpaceMarkdownRenderer";

export default function DeepSpaceThinkingPanel({ content, isStreaming }: { content: string; isStreaming: boolean }) {
  if (!content.trim() && !isStreaming) return null;
  return (
    <details open={isStreaming} className="mb-4 rounded-lg border border-white/5 bg-white/[0.02]">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-[11px] font-bold tracking-wider text-foreground/50 uppercase">
        <BrainCircuit size={13} className="text-primary/60" />
        {isStreaming ? "Thinking…" : "Thought Process"}
      </summary>
      <div className="border-t border-white/5 px-4 py-3 text-xs text-foreground/60">
        <DeepSpaceMarkdownRenderer content={content} streaming={isStreaming} />
      </div>
    </details>
  );
}
