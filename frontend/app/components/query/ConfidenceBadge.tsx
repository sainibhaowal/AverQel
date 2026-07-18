"use client";

import { motion } from "framer-motion";
import { ShieldCheck, ShieldAlert, Shield } from "lucide-react";

interface ConfidenceBadgeProps {
  score: number;
}

export default function ConfidenceBadge({ score }: ConfidenceBadgeProps) {
  let colorClass = "bg-green-500/10 text-green-400 border-green-500/20";
  let Icon = ShieldCheck;
  let label = "High Confidence";

  if (score < 0.4) {
    colorClass = "bg-red-500/10 text-red-400 border-red-500/20";
    Icon = ShieldAlert;
    label = "Insufficient Evidence";
  } else if (score < 0.7) {
    colorClass = "bg-yellow-500/10 text-yellow-500 border-yellow-500/20";
    Icon = Shield;
    label = "Medium Confidence";
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${colorClass}`}
    >
      <Icon size={14} className="opacity-80" />
      <span>{label}</span>
      <span className="ml-1 font-mono text-[10px] opacity-60">{(score * 100).toFixed(0)}%</span>
    </motion.div>
  );
}
