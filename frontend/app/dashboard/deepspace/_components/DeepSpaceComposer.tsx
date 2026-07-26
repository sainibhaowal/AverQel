"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Bot, ChevronDown, Check, Mic, MicOff, Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface DeepSpaceComposerProps {
  query: string;
  isStreaming: boolean;
  onQueryChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  modelName?: string | null;
  availableModels?: Array<{
    providerId: string;
    modelName: string;
    displayName: string;
    contextWindow?: number | null;
    contextWindowSource?: string | null;
  }>;
  onModelSelect?: (providerId: string, modelName: string) => void;
  voiceState?: "idle" | "listening" | "thinking" | "speaking";
  contextUsedTokens?: number | null;
  contextLimit?: number | null;
  sttActive?: boolean;
  ttsActive?: boolean;
  onSttToggle?: () => void;
  onTtsToggle?: () => void;
  voiceLabel?: string;
}

function SendIcon() {
  return (
    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2.5}
        d="M13 5l7 7m0 0l-7 7m7-7H6"
      />
    </svg>
  );
}

// High-fidelity Neural Pulsar animation for streaming state
function StreamingIcon() {
  return (
    <div className="relative flex h-6 w-6 items-center justify-center">
      {/* Central Pulsar Core */}
      <motion.div
        className="relative z-10 h-2.5 w-2.5 rounded-full bg-white shadow-[0_0_15px_rgba(255,255,255,0.8)]"
        animate={{
          scale: [1, 1.4, 1],
          boxShadow: [
            "0 0 10px rgba(255,255,255,0.5)",
            "0 0 25px rgba(255,255,255,0.9), 0 0 45px rgba(255,255,255,0.4)",
            "0 0 10px rgba(255,255,255,0.5)",
          ],
        }}
        transition={{
          duration: 1.2,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />

      {/* Resonance Rings */}
      {[0, 1, 2].map((i) => (
        <motion.div
          key={`ring-${i}`}
          className="absolute rounded-full border border-white/40"
          initial={{ width: 6, height: 6, opacity: 0 }}
          animate={{
            width: [6, 28],
            height: [6, 28],
            opacity: [0, 0.5, 0],
          }}
          transition={{
            duration: 1.8,
            repeat: Infinity,
            delay: i * 0.6,
            ease: "easeOut",
          }}
        />
      ))}

      {/* Orbital Data Particles */}
      {[0, 1, 2, 3].map((i) => (
        <motion.div
          key={`particle-${i}`}
          className="absolute h-1 w-1 rounded-full bg-white/80"
          animate={{
            rotate: [i * 90, i * 90 + 360],
            scale: [0.8, 1.2, 0.8],
          }}
          transition={{
            rotate: { duration: 2.5 + i * 0.5, repeat: Infinity, ease: "linear" },
            scale: { duration: 1.5, repeat: Infinity, ease: "easeInOut" },
          }}
          style={{
            originX: "50%",
            originY: "50%",
            paddingLeft: "11px", // Radius of orbit
          }}
        />
      ))}

      {/* Energy Field Glow */}
      <motion.div
        className="absolute inset-0 rounded-full bg-white/20 blur-xl"
        animate={{
          scale: [0.8, 1.5, 0.8],
          opacity: [0.1, 0.4, 0.1],
        }}
        transition={{
          duration: 2,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />
    </div>
  );
}

export default function DeepSpaceComposer({
  query,
  isStreaming,
  onQueryChange,
  onSubmit,
  onStop,
  modelName,
  availableModels = [],
  onModelSelect,
  voiceState = "idle",
  contextUsedTokens = null,
  contextLimit = null,
  sttActive = false,
  ttsActive = false,
  onSttToggle,
  onTtsToggle,
  voiceLabel = "",
}: DeepSpaceComposerProps) {
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setModelDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => document.removeEventListener("mousedown", handleOutsideClick);
  }, []);

  const borderHighlight = "border-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.18)]";

  const shellPadding = "p-2.5 sm:p-3";
  const composerShell = `relative isolate bg-surface-1/35 backdrop-blur-md border ${borderHighlight} transition-all duration-300`;
  const textareaClass =
    "min-h-[52px] rounded-[1rem] bg-transparent px-3 py-2 text-[14px] leading-6";
  const pillClass =
    "theme-pill !rounded-[0.5rem] h-8 border-primary/15 bg-primary/5 px-2.5 text-[10px] font-semibold tracking-wide";
  return (
    <div className="border-glass-border/60 sticky bottom-0 z-20 w-full border-t bg-transparent px-3 pt-3 pb-0 sm:px-5">
      <div
        className={`mx-auto w-full max-w-[min(100%,74rem)] overflow-visible rounded-[1.2rem] shadow-xl transition-all ${composerShell} ${shellPadding}`}
      >
        {isStreaming && (
          <>
            <motion.div
              aria-hidden="true"
              className="pointer-events-none absolute inset-[-3px] z-0 rounded-[1.2rem] opacity-90 blur-[7px]"
              style={{
                background:
                  "conic-gradient(from 0deg, rgba(34,211,238,.05), rgba(45,212,191,.9), rgba(168,85,247,.7), rgba(59,130,246,.8), rgba(34,211,238,.05))",
              }}
              animate={{ rotate: 360 }}
              transition={{ duration: 4.5, repeat: Infinity, ease: "linear" }}
            />
            <motion.div
              aria-hidden="true"
              className="pointer-events-none absolute -inset-px z-0 rounded-[1.2rem] border border-cyan-300/70"
              animate={{
                opacity: [0.25, 0.9, 0.25],
                boxShadow: [
                  "0 0 10px rgba(34,211,238,.15), 0 0 24px rgba(168,85,247,.08)",
                  "0 0 18px rgba(34,211,238,.55), 0 0 42px rgba(168,85,247,.25)",
                  "0 0 10px rgba(34,211,238,.15), 0 0 24px rgba(168,85,247,.08)",
                ],
              }}
              transition={{ duration: 1.8, repeat: Infinity, ease: "easeInOut" }}
            />
          </>
        )}

        <div className="relative z-10">
          {isStreaming && (
            <div className="mb-2 flex items-center gap-2 overflow-hidden rounded-lg border border-white/[0.07] bg-black/20 px-2.5 py-1.5">
              <div className="flex items-center gap-1.5" aria-label="DeepSpace is processing">
                {[0, 1, 2, 3].map((index) => (
                  <motion.span
                    key={`processing-node-${index}`}
                    className="h-1.5 w-1.5 rounded-full bg-cyan-300 shadow-[0_0_8px_rgba(103,232,249,.8)]"
                    animate={{
                      scale: [0.65, 1.35, 0.65],
                      opacity: [0.35, 1, 0.35],
                    }}
                    transition={{
                      duration: 1.1,
                      delay: index * 0.16,
                      repeat: Infinity,
                      ease: "easeInOut",
                    }}
                  />
                ))}
              </div>
              <span className="text-[9px] font-semibold tracking-[0.18em] text-cyan-100/65 uppercase">
                Processing request
              </span>
              <motion.span
                aria-hidden="true"
                className="ml-auto h-px w-16 bg-gradient-to-r from-transparent via-fuchsia-300/80 to-transparent"
                animate={{ x: [-24, 24, -24], opacity: [0.15, 0.9, 0.15] }}
                transition={{ duration: 1.7, repeat: Infinity, ease: "easeInOut" }}
              />
            </div>
          )}

          <textarea
            value={query}
            onChange={(event) => onQueryChange(event.target.value.slice(0, 4000))}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                onSubmit();
              }
            }}
            placeholder="Message DeepSpace..."
            className={`text-foreground placeholder:text-foreground/30 w-full resize-none border-none bg-transparent outline-none ${textareaClass}`}
            disabled={isStreaming}
          />

          {contextLimit && contextLimit > 0 ? (
            <div className="mt-1 flex items-center gap-2 px-2 text-[9px] text-white/40">
              <span className="shrink-0 tracking-[0.14em] uppercase">Context</span>
              <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-white/10">
                <div
                  className={`h-full rounded-full transition-all ${
                    (contextUsedTokens ?? 0) / contextLimit > 0.9
                      ? "bg-red-400"
                      : (contextUsedTokens ?? 0) / contextLimit > 0.7
                        ? "bg-amber-300"
                        : "bg-cyan-300"
                  }`}
                  style={{
                    width: `${Math.min(100, Math.max(0, ((contextUsedTokens ?? 0) / contextLimit) * 100))}%`,
                  }}
                />
              </div>
              <span className="shrink-0 tabular-nums">
                {(contextUsedTokens ?? 0).toLocaleString()} / {contextLimit.toLocaleString()}
              </span>
            </div>
          ) : null}

          <div className="border-glass-border/70 mt-2.5 flex items-center justify-between gap-3 border-t pt-2.5">
            <div className="flex min-w-0 flex-grow flex-wrap items-center gap-1.5 sm:gap-2">
              {/* Functional Model Dropdown */}
              <div ref={dropdownRef} className="relative flex-shrink-0">
                <button
                  type="button"
                  onClick={() => setModelDropdownOpen(!modelDropdownOpen)}
                  disabled={isStreaming}
                  className={`${pillClass} border-glass-border bg-surface-2 text-foreground/60 hover:text-foreground flex items-center gap-1.5 transition-all hover:bg-white/5 active:scale-95`}
                >
                  <Bot size={11} />
                  <span className="max-w-[11rem] truncate">{modelName || "Select Model"}</span>
                  <ChevronDown
                    size={11}
                    className={`transition-transform duration-200 ${modelDropdownOpen ? "rotate-180" : ""}`}
                  />
                </button>

                <AnimatePresence>
                  {modelDropdownOpen && (
                    <motion.div
                      initial={{ opacity: 0, y: 8, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 6, scale: 0.98 }}
                      transition={{ duration: 0.16, ease: "easeOut" }}
                      className="border-glass-border bg-surface-0/95 absolute bottom-full left-0 z-50 mb-2 max-h-60 min-w-[200px] overflow-y-auto rounded-xl border p-1 shadow-2xl backdrop-blur-xl"
                    >
                      {availableModels && availableModels.length > 0 ? (
                        availableModels.map((m) => {
                          const selected = m.modelName === modelName;
                          return (
                            <button
                              key={`${m.providerId}-${m.modelName}`}
                              type="button"
                              onClick={() => {
                                onModelSelect?.(m.providerId, m.modelName);
                                setModelDropdownOpen(false);
                              }}
                              className={`flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-xs transition-all ${
                                selected
                                  ? "bg-primary/15 text-primary font-medium"
                                  : "text-foreground/80 hover:bg-foreground/[0.04]"
                              }`}
                            >
                              <span className="truncate">{m.displayName}</span>
                              {selected && (
                                <Check size={11} className="text-primary ml-2 flex-shrink-0" />
                              )}
                            </button>
                          );
                        })
                      ) : (
                        <div className="text-foreground/40 px-2.5 py-2 text-xs italic">
                          No models found
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Direct Voice Integration Controls */}
              <div className="relative flex h-8 items-center rounded-lg border border-white/10 bg-black/40 p-0.5 backdrop-blur-md">
                {/* Voice Dictation (STT Mode) Button */}
                <div className="group relative">
                  <button
                    type="button"
                    onClick={onSttToggle}
                    className={`relative z-10 flex h-7 w-7 items-center justify-center rounded-[0.35rem] transition-all duration-200 ${
                      sttActive
                        ? "border border-emerald-500/35 bg-emerald-500/25 text-emerald-400 shadow-[0_2px_8px_rgba(16,185,129,0.3)]"
                        : "border border-transparent text-white/40 hover:text-white/80"
                    }`}
                    aria-label="Voice Dictation (STT)"
                  >
                    {sttActive ? (
                      <Mic
                        size={13}
                        className={voiceState === "listening" ? "animate-pulse" : ""}
                      />
                    ) : (
                      <MicOff size={13} />
                    )}
                  </button>
                  <div className="pointer-events-none absolute bottom-full left-1/2 z-[60] mb-2 -translate-x-1/2 opacity-0 transition-all group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                    <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider whitespace-nowrap text-white uppercase shadow-xl backdrop-blur-sm">
                      Voice Dictation (STT)
                    </div>
                  </div>
                </div>

                {/* Jarvis Mode (Verbal Commentary) Button */}
                <div className="group relative">
                  <button
                    type="button"
                    onClick={onTtsToggle}
                    className={`relative z-10 flex h-7 w-7 items-center justify-center rounded-[0.35rem] transition-all duration-200 ${
                      ttsActive
                        ? "bg-primary/20 text-primary border-primary/35 border shadow-[0_2px_8px_rgba(var(--primary),0.3)]"
                        : "border border-transparent text-white/40 hover:text-white/80"
                    }`}
                    aria-label="Jarvis Mode"
                  >
                    {ttsActive ? (
                      <Volume2
                        size={13}
                        className={voiceState === "speaking" ? "animate-bounce" : ""}
                      />
                    ) : (
                      <VolumeX size={13} />
                    )}
                  </button>
                  <div className="pointer-events-none absolute bottom-full left-1/2 z-[60] mb-2 -translate-x-1/2 opacity-0 transition-all group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                    <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider whitespace-nowrap text-white uppercase shadow-xl backdrop-blur-sm">
                      Voice Commentary (TTS)
                    </div>
                  </div>
                </div>
              </div>

              {(sttActive || ttsActive) && voiceLabel && (
                <span className="ml-0.5 max-w-[140px] animate-pulse truncate text-[10px] font-semibold tracking-wide text-white/45">
                  {voiceLabel}
                </span>
              )}
            </div>

            <div className="flex flex-shrink-0 items-center gap-2 sm:gap-3">
              <motion.button
                type="button"
                onClick={isStreaming ? onStop : onSubmit}
                disabled={!isStreaming && !query.trim()}
                className="border-primary/40 from-primary/90 to-primary text-primary-foreground hover:border-primary/60 disabled:border-border-subtle disabled:bg-surface-2 disabled:text-muted-foreground relative flex h-10 w-10 items-center justify-center rounded-full border bg-gradient-to-br shadow-lg transition-all hover:scale-110 hover:brightness-110 active:scale-95 disabled:cursor-not-allowed disabled:shadow-none"
                whileHover={!isStreaming ? { scale: 1.08 } : {}}
                whileTap={!isStreaming ? { scale: 0.95 } : {}}
                animate={
                  isStreaming
                    ? {
                        borderColor: [
                          "rgba(var(--primary),0.4)",
                          "rgba(var(--primary),0.9)",
                          "rgba(var(--primary),0.4)",
                        ],
                        boxShadow: [
                          "0_0_12px_rgba(var(--primary),0.2)",
                          "0_0_24px_rgba(var(--primary),0.5),0_0_40px_rgba(var(--primary),0.3)",
                          "0_0_12px_rgba(var(--primary),0.2)",
                        ],
                      }
                    : {}
                }
                transition={
                  isStreaming
                    ? {
                        duration: 1.8,
                        repeat: Infinity,
                        ease: "easeInOut",
                      }
                    : {}
                }
              >
                {isStreaming ? <StreamingIcon /> : <SendIcon />}

                {isStreaming && (
                  <>
                    <motion.span
                      className="border-primary/30 pointer-events-none absolute inset-[-6px] rounded-full border-2"
                      animate={{ scale: [1, 1.15, 1], opacity: [0.3, 0.6, 0.3] }}
                      transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
                    />
                    <motion.span
                      className="border-primary/15 pointer-events-none absolute inset-[-12px] rounded-full border"
                      animate={{ scale: [1, 1.25, 1], opacity: [0.1, 0.3, 0.1] }}
                      transition={{ duration: 2, repeat: Infinity, ease: "easeInOut", delay: 0.2 }}
                    />
                  </>
                )}
              </motion.button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
