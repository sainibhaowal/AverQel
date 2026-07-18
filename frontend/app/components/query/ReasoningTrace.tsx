"use client";

import React, { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Activity, ChevronDown, Network } from "lucide-react";

export interface ReasoningTraceData {
  chunks_searched: number;
  chunks_evaluated: number;
  chunks_selected: number;
  chunks_rejected: number;
  rejection_reasons: string[];
  search_strategy: string;
  timing_ms: Record<string, number>;
  search_strategy_summary: string;
  trace_id: string;
}

interface ReasoningTraceProps {
  trace: ReasoningTraceData;
  confidence?: number;
}

export default function ReasoningTrace({ trace, confidence = 0 }: ReasoningTraceProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <section className="theme-panel overflow-hidden rounded-[1.65rem]">
      <button
        onClick={() => setIsOpen((value) => !value)}
        className="hover-yellow flex w-full items-center justify-between px-5 py-4 text-left transition"
      >
        <div>
          <div className="text-primary dark:text-primary/80 flex items-center gap-2.5 text-[11px] font-black tracking-[0.25em] uppercase">
            <Network size={14} className="stroke-[2.5]" />
            Analytic Reasoning Trace
          </div>
          <div className="text-foreground/40 mt-1 text-xs font-medium">
            Confidence Score: {(confidence * 100).toFixed(1)}%
          </div>
        </div>
        <ChevronDown
          size={18}
          className={
            isOpen
              ? "text-primary dark:text-primary rotate-180 transition-transform"
              : "text-foreground/30 transition-transform"
          }
        />
      </button>

      <AnimatePresence>
        {isOpen ? (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="border-glass-border border-t px-5 py-5"
          >
            <div className="mb-4 flex items-center gap-2.5">
              <span className="theme-pill !border-info/20 !bg-info/10 !text-info dark:!border-primary/20 dark:!bg-primary/10 dark:!text-primary">
                <Activity size={12} className="stroke-[2.5]" />
                <span className="font-mono text-[11px] tracking-tight">
                  {trace.trace_id || "trc_identity_pending"}
                </span>
              </span>
            </div>

            <div className="bg-info/5 border-info/20 text-info dark:border-glass-border dark:text-foreground/80 mb-5 rounded-2xl border px-4 py-4 text-[14px] leading-relaxed font-bold dark:bg-white/[0.02]">
              {trace.search_strategy_summary || `${trace.search_strategy} search strategy executed`}
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: "Searched", value: trace.chunks_searched },
                { label: "Evaluated", value: trace.chunks_evaluated },
                { label: "Selected", value: trace.chunks_selected },
                { label: "Rejected", value: trace.chunks_rejected },
              ].map((stat) => (
                <div
                  key={stat.label}
                  className="theme-chip rounded-2xl px-4 py-4 text-center transition-all hover:translate-y-[-2px]"
                >
                  <div className="text-foreground text-2xl font-bold tracking-tight">
                    {stat.value}
                  </div>
                  <div className="text-primary dark:text-primary/60 mt-1.5 text-[10px] font-black tracking-wider uppercase">
                    {stat.label}
                  </div>
                </div>
              ))}
            </div>

            {trace.rejection_reasons && trace.rejection_reasons.length > 0 ? (
              <div className="text-foreground/72 mt-4 text-sm leading-7">
                <div className="text-foreground/56 mb-2 text-[11px] font-semibold tracking-[0.18em] uppercase">
                  Rejection reasons
                </div>
                <ul className="list-disc space-y-1 pl-5">
                  {trace.rejection_reasons.map((reason, index) => (
                    <li key={index}>{reason}</li>
                  ))}
                </ul>
              </div>
            ) : null}

            {Object.keys(trace.timing_ms || {}).length > 0 ? (
              <div className="border-glass-border/60 text-foreground/44 mt-4 flex flex-wrap gap-3 border-t pt-3 font-mono text-[11px]">
                {Object.entries(trace.timing_ms).map(([stage, ms]) => (
                  <span key={stage}>
                    {stage}: {ms.toFixed(1)}ms
                  </span>
                ))}
              </div>
            ) : null}
          </motion.div>
        ) : null}
      </AnimatePresence>
    </section>
  );
}
