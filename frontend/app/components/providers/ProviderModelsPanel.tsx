"use client";

import { Download, RefreshCw, Layers, ShieldCheck, Zap } from "lucide-react";
import ProviderModelPicker from "@/app/components/providers/ProviderModelPicker";
import type { ProviderConfig, ProviderModel } from "@/lib/providers-api";

type ProviderModelKind = "chat" | "embedding" | "reranker" | "other";

interface ProviderModelsPanelProps {
  activeServiceKind: "chat" | "embedding" | "reranker" | "all";
  provider: ProviderConfig | null;
  models: ProviderModel[];
  loading?: boolean;
  pulling?: boolean;
  pullModelName: string;
  onPullModelNameChange: (value: string) => void;
  onRefresh: () => void;
  onPull: () => void;
  defaultModel: string;
  onDefaultModelChange: (value: string) => void;
}

/**
 * Single-purpose model management dashboard.
 * Dynamically adapts to the active service kind for focused configuration.
 */
export default function ProviderModelsPanel({
  activeServiceKind,
  provider,
  models,
  loading = false,
  pulling = false,
  pullModelName,
  onPullModelNameChange,
  onRefresh,
  onPull,
  defaultModel,
  onDefaultModelChange,
}: ProviderModelsPanelProps) {
  const providerEnabled = provider?.enabled ?? false;

  // Selective filtering based on the active tab context
  const filteredModels = models.filter((m) => {
    if (activeServiceKind === "all") return true;
    if (activeServiceKind === "chat") return m.model_kind === "chat" || m.model_kind === "other";
    if (activeServiceKind === "embedding") return m.model_kind === "embedding";
    if (activeServiceKind === "reranker") return m.model_kind === "reranker";
    return true;
  });

  const getLabel = () => {
    if (activeServiceKind === "chat") return "Primary Conversational Assistant";
    if (activeServiceKind === "embedding") return "Intelligence Embedding Interface";
    if (activeServiceKind === "reranker") return "Search Refinement Reranker";
    return "Default Runtime Model";
  };

  const getIcon = () => {
    if (activeServiceKind === "chat") return <Layers size={14} />;
    if (activeServiceKind === "embedding") return <ShieldCheck size={14} />;
    if (activeServiceKind === "reranker") return <Zap size={14} />;
    return <Layers size={14} />;
  };

  return (
    <div className="flex flex-col space-y-6">
      {/* Dynamic Model Routing */}
      <div className="space-y-4">
        <div className="flex items-center justify-between border-b border-white/5 pb-4">
          <div className="space-y-1">
            <div className="text-foreground/45 flex items-center gap-2 text-[10px] font-bold tracking-[0.2em] uppercase">
              {getIcon()}
              Active Routing Profile
            </div>
            <p className="text-muted-foreground text-xs">
              Select the default model for{" "}
              {activeServiceKind === "all" ? "the runtime" : activeServiceKind} service.
            </p>
          </div>

          <button
            type="button"
            onClick={onRefresh}
            disabled={!providerEnabled || loading}
            className="theme-chip text-foreground/60 hover:text-foreground flex items-center gap-2 rounded-full px-4 py-2 text-[11px] font-bold tracking-widest uppercase disabled:opacity-40"
          >
            {loading ? <RefreshCw size={12} className="animate-spin" /> : <RefreshCw size={12} />}
            Synchronize
          </button>
        </div>

        <ProviderModelPicker
          label={getLabel()}
          value={defaultModel}
          models={filteredModels}
          onChange={(v) => providerEnabled && onDefaultModelChange(v)}
          kinds={
            activeServiceKind === "all"
              ? ["chat", "embedding", "reranker", "other"]
              : [activeServiceKind as ProviderModelKind, "other"]
          }
          allowClear
          disabled={!providerEnabled}
        />
      </div>

      {/* Model Inventory Area */}
      <div className="space-y-4">
        <div className="text-foreground/45 flex items-center gap-2 px-1 text-[10px] font-bold tracking-[0.2em] uppercase">
          Model Discovery Inventory
          <span className="theme-chip rounded-full px-2 py-0.5 opacity-60">
            {filteredModels.length}
          </span>
        </div>

        <div className="theme-panel-muted scrollbar-hide max-h-60 overflow-y-auto rounded-3xl ring-1 ring-white/5">
          {filteredModels.length === 0 ? (
            <div className="text-muted-foreground p-8 text-center text-xs italic">
              No {activeServiceKind === "all" ? "" : activeServiceKind} models identified. Try
              synchronizing.
            </div>
          ) : (
            <div className="divide-y divide-white/5">
              {filteredModels.map((model) => (
                <div
                  key={`${model.model_kind}-${model.model_name}`}
                  className="flex items-center justify-between px-5 py-3.5 hover:bg-white/[0.02]"
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-foreground/90 truncate text-[13px] font-medium">
                      {model.display_name || model.model_name}
                    </p>
                    <div className="mt-0.5 flex items-center gap-2">
                      <span className="text-foreground/30 text-[9px] font-bold tracking-widest uppercase">
                        {model.model_kind}
                      </span>
                      {typeof model.capabilities_json.quantization === "string" && (
                        <>
                          <span className="text-foreground/20 text-[9px]">•</span>
                          <span className="text-[9px] font-bold tracking-widest text-cyan-300/70 uppercase">
                            {model.capabilities_json.quantization}
                          </span>
                        </>
                      )}
                      <span className="text-foreground/20 text-[9px]">•</span>
                      <span className="text-foreground/30 text-[9px] font-bold tracking-widest uppercase">
                        {model.context_window
                          ? `${Math.floor(model.context_window / 1000)}k ctx`
                          : "ctx unknown"}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Local Pull Controls (Scoped) */}
      {provider?.supports_model_install && (
        <div className="theme-panel-muted relative flex items-center gap-4 rounded-3xl p-4 ring-1 ring-white/5">
          <div className="absolute -top-2.5 right-6 flex items-center gap-1.5 rounded-full border border-white/10 bg-slate-900 px-2.5 py-0.5 text-[9px] font-bold tracking-widest text-cyan-400 uppercase">
            <Download size={10} />
            Runtime Pull
          </div>
          <input
            value={pullModelName}
            onChange={(e) => onPullModelNameChange(e.target.value)}
            placeholder="Search & pull from registry..."
            className="text-foreground placeholder:text-foreground/20 flex-1 bg-transparent px-2 text-xs outline-none"
          />
          <button
            onClick={onPull}
            disabled={!providerEnabled || !pullModelName.trim() || pulling}
            className="flex items-center gap-2 rounded-xl bg-teal-400 px-4 py-2.5 text-[11px] font-bold text-slate-950 uppercase transition-all hover:scale-[1.02] disabled:opacity-40"
          >
            {pulling ? <RefreshCw size={14} className="animate-spin" /> : <Download size={14} />}
            Pull
          </button>
        </div>
      )}
    </div>
  );
}
