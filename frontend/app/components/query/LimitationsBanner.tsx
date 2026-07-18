"use client";

import { motion } from "framer-motion";
import { AlertTriangle } from "lucide-react";

interface LimitationsBannerProps {
  content: string;
}

export default function LimitationsBanner({ content }: LimitationsBannerProps) {
  if (!content) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="mt-6 flex items-start gap-3 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4"
    >
      <AlertTriangle className="mt-0.5 shrink-0 text-amber-500" size={18} />
      <div>
        <h4 className="mb-1 text-xs font-semibold tracking-wide text-amber-500/90 uppercase">
          Limitations & Missing Context
        </h4>
        <p className="text-sm leading-relaxed text-amber-500/80">{content}</p>
      </div>
    </motion.div>
  );
}
