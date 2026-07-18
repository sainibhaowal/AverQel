"use client";

import { Cpu, ShieldCheck, Sparkles, Workflow, Wrench } from "lucide-react";
import type { RuntimePreferencesValue } from "./RuntimePreferencesDropdown";

export interface RuntimeIndicatorState {
  executionMode: "auto_review" | "full_access";
  plannerMode: RuntimePreferencesValue["planner_mode"];
  subagentProfile: RuntimePreferencesValue["subagent_profile"];
  runtimeHooksEnabled: boolean;
  workspaceModeEnabled?: boolean;
}

function formatModeLabel(value: string): string {
  return value.replace(/_/g, " ");
}

function profileLabel(profile: RuntimePreferencesValue["subagent_profile"]): string {
  if (profile === "default") {
    return "Adaptive";
  }
  return profile.charAt(0).toUpperCase() + profile.slice(1);
}

export default function RuntimeIndicatorChips({
  indicators,
  compact = false,
  includeExecutionMode = true,
  className = "",
}: {
  indicators: RuntimeIndicatorState;
  compact?: boolean;
  includeExecutionMode?: boolean;
  className?: string;
}) {
  return (
    <div className={`flex flex-wrap gap-2.5 ${className}`.trim()}>
      {includeExecutionMode && (
        <div className="group relative">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-sky-500/20 bg-sky-500/10 text-sky-300 shadow-sm backdrop-blur-md">
            <ShieldCheck size={14} />
            <span className="sr-only">Mode: {formatModeLabel(indicators.executionMode)}</span>
          </div>
          {/* Custom Tooltip */}
          <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 z-50 -translate-x-1/2 opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
            <div className="theme-panel border-glass-border bg-surface-0/95 min-w-[150px] border p-2 shadow-2xl backdrop-blur-xl rounded-lg text-center">
              <span className="text-[10px] font-bold text-sky-300 uppercase tracking-wider block">
                Execution Mode
              </span>
              <span className="text-[11px] text-foreground font-medium mt-0.5 block">
                {formatModeLabel(indicators.executionMode)}
              </span>
            </div>
          </div>
        </div>
      )}

      <div className="group relative">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-fuchsia-500/20 bg-fuchsia-500/10 text-fuchsia-300 shadow-sm backdrop-blur-md">
            <Workflow size={14} />
            <span className="sr-only">
              Planner: {indicators.plannerMode === "structured" ? "structured" : "default"}
            </span>
        </div>
        {/* Custom Tooltip */}
        <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 z-50 -translate-x-1/2 opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
          <div className="theme-panel border-glass-border bg-surface-0/95 min-w-[150px] border p-2 shadow-2xl backdrop-blur-xl rounded-lg text-center">
            <span className="text-[10px] font-bold text-fuchsia-300 uppercase tracking-wider block">
              Planner Mode
            </span>
            <span className="text-[11px] text-foreground font-medium mt-0.5 block">
              {indicators.plannerMode === "structured" ? "Structured" : "Default"}
            </span>
          </div>
        </div>
      </div>

      <div className="group relative">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-cyan-500/20 bg-cyan-500/10 text-cyan-300 shadow-sm backdrop-blur-md">
            <Sparkles size={14} />
            <span className="sr-only">Subagent: {profileLabel(indicators.subagentProfile)}</span>
        </div>
        {/* Custom Tooltip */}
        <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 z-50 -translate-x-1/2 opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
          <div className="theme-panel border-glass-border bg-surface-0/95 min-w-[150px] border p-2 shadow-2xl backdrop-blur-xl rounded-lg text-center">
            <span className="text-[10px] font-bold text-cyan-300 uppercase tracking-wider block">
              Subagent Profile
            </span>
            <span className="text-[11px] text-foreground font-medium mt-0.5 block">
              {profileLabel(indicators.subagentProfile)}
            </span>
          </div>
        </div>
      </div>

      <div className="group relative">
        <div
          className={`flex h-8 w-8 items-center justify-center rounded-lg border transition-all duration-300 ${
            indicators.runtimeHooksEnabled
              ? "border-emerald-500/20 bg-emerald-500/10 text-emerald-300 shadow-sm"
              : "border-white/5 bg-white/5 text-white/30 grayscale"
          }`}
        >
          <Cpu size={14} />
        </div>
        {/* Custom Tooltip */}
        <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 z-50 -translate-x-1/2 opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
          <div className="theme-panel border-glass-border bg-surface-0/95 min-w-[150px] border p-2 shadow-2xl backdrop-blur-xl rounded-lg text-center">
            <span className={`text-[10px] font-bold uppercase tracking-wider block ${indicators.runtimeHooksEnabled ? "text-emerald-300" : "text-white/40"}`}>
              Runtime Hooks
            </span>
            <span className="text-[11px] text-foreground font-medium mt-0.5 block">
              {indicators.runtimeHooksEnabled ? "Hooks Active" : "Hooks Paused"}
            </span>
          </div>
        </div>
      </div>

      {typeof indicators.workspaceModeEnabled === "boolean" && (
        <div className="group relative">
          <div
            className={`flex h-8 w-8 items-center justify-center rounded-lg border transition-all duration-300 ${
              indicators.workspaceModeEnabled
                ? "border-amber-500/20 bg-amber-500/10 text-amber-300 shadow-sm"
                : "border-white/5 bg-white/5 text-white/30 grayscale"
            }`}
          >
            <Wrench size={14} />
          </div>
          {/* Custom Tooltip */}
          <div className="pointer-events-none absolute bottom-full left-1/2 mb-2 z-50 -translate-x-1/2 opacity-0 transition-all duration-200 group-hover:pointer-events-auto group-hover:mb-3 group-hover:opacity-100">
            <div className="theme-panel border-glass-border bg-surface-0/95 min-w-[150px] border p-2 shadow-2xl backdrop-blur-xl rounded-lg text-center">
              <span className={`text-[10px] font-bold uppercase tracking-wider block ${indicators.workspaceModeEnabled ? "text-amber-300" : "text-white/40"}`}>
                Workspace Mode
              </span>
              <span className="text-[11px] text-foreground font-medium mt-0.5 block">
                {indicators.workspaceModeEnabled ? "Code Mode Scoped" : "Code Mode Off"}
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
