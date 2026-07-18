"use client";

import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, BrainCircuit } from "lucide-react";
import { useState } from "react";

import { InlineMarkdown } from "./InlineMarkdown";

interface ThinkingPanelProps {
  content: string;
  isStreaming: boolean;
}

export default function ThinkingPanel({ content, isStreaming }: ThinkingPanelProps) {
  const [manualExpanded, setManualExpanded] = useState(false);
  const trimmed = content.trim();
  const expanded = isStreaming || manualExpanded;

  if (!trimmed && !isStreaming) {
    return null;
  }

  return (
    <div className="mb-4 overflow-hidden rounded-lg border border-white/5 bg-white/[0.02] transition-all duration-200">
      <button
        type="button"
        onClick={() => setManualExpanded((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-white/[0.03]"
      >
        <ChevronDown
          size={14}
          className={`text-foreground/30 transition-transform duration-200 ${expanded ? "" : "-rotate-90"}`}
        />
        <div className="flex items-center gap-2">
          <BrainCircuit size={13} className="text-primary/60" />
          <span className="text-foreground/50 text-[11px] font-bold tracking-wider uppercase">
            {isStreaming ? "Thinking..." : "Thought Process"}
          </span>
        </div>
        {isStreaming && (
          <motion.div
            animate={{ opacity: [1, 0.4, 1] }}
            transition={{ repeat: Infinity, duration: 1.5 }}
            className="bg-primary ml-auto h-1.5 w-1.5 rounded-full shadow-[0_0_8px_rgba(var(--primary),0.8)]"
          />
        )}
      </button>

      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeInOut" }}
          >
            <div className="border-t border-white/5 px-4 py-3">
              <div className="prose prose-invert text-foreground/60 max-w-none text-[12px] leading-relaxed">
                <InlineMarkdown content={trimmed} />
                {isStreaming && (
                  <motion.span
                    animate={{ opacity: [1, 0, 1] }}
                    transition={{ repeat: Infinity, duration: 0.8 }}
                    className="bg-primary/40 ml-1 inline-block h-3.5 w-1.5 align-middle"
                  />
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
