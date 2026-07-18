"use client";

import { ShieldAlert } from "lucide-react";
import { motion } from "framer-motion";

export default function InsufficientEvidenceBanner() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-4 flex w-full flex-col items-center justify-center rounded-3xl border-2 border-dashed border-red-500/20 bg-red-500/5 p-8 text-center"
    >
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-red-500/10 text-red-500 shadow-[0_0_30px_rgba(239,68,68,0.15)]">
        <ShieldAlert size={32} />
      </div>
      <h3 className="mb-2 text-xl font-bold tracking-tight text-red-500">
        Insufficient Grounded Evidence
      </h3>
      <p className="text-muted-foreground/80 mx-auto max-w-md text-sm leading-relaxed">
        The retrieved documents do not contain enough relevant information to confidently answer
        your question. To prevent hallucination, the generation has been aborted.
      </p>
      <div className="mt-8 grid w-full max-w-xs grid-cols-2 gap-4">
        <div className="bg-glass-bg border-glass-border rounded-xl border p-3">
          <span className="text-muted-foreground mb-1 block text-[10px] font-bold uppercase">
            Status
          </span>
          <span className="font-mono text-xs text-red-400">REJECTED</span>
        </div>
        <div className="bg-glass-bg border-glass-border rounded-xl border p-3">
          <span className="text-muted-foreground mb-1 block text-[10px] font-bold uppercase">
            Reason
          </span>
          <span className="font-mono text-xs text-red-400">SCORE_TOO_LOW</span>
        </div>
      </div>
    </motion.div>
  );
}
