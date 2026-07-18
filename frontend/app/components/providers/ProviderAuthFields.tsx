"use client";

import { Globe, KeyRound, Info } from "lucide-react";
import React from "react";

import ProviderDropdown from "./ProviderDropdown";
import ProviderSecretField from "./ProviderSecretField";

interface ProviderAuthFieldsProps {
  providerType: string;
  catalogEntry?: {
    auth_modes: string[];
    is_local?: boolean;
  };
  authMode: string;
  onAuthModeChange: (mode: string) => void;
  apiBaseUrl: string;
  onApiBaseUrlChange: (url: string) => void;
  secretValue: string;
  onSecretValueChange: (value: string) => void;
  maskedSummary: string | null;
}

export default function ProviderAuthFields({
  catalogEntry,
  authMode,
  onAuthModeChange,
  apiBaseUrl,
  onApiBaseUrlChange,
  secretValue,
  onSecretValueChange,
  maskedSummary,
}: ProviderAuthFieldsProps) {
  const authModes = catalogEntry?.auth_modes || ["api_key", "none"];
  // Only hide URL for fully built-in providers (auth_mode "none") — local runtimes like LM Studio still need their URL
  const requiresBaseUrl = authMode !== "none";

  const authOptions = authModes.map((m) => ({
    value: m,
    label:
      m === "api_key" ? "API Key" : m === "none" ? "No Authentication" : m.replaceAll("_", " "),
  }));

  return (
    <div className="space-y-8">
      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-muted-foreground/60 block px-0.5 font-mono text-[9px] tracking-[0.2em] uppercase">
            Authentication Protocol
          </label>
          <ProviderDropdown
            value={authMode}
            onChange={onAuthModeChange}
            options={authOptions}
            placeholder="Select Auth Mode"
            className="bg-surface-1 border-glass-border h-10 opacity-90"
          />
        </div>

        <div className="space-y-1.5">
          <label className="text-muted-foreground/60 block px-0.5 font-mono text-[9px] tracking-[0.2em] uppercase">
            API / Runtime URL
          </label>
          {requiresBaseUrl ? (
            <div className="group relative">
              <input
                type="text"
                value={apiBaseUrl}
                onChange={(e) => onApiBaseUrlChange(e.target.value)}
                placeholder="https://api.provider.ai/v1"
                className="border-glass-border bg-surface-1 text-foreground placeholder:text-muted-foreground/30 focus:border-primary/40 focus:ring-primary/5 h-10 w-full rounded-xl border px-4 text-xs ring-1 ring-transparent transition-all outline-none"
              />
              <Globe className="text-muted-foreground/40 group-focus-within:text-primary/50 pointer-events-none absolute top-[11px] right-4 h-3.5 w-3.5 transition-colors" />
            </div>
          ) : (
            <div className="border-glass-border bg-muted/30 text-muted-foreground/50 flex h-10 items-center gap-3 rounded-xl border border-dashed px-4 text-[10px]">
              <Info size={13} className="text-primary/40" />
              Managed runtime; no URL needed.
            </div>
          )}
        </div>
      </div>

      {authMode === "api_key" && (
        <div className="space-y-1.5">
          <label className="text-muted-foreground/60 block px-0.5 font-mono text-[9px] tracking-[0.2em] uppercase">
            Security Token / Secret
          </label>
          <div className="group relative">
            <ProviderSecretField
              value={secretValue}
              onChange={onSecretValueChange}
              maskedSummary={maskedSummary}
              className="bg-surface-1 border-glass-border h-10"
            />
            <KeyRound className="text-muted-foreground/40 group-focus-within:text-primary/50 pointer-events-none absolute top-[11px] right-4 h-3.5 w-3.5 transition-colors" />
          </div>
        </div>
      )}
    </div>
  );
}
