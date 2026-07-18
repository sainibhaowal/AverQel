"use client";

import { motion } from "framer-motion";
import { ListChecks } from "lucide-react";
import { renderTextWithCitations } from "./InlineCitation";

interface KeyFindingsProps {
  findings: string[];
}

export default function KeyFindings({ findings }: KeyFindingsProps) {
  if (!findings || findings.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-primary/5 mb-6 rounded-2xl border-none p-5"
    >
      <div className="text-primary mb-4 flex items-center gap-2 text-sm font-semibold tracking-wide">
        <ListChecks size={18} />
        <h3 className="uppercase">Key Findings</h3>
      </div>
      <ul className="space-y-3">
        {findings
          .filter((finding) => typeof finding === "string" && finding.trim().length > 0)
          .map((finding, idx) => (
            <li
              key={idx}
              className="text-foreground/90 flex items-start gap-3 text-sm leading-relaxed"
            >
              <span className="bg-primary/50 mt-2 h-1.5 w-1.5 shrink-0 rounded-full" />
              <span>{renderTextWithCitations(finding)}</span>
            </li>
          ))}
      </ul>
    </motion.div>
  );
}
