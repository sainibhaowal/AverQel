"use client";
import { motion } from "framer-motion";

interface StreamingTypingIndicatorProps {
  phase?: "searching" | "grounding" | "answering";
}

function labelForPhase(phase?: StreamingTypingIndicatorProps["phase"]) {
  switch (phase) {
    case "searching":
      return "Searching evidence";
    case "grounding":
      return "Grounding answer";
    case "answering":
    default:
      return "Streaming response";
  }
}

function helperForPhase(phase?: StreamingTypingIndicatorProps["phase"]) {
  switch (phase) {
    case "searching":
      return "Scanning the workspace for grounded signals.";
    case "grounding":
      return "Cross-checking evidence and assembling the final path.";
    case "answering":
    default:
      return "Writing the response as validated content arrives.";
  }
}

const PHASE_ACCENT = {
  searching: "from-primary/16 to-primary/8 border-primary/18 text-primary",
  grounding:
    "from-emerald-500/16 to-primary/8 border-emerald-500/18 text-emerald-800 dark:text-emerald-50/86",
  answering:
    "from-violet-500/14 to-primary/8 border-violet-500/18 text-violet-800 dark:text-violet-50/86",
} as const;

function PhaseIcon({ phase }: { phase: StreamingTypingIndicatorProps["phase"] }) {
  switch (phase) {
    case "searching":
      return (
        <div className="relative flex h-5 w-5 items-center justify-center">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
            className="text-primary/40 absolute inset-0 flex items-center justify-center"
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
            >
              <circle cx="12" cy="12" r="10" strokeDasharray="4 4" />
            </svg>
          </motion.div>
          <motion.div
            animate={{
              scale: [1, 1.2, 1],
              opacity: [0.7, 1, 0.7],
            }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            className="text-primary relative z-10"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.3-4.3" />
            </svg>
          </motion.div>
        </div>
      );
    case "grounding":
      return (
        <div className="relative flex h-5 w-5 items-center justify-center text-emerald-500">
          <motion.div
            className="absolute inset-0 rounded-full border border-emerald-500/30"
            animate={{ scale: [1, 1.5, 1], opacity: [0.3, 0, 0.3] }}
            transition={{ duration: 2, repeat: Infinity }}
          />
          <motion.div
            animate={{
              rotateY: [0, 180, 360],
            }}
            transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
              <path d="m9 12 2 2 4-4" />
            </svg>
          </motion.div>
        </div>
      );
    case "answering":
    default:
      return (
        <div className="relative flex h-5 w-5 items-center justify-center text-violet-500">
          <div className="absolute inset-0 flex items-center justify-center">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                className="absolute h-full w-full rounded-full border border-violet-500/20"
                animate={{ scale: [1, 1.4], opacity: [0.5, 0] }}
                transition={{ duration: 1.5, repeat: Infinity, delay: i * 0.5 }}
              />
            ))}
          </div>
          <motion.div
            animate={{
              scale: [1, 1.1, 1],
              rotate: [0, 5, -5, 0],
            }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
            className="relative z-10"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
            </svg>
          </motion.div>
        </div>
      );
  }
}

export default function StreamingTypingIndicator({
  phase = "answering",
}: StreamingTypingIndicatorProps) {
  return (
    <div className={`rounded-[1.35rem] border bg-gradient-to-r px-4 py-3.5 ${PHASE_ACCENT[phase]}`}>
      <div className="theme-chip inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[10px] font-bold tracking-[0.22em] uppercase">
        <PhaseIcon phase={phase} />
        {labelForPhase(phase)}
      </div>
      <p className="text-foreground/66 mt-2.5 text-sm leading-6">{helperForPhase(phase)}</p>
    </div>
  );
}
