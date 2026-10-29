"use client";

import { motion, useReducedMotion } from "framer-motion";
import { useId } from "react";

export type DeepSpaceVoiceState = "idle" | "listening" | "thinking" | "speaking";

type VoicePresentation = {
  label: string;
  detail: string;
  color: string;
  softColor: string;
};

const PRESENTATIONS: Record<Exclude<DeepSpaceVoiceState, "idle">, VoicePresentation> = {
  listening: {
    label: "Listening",
    detail: "Microphone is live",
    color: "#4ade80",
    softColor: "#22c55e",
  },
  thinking: {
    label: "Working",
    detail: "DeepSpace is processing your request",
    color: "#22d3ee",
    softColor: "#a855f7",
  },
  speaking: {
    label: "Speaking",
    detail: "Audio reply is playing",
    color: "#60a5fa",
    softColor: "#c084fc",
  },
};

const WAVE_PATHS = [
  "M2 20 C 10 20, 10 8, 18 8 S 26 32, 34 32 S 42 8, 50 8 S 58 20, 66 20 S 74 12, 82 12 S 90 28, 98 28 S 106 14, 114 14 S 122 20, 130 20",
  "M2 20 C 10 20, 10 28, 18 28 S 26 10, 34 10 S 42 28, 50 28 S 58 20, 66 20 S 74 30, 82 30 S 90 10, 98 10 S 106 26, 114 26 S 122 20, 130 20",
];

function normaliseActivityLevel(level: number) {
  if (!Number.isFinite(level)) return 0;
  return Math.min(1, Math.max(0, level));
}

export default function DeepSpaceVoicePresence({
  state,
  activityLevel = 0,
}: {
  state: DeepSpaceVoiceState;
  activityLevel?: number;
}) {
  const reducedMotion = useReducedMotion();
  const gradientId = `deepspace-voice-${useId().replace(/:/g, "")}`;
  const level = normaliseActivityLevel(activityLevel);

  if (state === "idle") return null;

  const presentation = PRESENTATIONS[state];
  const listening = state === "listening";
  const thinking = state === "thinking";
  const waveformScale = 0.7 + level * 0.55;
  const endingColor = thinking ? "#fb7185" : presentation.color;

  return (
    <div
      aria-label={`Voice mode is ${presentation.label.toLowerCase()}`}
      aria-live="polite"
      className="pointer-events-none flex h-7 shrink-0 items-center gap-1.5 px-1"
      data-testid="deepspace-voice-presence"
      data-voice-state={state}
      role="status"
    >
      <div
        aria-hidden="true"
        className="relative flex h-6 w-14 shrink-0 items-center overflow-hidden rounded-lg border border-white/8 bg-black/20 px-1.5 sm:w-20"
        data-testid="deepspace-voice-waveform"
        data-voice-level={level.toFixed(2)}
      >
        {listening ? (
          <div className="flex h-full w-full items-center justify-between gap-0.5">
            {Array.from({ length: 11 }, (_, index) => {
              const base = 0.32 + ((index * 17) % 5) * 0.08;
              const peak = Math.min(1.35, base + 0.36 + level * 1.15);
              return (
                <motion.span
                  key={index}
                  animate={
                    reducedMotion
                      ? { scaleY: Math.min(1, base + level * 0.45) }
                      : { scaleY: [base, peak, Math.max(0.25, base * 0.78)] }
                  }
                  className="h-4 flex-1 origin-center rounded-sm bg-emerald-400 shadow-[0_0_9px_rgba(74,222,128,0.65)]"
                  data-testid="deepspace-voice-wave-bar"
                  transition={{
                    duration: 0.52 + (index % 4) * 0.09,
                    ease: "easeInOut",
                    repeat: reducedMotion ? 0 : Infinity,
                    repeatType: "mirror",
                    delay: (index % 6) * 0.045,
                  }}
                />
              );
            })}
          </div>
        ) : (
          <motion.svg
            animate={reducedMotion ? { scaleY: 1 } : { scaleY: [0.9, waveformScale, 0.9] }}
            className="h-6 w-full origin-center"
            fill="none"
            transition={{ duration: thinking ? 1.25 : 0.86, ease: "easeInOut", repeat: Infinity }}
            viewBox="0 0 132 40"
          >
            <defs>
              <linearGradient id={gradientId} x1="0" x2="1" y1="0" y2="0">
                <stop offset="0%" stopColor={presentation.color} />
                <stop offset="42%" stopColor={presentation.softColor} />
                <stop offset="72%" stopColor={endingColor} />
                <stop offset="100%" stopColor={presentation.color} />
              </linearGradient>
            </defs>
            {WAVE_PATHS.map((path, index) => (
              <motion.path
                key={path}
                className={
                  index === 1
                    ? "deepspace-voice-wave-trace deepspace-voice-wave-trace--second"
                    : "deepspace-voice-wave-trace"
                }
                animate={
                  reducedMotion
                    ? { opacity: index === 0 ? 0.94 : 0.48 }
                    : {
                        opacity: index === 0 ? [0.62, 1, 0.62] : [0.25, 0.76, 0.25],
                      }
                }
                d={path}
                data-testid="deepspace-voice-wave-trace"
                pathLength={1}
                stroke={`url(#${gradientId})`}
                strokeDasharray="0.14 0.08"
                strokeLinecap="round"
                strokeWidth={index === 0 ? 2.6 : 1.5}
                transition={{
                  duration: thinking ? 1.8 + index * 0.24 : 1.1 + index * 0.16,
                  ease: "linear",
                  repeat: reducedMotion ? 0 : Infinity,
                }}
              />
            ))}
          </motion.svg>
        )}
      </div>

      <div className="min-w-0">
        <p className="text-[9px] leading-none font-semibold tracking-wide text-white/80 uppercase">
          {presentation.label}
        </p>
        <span className="sr-only">{presentation.detail}</span>
      </div>
    </div>
  );
}
