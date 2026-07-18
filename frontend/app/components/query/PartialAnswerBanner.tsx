"use client";

import { AlertCircle } from "lucide-react";
import { motion } from "framer-motion";

export default function PartialAnswerBanner() {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="mb-4 flex w-full items-center gap-3 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-500/90"
    >
      <AlertCircle size={24} className="shrink-0" />
      <div>
        <h4 className="mb-0.5 text-xs font-bold tracking-wide text-amber-500 uppercase">
          Partial Context (Verification Recommended)
        </h4>
        <p className="text-[13px] leading-relaxed text-amber-600/90 opacity-90">
          The system found some relevant information, but the overall confidence score is medium.
          The answer below may be incomplete or extrapolated. Please carefully review the provided
          citations.
        </p>
      </div>
    </motion.div>
  );
}
