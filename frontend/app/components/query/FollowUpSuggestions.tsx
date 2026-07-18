"use client";

import { motion } from "framer-motion";
import { MessageSquarePlus } from "lucide-react";

interface FollowUpSuggestionsProps {
  suggestions: string[];
  onSelect: (query: string) => void;
}

export default function FollowUpSuggestions({ suggestions, onSelect }: FollowUpSuggestionsProps) {
  if (!suggestions || suggestions.length === 0) return null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.12 }}
      className="theme-panel rounded-[1.7rem] px-4 py-4 sm:px-5"
    >
      <div className="text-foreground/66 mb-3 flex items-center gap-2 text-[11px] font-semibold tracking-[0.18em] uppercase">
        <MessageSquarePlus size={14} />
        Follow-up questions
      </div>
      <div className="flex flex-wrap gap-2.5">
        {suggestions.map((suggestion, idx) => (
          <button
            key={idx}
            onClick={() => onSelect(suggestion)}
            className="theme-chip text-foreground/80 hover:text-foreground rounded-full px-3.5 py-2 text-sm transition hover:border-cyan-400/24 hover:bg-cyan-500/[0.08] dark:hover:text-white"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </motion.section>
  );
}
