"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Bot, ChevronDown, Check, Sparkles, MessageSquare, Mic, MicOff, Volume2, VolumeX } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import ExecutionModeDropdown from "./ExecutionModeDropdown";
import RuntimePreferencesDropdown, {
  type RuntimePreferencesValue,
} from "./RuntimePreferencesDropdown";

interface DeepSpaceComposerProps {
  query: string;
  isStreaming: boolean;
  variant?: "default" | "deepspace";
  onQueryChange: (value: string) => void;
  onSubmit: () => void;
  onStop: () => void;
  usedTokens?: number;
  totalContext?: number | null;
  modelName?: string | null;
  isAgentic?: boolean;
  onAgenticChange?: (val: boolean) => void;
  availableModels?: Array<{ providerId: string; modelName: string; displayName: string }>;
  onModelSelect?: (providerId: string, modelName: string) => void;
  executionMode?: "auto_review" | "full_access";
  onExecutionModeChange?: (mode: "auto_review" | "full_access") => void;
  runtimePreferences?: RuntimePreferencesValue;
  isSavingRuntimePreferences?: boolean;
  activeConversationId?: string | null;
  onRuntimePreferencesChange?: (changes: Partial<RuntimePreferencesValue>) => void;
  fullAutonomyEnabled?: boolean;
  onFullAutonomyChange?: (enabled: boolean) => void;
  voiceState?: "idle" | "listening" | "thinking" | "speaking";
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

function TokenIndicator({ used, total }: { used: number; total: number | null }) {
  const hasKnownTotal = typeof total === "number" && total > 0;
  const percentage = hasKnownTotal ? Math.min(100, Math.max(0, (used / total) * 100)) : 0;
  const remaining = hasKnownTotal ? Math.max((total as number) - used, 0) : null;
  const isWarning = percentage > 80;
  const isCritical = percentage > 95;

  return (
    <div className="group relative flex items-center">
      <div className="relative h-7 w-7 transition-transform group-hover:scale-110">
        <svg className="h-full w-full -rotate-90 transform" viewBox="0 0 32 32">
          <circle
            cx="16"
            cy="16"
            r="14"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            className="text-foreground/5"
          />
          <motion.circle
            cx="16"
            cy="16"
            r="14"
            fill="none"
            stroke="currentColor"
            strokeWidth="3"
            strokeDasharray={88}
            initial={{ strokeDashoffset: 88 }}
            animate={{ strokeDashoffset: 88 - (88 * percentage) / 100 }}
            transition={{ duration: 1, ease: "easeOut" }}
            className={`${
              isCritical ? "text-danger" : isWarning ? "text-warning" : "text-primary/60"
            }`}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span
            className={`text-[10px] font-bold ${isCritical ? "text-danger" : "text-foreground/40"}`}
          >
            {hasKnownTotal ? `${Math.round(percentage)}%` : "—"}
          </span>
        </div>
      </div>

      {/* Tooltip */}
      <div className="pointer-events-none absolute right-full bottom-0 z-50 mr-3 mb-0 opacity-0 transition-all group-hover:pointer-events-auto group-hover:mb-1 group-hover:opacity-100">
        <div className="theme-panel border-glass-border bg-surface-0/95 min-w-[220px] border p-4 shadow-2xl backdrop-blur-xl rounded-2xl">
          <div className="border-glass-border/40 mb-2 flex items-center justify-between border-b pb-2">
            <span className="text-foreground/40 text-[10px] font-bold tracking-wider uppercase">
              Context Usage
            </span>
            <span
              className={`text-[10px] font-bold ${isCritical ? "text-danger" : "text-primary"}`}
            >
              {hasKnownTotal ? `${Math.round(percentage)}%` : "unknown"}
            </span>
          </div>
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between gap-4">
              <span className="text-foreground/50">Used</span>
              <span className="text-foreground font-mono font-medium">{used.toLocaleString()}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span className="text-foreground/50">Available</span>
              <span className="text-foreground font-mono font-medium">
                {typeof remaining === "number" ? remaining.toLocaleString() : "unknown"}
              </span>
            </div>
            <div className="border-glass-border/20 flex justify-between gap-4 border-t pt-1.5">
              <span className="text-foreground/50 font-semibold">Limit</span>
              <span className="text-foreground/80 font-mono font-bold">
                {hasKnownTotal ? total.toLocaleString() : "unknown"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function DeepSpaceComposer({
  query,
  isStreaming,
  variant = "default",
  onQueryChange,
  onSubmit,
  onStop,
  usedTokens = 0,
  totalContext = null,
  modelName,
  isAgentic = true,
  onAgenticChange,
  availableModels = [],
  onModelSelect,
  executionMode = "auto_review",
  onExecutionModeChange,
  runtimePreferences = {
    planner_mode: "default",
    subagent_profile: "default",
    runtime_hooks_enabled: true,
    workspace_mode_enabled: true,
    full_autonomy_enabled: false,
  },
  isSavingRuntimePreferences = false,
  activeConversationId = null,
  onRuntimePreferencesChange,
  fullAutonomyEnabled = false,
  onFullAutonomyChange,
  voiceState = "idle",
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

  const borderHighlight = isAgentic
    ? "border-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.18)]"
    : "border-amber-500/40 shadow-[0_0_15px_rgba(245,158,11,0.12)]";

  const shellPadding = "p-2.5 sm:p-3";
  const composerShell = `bg-surface-1/35 backdrop-blur-md border ${borderHighlight} transition-all duration-300`;
  const textareaClass = "min-h-[52px] rounded-[1rem] bg-transparent px-3 py-2 text-[14px] leading-6";
  const pillClass = "theme-pill !rounded-[0.5rem] h-8 border-primary/15 bg-primary/5 px-2.5 text-[10px] font-semibold tracking-wide";
  return (
    <div className="border-glass-border/60 sticky bottom-0 z-20 w-full border-t bg-transparent px-3 pt-3 pb-0 sm:px-5">
      <div
        className={`mx-auto w-full max-w-[min(100%,74rem)] overflow-visible rounded-[1.2rem] shadow-xl transition-all ${composerShell} ${shellPadding}`}
      >
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

        <div className="border-glass-border/70 mt-2.5 flex items-center justify-between gap-3 border-t pt-2.5">
          <div className="flex min-w-0 flex-grow flex-wrap items-center gap-1.5 sm:gap-2">
            <button
              type="button"
              aria-pressed={fullAutonomyEnabled}
              aria-label="Full Autonomy"
              onClick={() => onFullAutonomyChange?.(!fullAutonomyEnabled)}
              className={`inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-[10px] font-bold tracking-wide transition ${
                fullAutonomyEnabled
                  ? "border-emerald-400/50 bg-emerald-400/15 text-emerald-300"
                  : "border-white/10 bg-black/20 text-white/55 hover:text-white/85"
              }`}
              title="Automatically continue checkpointed missions until verified, stopped, cancelled, or approval is required."
            >
              <Sparkles size={12} />
              Full Autonomy
            </button>
            {/* Premium Mode Selector (Toggle Section with Icons & Tooltips) */}
            <div className="relative flex h-8 items-center rounded-lg border border-white/10 bg-black/40 p-0.5 backdrop-blur-md">
              <div className="group relative">
                <button
                  type="button"
                  onClick={() => onAgenticChange?.(false)}
                  className={`relative z-10 flex h-7 w-7 items-center justify-center rounded-[0.35rem] transition-all duration-200 ${
                    !isAgentic
                      ? "bg-white/10 text-white shadow-[0_2px_8px_rgba(0,0,0,0.3)]"
                      : "text-white/40 hover:text-white/80"
                  }`}
                  aria-label="Normal Chat Mode"
                >
                  <MessageSquare size={13} />
                </button>
                <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 -translate-x-1/2 opacity-0 transition-all group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                  <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider text-white uppercase shadow-xl backdrop-blur-sm whitespace-nowrap">
                    Normal Chat
                  </div>
                </div>
              </div>
              <div className="group relative">
                <button
                  type="button"
                  onClick={() => onAgenticChange?.(true)}
                  className={`relative z-10 flex h-7 w-7 items-center justify-center rounded-[0.35rem] transition-all duration-200 ${
                    isAgentic
                      ? "bg-primary/20 text-primary border-primary/30 border shadow-[0_2px_8px_rgba(var(--primary),0.2)]"
                      : "border border-transparent text-white/40 hover:text-white/80"
                  }`}
                  aria-label="Agentic Work Mode"
                >
                  <Sparkles size={13} className={isAgentic ? "animate-pulse" : ""} />
                </button>
                <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 -translate-x-1/2 opacity-0 transition-all group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
                  <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider text-white uppercase shadow-xl backdrop-blur-sm whitespace-nowrap">
                    Agentic Work
                  </div>
                </div>
              </div>
            </div>

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

            {/* Integrated Execution Mode Dropdown */}
            <ExecutionModeDropdown
              value={executionMode}
              onChange={onExecutionModeChange || (() => {})}
              compact
              className={`${pillClass} border-glass-border bg-surface-2 flex items-center gap-1.5 transition-all hover:bg-white/5 active:scale-95`}
            />

            {/* Integrated Runtime Preferences Dropdown */}
            <RuntimePreferencesDropdown
              value={runtimePreferences}
              saving={isSavingRuntimePreferences}
              conversationScoped={Boolean(activeConversationId)}
              onChange={onRuntimePreferencesChange || (() => {})}
              className={`${pillClass} border-glass-border bg-surface-2 flex items-center gap-1.5 transition-all hover:bg-white/5 active:scale-95`}
            />

            {/* Direct Voice Integration Controls */}
            <div className="relative flex h-8 items-center rounded-lg border border-white/10 bg-black/40 p-0.5 backdrop-blur-md">
              {/* Voice Dictation (STT Mode) Button */}
              <div className="group relative">
                <button
                  type="button"
                  onClick={onSttToggle}
                  className={`relative z-10 flex h-7 w-7 items-center justify-center rounded-[0.35rem] transition-all duration-200 ${
                    sttActive
                      ? "bg-emerald-500/25 text-emerald-400 border-emerald-500/35 border shadow-[0_2px_8px_rgba(16,185,129,0.3)]"
                      : "border border-transparent text-white/40 hover:text-white/80"
                  }`}
                  aria-label="Voice Dictation (STT)"
                >
                  {sttActive ? <Mic size={13} className={voiceState === "listening" ? "animate-pulse" : ""} /> : <MicOff size={13} />}
                </button>
                <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 -translate-x-1/2 opacity-0 transition-all group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100 z-[60]">
                  <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider text-white uppercase shadow-xl backdrop-blur-sm whitespace-nowrap">
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
                  {ttsActive ? <Volume2 size={13} className={voiceState === "speaking" ? "animate-bounce" : ""} /> : <VolumeX size={13} />}
                </button>
                <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 -translate-x-1/2 opacity-0 transition-all group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100 z-[60]">
                  <div className="rounded-md border border-white/10 bg-black/85 px-2 py-1 text-[9px] font-bold tracking-wider text-white uppercase shadow-xl backdrop-blur-sm whitespace-nowrap">
                    Voice Commentary (TTS)
                  </div>
                </div>
              </div>
            </div>

            {(sttActive || ttsActive) && voiceLabel && (
              <span className="text-[10px] text-white/45 animate-pulse truncate max-w-[140px] font-semibold tracking-wide ml-0.5">
                {voiceLabel}
              </span>
            )}
          </div>

          <div className="flex flex-shrink-0 items-center gap-2 sm:gap-3">
            <TokenIndicator used={usedTokens} total={totalContext} />

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
  );
}
