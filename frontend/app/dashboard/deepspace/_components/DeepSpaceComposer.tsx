"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Bot,
  ChevronDown,
  Check,
  CircleHelp,
  Gauge,
  Mic,
  MicOff,
  Play,
  Square,
  Volume2,
  VolumeX,
} from "lucide-react";
import { useEffect, useRef, useState, type CSSProperties } from "react";

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
    quantization?: string | null;
    contextWindow?: number | null;
    contextWindowSource?: string | null;
  }>;
  onModelSelect?: (providerId: string, modelName: string) => void;
  voiceState?: "idle" | "listening" | "thinking" | "speaking";
  contextUsedTokens?: number | null;
  contextLimit?: number | null;
  contextUsageSource?: string | null;
  contextRemainingTokens?: number | null;
  safeRemainingTokens?: number | null;
  sessionInputTokens?: number | null;
  sessionOutputTokens?: number | null;
  sessionTotalTokens?: number | null;
  reservedOutputTokens?: number | null;
  maxOutputTokens?: number | null;
  contextStatus?: string | null;
  contextCompacted?: boolean;
  sttActive?: boolean;
  ttsActive?: boolean;
  onSttToggle?: () => void;
  onTtsToggle?: () => void;
  voiceLabel?: string;
  runtimePhase?: DeepSpaceRuntimePhase;
  activeToolName?: string | null;
  streamActivity?: number;
  hasRuntimeError?: boolean;
}

export type DeepSpaceRuntimePhase =
  | "idle"
  | "typing"
  | "submitting"
  | "thinking"
  | "tool_calling"
  | "receiving"
  | "completed"
  | "error";

function SendIcon() {
  return <Play className="h-[18px] w-[18px] translate-x-px fill-current" strokeWidth={2.5} />;
}

function StopIcon() {
  return <Square className="h-4 w-4 fill-current" strokeWidth={2.5} />;
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
  contextUsageSource = null,
  contextRemainingTokens = null,
  safeRemainingTokens = null,
  sessionInputTokens = null,
  sessionOutputTokens = null,
  sessionTotalTokens = null,
  reservedOutputTokens = null,
  maxOutputTokens = null,
  contextStatus = null,
  contextCompacted = false,
  sttActive = false,
  ttsActive = false,
  onSttToggle,
  onTtsToggle,
  voiceLabel = "",
  runtimePhase = "idle",
  activeToolName = null,
  streamActivity = 0,
  hasRuntimeError = false,
}: DeepSpaceComposerProps) {
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [runtimeLegendOpen, setRuntimeLegendOpen] = useState(false);
  const [contextDialogOpen, setContextDialogOpen] = useState(false);
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

  const visualPhase: DeepSpaceRuntimePhase = hasRuntimeError
    ? "error"
    : runtimePhase === "idle" && query.trim()
      ? "typing"
      : runtimePhase;
  const toolKind = /search|web|searx|browse/i.test(activeToolName ?? "")
    ? "web"
    : /note[_-]?read|read|fetch|load|inspect/i.test(activeToolName ?? "")
      ? "read"
      : /note[_-]?write|write|insert|update|append/i.test(activeToolName ?? "")
        ? "write"
        : "default";
  const contextRatio =
    contextLimit && contextLimit > 0
      ? Math.min(1, Math.max(0, (contextUsedTokens ?? 0) / contextLimit))
      : 0;
  const hasContextLimit = Boolean(contextLimit && contextLimit > 0);
  const runtimeStyle = {
    "--deepspace-context-ratio": contextRatio,
    "--deepspace-context-hue": Math.round(155 - contextRatio * 155),
    "--deepspace-stream-activity": streamActivity,
    "--deepspace-receive-duration": `${1.05 + (Math.abs(streamActivity) % 7) * 0.04}s`,
  } as CSSProperties;

  const borderHighlight = "border-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.18)]";

  const shellPadding = "p-2.5 sm:p-3";
  const composerShell = `bg-surface-1/35 backdrop-blur-md border transition-all duration-300 ${
    visualPhase === "idle" || visualPhase === "typing"
      ? borderHighlight
      : visualPhase === "error"
        ? "border-red-400/55 shadow-[0_0_24px_rgba(248,113,113,0.16)]"
        : "border-transparent shadow-[0_0_24px_rgba(34,211,238,0.12)]"
  }`;
  const textareaClass =
    "min-h-[52px] rounded-[1rem] bg-transparent px-3 py-2 text-[14px] leading-6";
  const pillClass =
    "theme-pill !rounded-[0.5rem] h-8 border-primary/15 bg-primary/5 px-2.5 text-[10px] font-semibold tracking-wide";
  return (
    <div className="border-glass-border/60 sticky bottom-0 z-20 w-full border-t bg-transparent px-3 pt-3 pb-0 sm:px-5">
      <div
        className="deepspace-composer-runtime relative mx-auto w-full max-w-[min(100%,74rem)] overflow-visible"
        data-runtime-phase={visualPhase}
        data-runtime-tool={toolKind}
        style={runtimeStyle}
      >
        <div
          aria-hidden="true"
          className="deepspace-composer-border-trace pointer-events-none absolute inset-0 z-20 overflow-hidden rounded-[1.2rem]"
          style={
            {
              padding: "1.5px",
              WebkitMask: "linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0)",
              WebkitMaskComposite: "xor",
              maskComposite: "exclude",
            } as CSSProperties
          }
        >
          <div
            aria-hidden="true"
            className="deepspace-composer-border-gradient absolute -inset-[200%]"
          />
          {visualPhase === "tool_calling" && (
            <div className="absolute inset-0" aria-hidden="true">
              {["#38bdf8", "#a78bfa", "#34d399"].map((color, index) => (
                <span
                  key={color}
                  className="deepspace-composer-tool-trace absolute inset-0"
                  style={
                    {
                      "--deepspace-trace-color": color,
                      animationDelay: `${index * -0.42}s`,
                    } as CSSProperties
                  }
                />
              ))}
            </div>
          )}
          {visualPhase === "tool_calling" && toolKind === "web" && (
            <div className="deepspace-composer-search-particles" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          )}
        </div>

        <div
          className={`relative rounded-[1.2rem] shadow-xl ${modelDropdownOpen ? "z-[60]" : "z-10"} ${composerShell} ${shellPadding}`}
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

          <div className="relative mt-1 flex items-center gap-2 px-2 text-[9px] text-white/40">
            <button
              type="button"
              onClick={() => setContextDialogOpen((open) => !open)}
              className="flex shrink-0 items-center gap-1 tracking-[0.14em] uppercase transition-colors hover:text-cyan-200"
              aria-expanded={contextDialogOpen}
              aria-label="Show context usage details"
            >
              <Gauge size={11} />
              Context{contextUsageSource === "estimated_local" ? " (est.)" : ""}
            </button>
            <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-white/10">
              <div
                className={`h-full rounded-full transition-all ${
                  hasContextLimit && (contextUsedTokens ?? 0) / (contextLimit ?? 1) > 0.9
                    ? "bg-red-400"
                    : hasContextLimit && (contextUsedTokens ?? 0) / (contextLimit ?? 1) > 0.7
                      ? "bg-amber-300"
                      : "bg-cyan-300"
                }`}
                style={{
                  width: hasContextLimit
                    ? `${Math.min(100, Math.max(0, ((contextUsedTokens ?? 0) / (contextLimit ?? 1)) * 100))}%`
                    : "0%",
                }}
              />
            </div>
            <span className="shrink-0 tabular-nums">
              {(contextUsedTokens ?? 0).toLocaleString()} /{" "}
              {hasContextLimit ? contextLimit?.toLocaleString() : "—"} ·{" "}
              {hasContextLimit ? `${Math.round(contextRatio * 100)}%` : "—"}
            </span>
            <AnimatePresence>
              {contextDialogOpen && (
                <motion.div
                  initial={{ opacity: 0, y: 5, scale: 0.98 }}
                  animate={{ opacity: 1, y: 0, scale: 1 }}
                  exit={{ opacity: 0, y: 3, scale: 0.98 }}
                  role="dialog"
                  aria-label="Context usage details"
                  className="border-glass-border bg-surface-0/95 absolute right-0 bottom-full z-[75] mb-2 w-[min(23rem,calc(100vw-2rem))] rounded-xl border p-3 text-[10px] leading-4 text-white/65 shadow-2xl backdrop-blur-xl"
                >
                  <div className="mb-2 flex items-center justify-between text-[11px] font-semibold text-white/90">
                    <span>Context budget</span>
                    <button
                      type="button"
                      onClick={() => setContextDialogOpen(false)}
                      className="text-white/40 hover:text-white/80"
                      aria-label="Close context details"
                    >
                      ×
                    </button>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-2">
                      <span className="block text-white/40">Active context</span>
                      <strong className="text-white/90">
                        {(contextUsedTokens ?? 0).toLocaleString()} /{" "}
                        {hasContextLimit ? contextLimit?.toLocaleString() : "Unavailable"}
                      </strong>
                      <span className="ml-1 text-cyan-200">
                        ({Math.round(contextRatio * 100)}%)
                      </span>
                    </div>
                    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-2">
                      <span className="block text-white/40">Safe remaining</span>
                      <strong className="text-white/90">
                        {(safeRemainingTokens ?? contextRemainingTokens ?? 0).toLocaleString()}
                      </strong>
                    </div>
                    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-2">
                      <span className="block text-white/40">Session processed</span>
                      <strong className="text-white/90">
                        {(sessionTotalTokens ?? 0).toLocaleString()}
                      </strong>
                    </div>
                    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-2">
                      <span className="block text-white/40">Output reserve</span>
                      <strong className="text-white/90">
                        {(reservedOutputTokens ?? maxOutputTokens ?? 0).toLocaleString()}
                      </strong>
                    </div>
                  </div>
                  <p className="mt-2 border-t border-white/10 pt-2 text-white/45">
                    Active context is the exact serialized request estimate for the selected model.
                    Session processed is cumulative across rounds; it does not reset when you switch
                    models.
                  </p>
                  <div className="mt-2 flex items-center justify-between text-white/45">
                    <span>
                      Status: <span className="text-white/75">{contextStatus ?? "unknown"}</span>
                    </span>
                    {contextCompacted ? <span className="text-emerald-300">Compacted</span> : null}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
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
                  {isStreaming ? (
                    <motion.span
                      aria-hidden="true"
                      className="inline-flex text-cyan-300"
                      animate={{
                        rotate: [0, -8, 8, -4, 0],
                        scale: [1, 1.12, 1],
                        filter: [
                          "drop-shadow(0 0 0 rgba(103,232,249,0))",
                          "drop-shadow(0 0 5px rgba(103,232,249,.9))",
                          "drop-shadow(0 0 0 rgba(103,232,249,0))",
                        ],
                      }}
                      transition={{ duration: 1.4, repeat: Infinity, ease: "easeInOut" }}
                    >
                      <Bot size={11} />
                    </motion.span>
                  ) : (
                    <Bot size={11} />
                  )}
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
                              <span className="flex min-w-0 items-center gap-1.5 truncate">
                                <span className="truncate">{m.displayName}</span>
                                {m.quantization && (
                                  <span className="text-primary/70 shrink-0 text-[9px] font-semibold tracking-wide uppercase">
                                    {m.quantization}
                                  </span>
                                )}
                              </span>
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

            <div className="relative flex-shrink-0">
              <button
                type="button"
                onClick={() => setRuntimeLegendOpen((open) => !open)}
                aria-label="Show DeepSpace status legend"
                aria-expanded={runtimeLegendOpen}
                title="DeepSpace status legend"
                className={`flex h-8 w-8 items-center justify-center rounded-lg border transition-all duration-200 ${
                  runtimeLegendOpen
                    ? "border-cyan-400/45 bg-cyan-400/15 text-cyan-200"
                    : "border-white/10 bg-black/30 text-white/45 hover:border-cyan-400/30 hover:text-cyan-200"
                }`}
              >
                <CircleHelp size={14} />
              </button>
              <AnimatePresence>
                {runtimeLegendOpen && (
                  <motion.div
                    initial={{ opacity: 0, y: 6, scale: 0.98 }}
                    animate={{ opacity: 1, y: 0, scale: 1 }}
                    exit={{ opacity: 0, y: 4, scale: 0.98 }}
                    transition={{ duration: 0.14, ease: "easeOut" }}
                    role="dialog"
                    aria-label="DeepSpace status legend"
                    className="border-glass-border bg-surface-0/95 absolute right-0 bottom-full z-[70] mb-2 w-[min(19rem,calc(100vw-2rem))] rounded-xl border p-3 text-[10px] leading-4 text-white/65 shadow-2xl backdrop-blur-xl"
                  >
                    <div className="mb-2 flex items-center justify-between gap-3 text-[11px] font-semibold tracking-wide text-white/90">
                      <span>DeepSpace status</span>
                      <button
                        type="button"
                        onClick={() => setRuntimeLegendOpen(false)}
                        className="rounded px-1 text-white/35 hover:text-white/80"
                        aria-label="Close status legend"
                      >
                        ×
                      </button>
                    </div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">
                      {[
                        ["bg-emerald-400", "Ready / typing"],
                        ["bg-amber-300", "Submitting"],
                        ["bg-cyan-300", "Thinking / receiving"],
                        ["bg-blue-400", "Web/search tool"],
                        ["bg-emerald-300", "Reading data"],
                        ["bg-fuchsia-300", "Writing data"],
                        ["bg-white", "Completed"],
                        ["bg-red-400", "Error"],
                      ].map(([color, label]) => (
                        <span key={label} className="flex items-center gap-1.5">
                          <span
                            className={`h-1.5 w-1.5 rounded-full ${color}`}
                            aria-hidden="true"
                          />
                          {label}
                        </span>
                      ))}
                    </div>
                    <p className="mt-2 border-t border-white/10 pt-2 text-white/45">
                      The square button stops a running response; the play button sends your
                      message. Context glow shifts from cyan to amber/red as the model window fills.
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <div className="flex flex-shrink-0 items-center gap-2 sm:gap-3">
              <motion.button
                type="button"
                onClick={isStreaming ? onStop : onSubmit}
                disabled={!isStreaming && !query.trim()}
                aria-label={isStreaming ? "Stop response" : "Send message"}
                title={isStreaming ? "Stop response" : "Send message"}
                className="border-primary/45 from-primary/95 to-primary text-primary-foreground hover:border-primary/70 disabled:border-border-subtle disabled:bg-surface-2 disabled:text-muted-foreground relative flex h-10 w-10 items-center justify-center rounded-xl border bg-gradient-to-br shadow-[0_8px_20px_rgba(var(--primary),0.25)] transition-[border-color,background-color,box-shadow,filter] hover:brightness-110 active:brightness-95 disabled:cursor-not-allowed disabled:shadow-none"
                whileHover={{ scale: isStreaming ? 1.03 : 1.06 }}
                whileTap={{ scale: 0.94 }}
                animate={
                  isStreaming
                    ? {
                        scale: [1, 1.025, 1],
                        boxShadow: [
                          "0 8px 20px rgba(var(--primary),0.25)",
                          "0 10px 28px rgba(var(--primary),0.48)",
                          "0 8px 20px rgba(var(--primary),0.25)",
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
                <AnimatePresence initial={false} mode="wait">
                  <motion.span
                    key={isStreaming ? "stop" : "send"}
                    initial={{ opacity: 0, scale: 0.65, rotate: isStreaming ? -18 : 18 }}
                    animate={{ opacity: 1, scale: 1, rotate: 0 }}
                    exit={{ opacity: 0, scale: 0.65, rotate: isStreaming ? 18 : -18 }}
                    transition={{ duration: 0.16, ease: "easeOut" }}
                    className="relative z-10 flex items-center justify-center"
                  >
                    {isStreaming ? <StopIcon /> : <SendIcon />}
                  </motion.span>
                </AnimatePresence>

                {isStreaming && (
                  <motion.span
                    className="border-primary/30 pointer-events-none absolute inset-[-4px] rounded-[14px] border"
                    animate={{ opacity: [0.2, 0.65, 0.2], scale: [1, 1.06, 1] }}
                    transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
                  />
                )}
              </motion.button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
