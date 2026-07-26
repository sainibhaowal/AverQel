"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Bot, Check, ChevronDown, Equal, Settings2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface QueryComposerProps {
  mode?: "query" | "deepspace";
  query: string;
  searchMode: "hybrid" | "semantic" | "keyword";
  selectedCollectionId: string;
  collectionOptions: Array<{ id: string; name: string }>;
  collectionScopeLoading: boolean;
  isStreaming: boolean;
  filtersOpen: boolean;
  supportsThinking: boolean;
  thinkingEnabled: boolean;
  onQueryChange: (value: string) => void;
  onSearchModeChange: (value: "hybrid" | "semantic" | "keyword") => void;
  onCollectionChange: (value: string) => void;
  onToggleFilters: () => void;
  onThinkingChange: (value: boolean) => void;
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
  contextUsedTokens?: number | null;
  contextLimit?: number | null;
}

// Idle button icon - minimalist arrow send
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
  const remaining = hasKnownTotal ? Math.max(total - used, 0) : null;
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
            className={`text-[8px] font-bold ${isCritical ? "text-danger" : "text-foreground/40"}`}
          >
            {hasKnownTotal ? `${Math.round(percentage)}%` : "—"}
          </span>
        </div>
      </div>

      {/* Tooltip - positioned relative to right edge of container to prevent clipping */}
      <div className="pointer-events-none absolute bottom-full right-0 mb-3 opacity-0 transition-all group-hover:pointer-events-auto group-hover:mb-4 group-hover:opacity-100">
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
          {isCritical && (
            <div className="text-danger/80 mt-2 text-[9px] leading-tight italic">
              Approaching limit. Older context may be truncated.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function QueryComposer({
  mode = "query",
  query,
  searchMode,
  selectedCollectionId,
  collectionOptions,
  collectionScopeLoading,
  isStreaming,
  filtersOpen,
  supportsThinking,
  thinkingEnabled,
  onQueryChange,
  onSearchModeChange,
  onCollectionChange,
  onToggleFilters,
  onThinkingChange,
  onSubmit,
  onStop,
  modelName,
  availableModels = [],
  onModelSelect,
  contextUsedTokens = null,
  contextLimit = null,
}: QueryComposerProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const scopeMenuRef = useRef<HTMLDivElement | null>(null);
  const [scopeMenuOpen, setScopeMenuOpen] = useState(false);
  const selectedCollectionName =
    collectionOptions.find((collection) => collection.id === selectedCollectionId)?.name ??
    "All accessible documents";
  const isDeepSpace = mode === "deepspace";

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

  return (
    <div className="border-glass-border/60 sticky bottom-0 z-20 border-t bg-transparent px-2 pt-3 pb-0 sm:px-5">
      <div className="mx-auto w-full max-w-5xl overflow-visible rounded-2xl border border-primary/30 bg-surface-1/35 backdrop-blur-md p-2.5 shadow-lg sm:p-3 transition-all duration-300">
        <textarea
          ref={textareaRef}
          value={query}
          onChange={(event) => onQueryChange(event.target.value.slice(0, 4000))}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSubmit();
            }
          }}
          placeholder="What would you like to investigate today?"
          className="text-foreground placeholder:text-foreground/30 min-h-[60px] w-full resize-none border-none bg-transparent px-2.5 py-2 text-[15px] leading-relaxed outline-none sm:px-3"
          disabled={isStreaming}
        />

        {contextLimit && contextLimit > 0 ? (
          <div className="mt-1 flex items-center gap-2 px-2 text-[9px] text-white/40">
            <span className="shrink-0 tracking-[0.14em] uppercase">Context</span>
            <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-white/10">
              <div
                className={`h-full rounded-full transition-[width] duration-200 ${
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

        <div className="border-glass-border mt-3 flex items-center justify-between gap-3 border-t pt-3">
          <div className="flex min-w-0 flex-grow flex-wrap items-center gap-1.5 sm:gap-2">
            {/* Functional Model Dropdown */}
            <div ref={dropdownRef} className="relative flex-shrink-0">
              <button
                type="button"
                onClick={() => setModelDropdownOpen(!modelDropdownOpen)}
                disabled={isStreaming}
                className="theme-pill !rounded-lg hover:text-foreground flex items-center gap-1.5 transition-all hover:bg-white/5 active:scale-95 cursor-pointer"
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

            {!isDeepSpace ? (
              <>
                <span className="theme-pill !rounded-lg !bg-foreground/5 !border-foreground/10 !text-foreground/60 flex-shrink-0 italic">
                  <span title="AVERQEL adjusts retrieval depth automatically based on the request.">
                    Retrieval Depth
                  </span>
                  <span className="sr-only">
                    AVERQEL adjusts retrieval depth automatically based on the request.
                  </span>
                </span>
                <span className="theme-pill !rounded-lg !bg-foreground/5 !border-foreground/10 !text-foreground/60 flex-shrink-0 capitalize">
                  {searchMode}
                </span>
                {supportsThinking ? (
                  <button
                    type="button"
                    onClick={() => onThinkingChange(!thinkingEnabled)}
                    disabled={isStreaming}
                    className={`theme-pill !rounded-lg flex-shrink-0 transition-all ${
                      thinkingEnabled
                        ? "!border-primary/30 !bg-primary/10 !text-primary shadow-sm"
                        : "!bg-foreground/5 !border-foreground/10 !text-foreground/60"
                    }`}
                  >
                    <span>Think {thinkingEnabled ? "On" : "Off"}</span>
                  </button>
                ) : null}
              </>
            ) : (
              <>
                {supportsThinking ? (
                  <button
                    type="button"
                    onClick={() => onThinkingChange(!thinkingEnabled)}
                    disabled={isStreaming}
                    className={`theme-pill !rounded-lg flex-shrink-0 transition-all ${
                      thinkingEnabled
                        ? "!border-primary/30 !bg-primary/10 !text-primary shadow-sm"
                        : "!bg-foreground/5 !border-foreground/10 !text-foreground/60"
                    }`}
                  >
                    <span>Think {thinkingEnabled ? "On" : "Off"}</span>
                  </button>
                ) : null}
              </>
            )}
          </div>

          <div className="flex items-center gap-4">
            <motion.button
              type="button"
              onClick={isStreaming ? onStop : onSubmit}
              disabled={!isStreaming && !query.trim()}
              className="border-primary/40 from-primary to-primary/80 text-primary-foreground disabled:bg-muted disabled:text-muted-foreground relative flex h-11 w-11 shrink-0 items-center justify-center rounded-full border bg-gradient-to-br shadow-lg transition-all hover:scale-110 hover:brightness-110 active:scale-95 disabled:cursor-not-allowed disabled:border-transparent disabled:shadow-none"
              whileHover={!isStreaming ? { scale: 1.1 } : {}}
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
                  {/* Clean Semantic Pulse */}
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
