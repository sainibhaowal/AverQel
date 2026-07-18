"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  BarChart3,
  Check,
  ChevronDown,
  Cpu,
  FileText,
  Files,
  LifeBuoy,
  Search,
  Settings2,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

export type PlannerMode = "default" | "structured";
export type SubagentProfile =
  | "default"
  | "research"
  | "analysis"
  | "writer"
  | "executor"
  | "planner"
  | "support"
  | "file";

export interface RuntimePreferencesValue {
  planner_mode: PlannerMode;
  subagent_profile: SubagentProfile;
  runtime_hooks_enabled: boolean;
  workspace_mode_enabled: boolean;
  full_autonomy_enabled?: boolean;
}

interface RuntimePreferencesDropdownProps {
  value: RuntimePreferencesValue;
  conversationScoped: boolean;
  saving?: boolean;
  onChange: (nextValue: Partial<RuntimePreferencesValue>) => void;
  className?: string;
}

const SUBAGENT_PROFILE_OPTIONS: Array<{
  value: SubagentProfile;
  label: string;
  description: string;
}> = [
  { value: "default", label: "Default", description: "Uses normal routing decisions." },
  {
    value: "research",
    label: "Research",
    description: "Biases generic delegation toward evidence gathering.",
  },
  {
    value: "analysis",
    label: "Analysis",
    description: "Biases generic delegation toward synthesis and reasoning.",
  },
  {
    value: "writer",
    label: "Writer",
    description: "Biases generic delegation toward drafting and rewriting.",
  },
  {
    value: "executor",
    label: "Executor",
    description: "Biases generic delegation toward action-oriented steps.",
  },
  {
    value: "planner",
    label: "Planner",
    description: "Biases generic delegation toward planning and decomposition.",
  },
  {
    value: "support",
    label: "Support",
    description: "Biases generic delegation toward task assistance and follow-through.",
  },
  {
    value: "file",
    label: "File",
    description: "Biases generic delegation toward file and workspace help.",
  },
];

function getProfileIcon(
  profile: SubagentProfile,
  props: { size?: number; className?: string } = {},
) {
  switch (profile) {
    case "research":
      return <Search {...props} />;
    case "analysis":
      return <BarChart3 {...props} />;
    case "writer":
      return <FileText {...props} />;
    case "executor":
      return <Cpu {...props} />;
    case "planner":
      return <Workflow {...props} />;
    case "support":
      return <LifeBuoy {...props} />;
    case "file":
      return <Files {...props} />;
    default:
      return <ShieldCheck {...props} />;
  }
}

export default function RuntimePreferencesDropdown({
  value,
  conversationScoped,
  saving = false,
  onChange,
  className,
}: RuntimePreferencesDropdownProps) {
  const [open, setOpen] = useState(false);
  const [biasOpen, setBiasOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState<{
    top: number;
    left: number;
    width: number;
    above: boolean;
  } | null>(null);

  const rootRef = useRef<HTMLDivElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const plannerLabel = useMemo(
    () => (value.planner_mode === "structured" ? "Structured" : "Default"),
    [value.planner_mode],
  );

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (rootRef.current && rootRef.current.contains(target)) return;
      if (menuRef.current && menuRef.current.contains(target)) return;
      setOpen(false);
      setBiasOpen(false);
    };
    window.addEventListener("mousedown", handlePointerDown);
    return () => window.removeEventListener("mousedown", handlePointerDown);
  }, []);

  useEffect(() => {
    if (!open) return;

    const updateMenuPosition = () => {
      const trigger = rootRef.current;
      if (!trigger) return;
      const rect = trigger.getBoundingClientRect();
      const width = Math.min(320, window.innerWidth - 16);
      const left = Math.max(8, Math.min(window.innerWidth - width - 8, rect.left));
      const estimatedHeight = 300;
      const above = rect.bottom + 8 + estimatedHeight > window.innerHeight;
      const top = above ? rect.top - 8 : rect.bottom + 8;
      setMenuPosition({ top, left, width, above });
    };

    updateMenuPosition();
    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("scroll", updateMenuPosition, true);
    return () => {
      window.removeEventListener("resize", updateMenuPosition);
      window.removeEventListener("scroll", updateMenuPosition, true);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => {
          setOpen((current) => !current);
          setBiasOpen(false);
        }}
        className={
          className ||
          "inline-flex items-center gap-1.5 rounded-lg border border-slate-300/80 bg-white/92 px-3 py-2 text-sm font-medium text-slate-700 shadow-[0_10px_24px_rgba(15,23,42,0.08)] backdrop-blur-md transition hover:text-slate-900 dark:border-white/10 dark:bg-[#2e3027]/90 dark:text-white/80 dark:shadow-[0_8px_24px_rgba(0,0,0,0.24)] dark:hover:text-white"
        }
      >
        <Settings2 size={13} className="text-emerald-600 dark:text-emerald-400" />
        <span>Runtime</span>
        <span className="hidden text-[10px] text-slate-400 sm:inline dark:text-white/35">
          ({plannerLabel})
        </span>
        <ChevronDown
          size={13}
          className={`transition-transform duration-200 ${open ? "rotate-180" : ""}`}
        />
      </button>

      {typeof document !== "undefined" && (
        createPortal(
          <AnimatePresence>
            {open && menuPosition && (
              <motion.div
                ref={menuRef}
                role="dialog"
                aria-label="DeepSpace runtime controls"
                initial={{ opacity: 0, scale: 0.95, y: menuPosition.above ? 8 : -8 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: menuPosition.above ? 8 : -8 }}
                transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
                className="fixed z-[260] overflow-hidden rounded-[20px] border border-slate-200 bg-white/95 p-4 shadow-[0_24px_50px_rgba(0,0,0,0.15)] backdrop-blur-xl transition-all duration-200 dark:border-white/10 dark:bg-[#1a1b18]/95 dark:shadow-[0_18px_40px_rgba(0,0,0,0.45)]"
                style={{
                  left: menuPosition.left,
                  width: menuPosition.width,
                  ...(menuPosition.above
                    ? { bottom: window.innerHeight - menuPosition.top, top: "auto" }
                    : { top: menuPosition.top }),
                }}
              >
                {/* Header */}
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <h3 className="text-[13px] font-bold text-slate-800 dark:text-white/90">
                      DeepSpace Runtime Settings
                    </h3>
                    <p className="mt-0.5 text-[10px] font-medium text-slate-400 dark:text-white/35">
                      {conversationScoped
                        ? "Changes apply to this conversation only."
                        : "Changes apply to your default runtime."}
                    </p>
                  </div>
                  {saving ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[9px] font-bold tracking-wide text-emerald-700 uppercase dark:bg-emerald-500/10 dark:text-emerald-400">
                      <Check size={10} />
                      Saving
                    </span>
                  ) : null}
                </div>

                <div className="space-y-4">
                  <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/[0.07] p-3">
                    <div className="flex items-center gap-2 text-xs font-bold text-cyan-700 dark:text-cyan-100">
                      <ShieldCheck size={13} />
                      Durable execution is active
                    </div>
                    <p className="mt-1 text-[9px] leading-relaxed text-cyan-700/70 dark:text-cyan-100/55">
                      Checkpoints, reconnectable events, approvals, recovery, and replay are
                      enforced by the native runtime. These controls tune planning and workspace
                      behavior; they do not switch to an unprotected legacy runner.
                    </p>
                  </div>

                  {/* Planner Mode Segmented Control */}
                  <div>
                    <span className="mb-1.5 block text-[10px] font-bold tracking-wider text-slate-400 uppercase dark:text-white/35">
                      Planner Mode
                    </span>
                    <div className="relative flex rounded-xl bg-slate-100 p-1 dark:bg-black/20">
                      <button
                        type="button"
                        onClick={() => onChange({ planner_mode: "default" })}
                        className={`relative z-10 flex-1 rounded-lg py-1.5 text-xs font-semibold transition-colors duration-150 ${
                          value.planner_mode === "default"
                            ? "text-slate-900 dark:text-white"
                            : "text-slate-500 hover:text-slate-900 dark:text-white/50 dark:hover:text-white"
                        }`}
                      >
                        {value.planner_mode === "default" && (
                          <span className="absolute inset-0 rounded-lg bg-white shadow-sm dark:bg-[#34362f]" />
                        )}
                        <span className="relative z-20">Default</span>
                      </button>
                      <button
                        type="button"
                        onClick={() => onChange({ planner_mode: "structured" })}
                        className={`relative z-10 flex-1 rounded-lg py-1.5 text-xs font-semibold transition-colors duration-150 ${
                          value.planner_mode === "structured"
                            ? "text-slate-900 dark:text-white"
                            : "text-slate-500 hover:text-slate-900 dark:text-white/50 dark:hover:text-white"
                        }`}
                      >
                        {value.planner_mode === "structured" && (
                          <span className="absolute inset-0 rounded-lg bg-white shadow-sm dark:bg-[#34362f]" />
                        )}
                        <span className="relative z-20">Structured</span>
                      </button>
                    </div>
                  </div>

                  {/* Custom Subagent Bias Selector */}
                  <div className="relative">
                    <span className="mb-1.5 block text-[10px] font-bold tracking-wider text-slate-400 uppercase dark:text-white/35">
                      Subagent Profile Bias
                    </span>
                    <button
                      type="button"
                      aria-label="Subagent profile bias"
                      onClick={() => setBiasOpen((prev) => !prev)}
                      className="flex w-full items-center justify-between rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-800 transition-colors outline-none hover:border-slate-300 focus:border-emerald-500 dark:border-white/5 dark:bg-white/5 dark:text-white dark:hover:border-white/10"
                    >
                      <span className="flex items-center gap-2">
                        {getProfileIcon(value.subagent_profile, {
                          size: 13,
                          className: "text-emerald-500",
                        })}
                        <span>
                          {
                            SUBAGENT_PROFILE_OPTIONS.find((o) => o.value === value.subagent_profile)
                              ?.label
                          }
                        </span>
                      </span>
                      <ChevronDown
                        size={13}
                        className={`text-slate-400 transition-transform duration-200 ${biasOpen ? "rotate-180" : ""}`}
                      />
                    </button>

                    <AnimatePresence>
                      {biasOpen && (
                        <motion.div
                          initial={{ opacity: 0, y: -4, scale: 0.98 }}
                          animate={{ opacity: 1, y: 0, scale: 1 }}
                          exit={{ opacity: 0, y: -4, scale: 0.98 }}
                          transition={{ duration: 0.15, ease: "easeOut" }}
                          className="absolute right-0 left-0 z-50 mt-1 max-h-48 overflow-y-auto rounded-xl border border-slate-200 bg-white/98 p-1 shadow-[0_12px_30px_rgba(0,0,0,0.12)] backdrop-blur-md dark:border-white/10 dark:bg-[#1a1b18]/98 dark:shadow-[0_12px_30px_rgba(0,0,0,0.4)]"
                        >
                          {SUBAGENT_PROFILE_OPTIONS.map((option) => {
                            const isSelected = option.value === value.subagent_profile;
                            return (
                              <button
                                key={option.value}
                                type="button"
                                onClick={() => {
                                  onChange({ subagent_profile: option.value });
                                  setBiasOpen(false);
                                }}
                                className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2 text-left text-xs transition-colors ${
                                  isSelected
                                    ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                                    : "text-slate-700 hover:bg-slate-100 dark:text-white/80 dark:hover:bg-white/5"
                                }`}
                              >
                                {getProfileIcon(option.value, {
                                  size: 13,
                                  className: `mt-0.5 shrink-0 ${isSelected ? "text-emerald-500" : "text-slate-400"}`,
                                })}
                                <div>
                                  <div className="font-bold">{option.label}</div>
                                  <div className="mt-0.5 text-[9px] leading-tight text-slate-400 dark:text-white/35">
                                    {option.description}
                                  </div>
                                </div>
                              </button>
                            );
                          })}
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>

                  {/* Toggles Group */}
                  <div className="space-y-2">
                    {/* Runtime Hooks Card Toggle */}
                    <div
                      onClick={() =>
                        onChange({ runtime_hooks_enabled: !value.runtime_hooks_enabled })
                      }
                      className="group flex cursor-pointer items-center justify-between rounded-xl border border-slate-200 bg-slate-50/50 p-3 transition-all duration-200 select-none hover:border-slate-300 dark:border-white/5 dark:bg-white/2 hover:dark:border-white/10"
                    >
                      <div className="pr-4">
                        <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800 dark:text-white/90">
                          <span>Runtime Hooks</span>
                          {value.runtime_hooks_enabled && (
                            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
                          )}
                        </div>
                        <p className="mt-1 text-[9px] leading-relaxed text-slate-400 dark:text-white/35">
                          Keeps lifecycle hook enforcement and audit extension points active.
                        </p>
                      </div>
                      <button
                        type="button"
                        aria-label="Toggle Runtime Hooks"
                        onClick={(e) => {
                          e.stopPropagation();
                          onChange({ runtime_hooks_enabled: !value.runtime_hooks_enabled });
                        }}
                        className="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors duration-200 focus:outline-none"
                        style={{
                          backgroundColor: value.runtime_hooks_enabled
                            ? "#10b981"
                            : "rgba(255,255,255,0.08)",
                        }}
                      >
                        <span
                          className={`pointer-events-none mt-0.5 ml-0.5 inline-block h-4 w-4 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                            value.runtime_hooks_enabled ? "translate-x-4" : "translate-x-0"
                          }`}
                        />
                      </button>
                    </div>

                    {/* Workspace Code Mode Card Toggle */}
                    <div
                      onClick={() =>
                        onChange({ workspace_mode_enabled: !value.workspace_mode_enabled })
                      }
                      className="group flex cursor-pointer items-center justify-between rounded-xl border border-slate-200 bg-slate-50/50 p-3 transition-all duration-200 select-none hover:border-slate-300 dark:border-white/5 dark:bg-white/2 hover:dark:border-white/10"
                    >
                      <div className="pr-4">
                        <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800 dark:text-white/90">
                          <span>Workspace Code Mode</span>
                          {value.workspace_mode_enabled && (
                            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
                          )}
                        </div>
                        <p className="mt-1 text-[9px] leading-relaxed text-slate-400 dark:text-white/35">
                          Lets coding missions use workspace-aware safety rules and scoped repo
                          actions.
                        </p>
                      </div>
                      <button
                        type="button"
                        aria-label="Toggle Workspace Code Mode"
                        onClick={(e) => {
                          e.stopPropagation();
                          onChange({ workspace_mode_enabled: !value.workspace_mode_enabled });
                        }}
                        className="relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full transition-colors duration-200 focus:outline-none"
                        style={{
                          backgroundColor: value.workspace_mode_enabled
                            ? "#10b981"
                            : "rgba(255,255,255,0.08)",
                        }}
                      >
                        <span
                          className={`pointer-events-none mt-0.5 ml-0.5 inline-block h-4 w-4 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                            value.workspace_mode_enabled ? "translate-x-4" : "translate-x-0"
                          }`}
                        />
                      </button>
                    </div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>,
          document.body,
        )
      )}
    </div>
  );
}
