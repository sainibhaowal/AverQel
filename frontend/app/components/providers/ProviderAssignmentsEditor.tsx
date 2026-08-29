"use client";

import * as React from "react";
import { ArrowRightLeft, BrainCircuit, Globe2, Layers3, SearchCheck, Sparkles } from "lucide-react";

import ProviderDropdown from "@/app/components/providers/ProviderDropdown";
import type { ProviderAssignment, ProviderConfig, ProviderModel } from "@/lib/providers-api";

const FEATURE_SCOPES = [
  "chat",
  "embeddings",
  "reranking",
  "fallback_chat",
  "fallback_embeddings",
  "fallback_reranking",
  "web_search",
  "fallback_web_search",
] as const;

interface ProviderAssignmentsEditorProps {
  assignments: ProviderAssignment[];
  providers: ProviderConfig[];
  modelsByProvider: Record<string, ProviderModel[]>;
  onSave: (featureScope: string, providerConfigId: string | null, modelName: string | null) => void;
  savingScope?: string | null;
}

function providerSupportsScope(provider: ProviderConfig, scope: string) {
  if (scope.includes("web_search"))
    return provider.supports_web_search || ["tavily", "searxng"].includes(provider.provider_type);
  if (scope.includes("reranking")) return provider.supports_reranking;
  if (scope.includes("embedding")) return provider.supports_embeddings;
  return provider.supports_chat;
}

function scopeMeta(scope: string) {
  if (scope === "chat") return { label: "Chat", desc: "Primary answer route", fallback: false };
  if (scope === "embeddings")
    return { label: "Embeddings", desc: "Primary retrieval route", fallback: false };
  if (scope === "reranking")
    return { label: "Reranking", desc: "Second-stage evidence refinement", fallback: false };
  if (scope === "web_search")
    return { label: "Web search", desc: "External search route", fallback: false };
  if (scope === "fallback_chat")
    return { label: "Fallback chat", desc: "Backup answer route", fallback: true };
  if (scope === "fallback_reranking")
    return { label: "Fallback reranking", desc: "Backup reranker route", fallback: true };
  if (scope === "fallback_web_search")
    return { label: "Fallback web search", desc: "Backup external search route", fallback: true };
  return { label: "Fallback embeddings", desc: "Backup retrieval route", fallback: true };
}

function modelSupportsScope(model: ProviderModel, scope: string) {
  if (scope.includes("web_search")) {
    return false;
  }
  if (scope.includes("reranking")) {
    return model.model_kind === "reranker";
  }
  if (scope.includes("embedding")) {
    return model.model_kind === "embedding";
  }
  return model.model_kind === "chat";
}

function scopeIcon(scope: string) {
  if (scope.includes("web_search")) {
    return <Globe2 size={16} />;
  }
  if (scope.includes("reranking")) {
    return <SearchCheck size={16} />;
  }
  if (scope.includes("embedding")) {
    return <Layers3 size={16} />;
  }
  return <BrainCircuit size={16} />;
}

export default function ProviderAssignmentsEditor({
  assignments,
  providers,
  modelsByProvider,
  onSave,
  savingScope = null,
}: ProviderAssignmentsEditorProps) {
  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-foreground/55 text-[11px] font-semibold tracking-[0.24em] uppercase">
            Feature Assignments
          </p>
          <h3 className="text-foreground mt-1 text-lg font-semibold tracking-tight">
            Assignment board
          </h3>
        </div>
      </div>

      <div className="theme-panel-muted overflow-hidden rounded-[1.6rem]">
        {FEATURE_SCOPES.map((scope, index) => (
          <AssignmentRow
            key={scope}
            scope={scope}
            assignment={assignments.find((item) => item.feature_scope === scope) ?? null}
            providers={providers}
            modelsByProvider={modelsByProvider}
            saving={savingScope === scope}
            onSave={onSave}
            bordered={index !== FEATURE_SCOPES.length - 1}
          />
        ))}
      </div>
    </div>
  );
}

function AssignmentRow({
  scope,
  assignment,
  providers,
  modelsByProvider,
  saving,
  onSave,
  bordered,
}: {
  scope: string;
  assignment: ProviderAssignment | null;
  providers: ProviderConfig[];
  modelsByProvider: Record<string, ProviderModel[]>;
  saving: boolean;
  onSave: (featureScope: string, providerConfigId: string | null, modelName: string | null) => void;
  bordered: boolean;
}) {
  const meta = scopeMeta(scope);
  const allowsServerDefault = scope.includes("embedding") || scope.includes("reranking");
  const compatibleProviders = providers.filter(
    (provider) => provider.enabled && providerSupportsScope(provider, scope),
  );
  const [selectedProviderId, setSelectedProviderId] = React.useState(
    assignment?.provider_config_id || (allowsServerDefault ? "" : compatibleProviders[0]?.id || ""),
  );
  const [selectedModel, setSelectedModel] = React.useState(assignment?.model_name || "");

  React.useEffect(() => {
    queueMicrotask(() => {
      setSelectedProviderId(
        assignment?.provider_config_id ||
          (allowsServerDefault ? "" : compatibleProviders[0]?.id || ""),
      );
      setSelectedModel(assignment?.model_name || "");
    });
  }, [
    allowsServerDefault,
    assignment?.model_name,
    assignment?.provider_config_id,
    compatibleProviders,
  ]);

  const models = selectedProviderId
    ? (modelsByProvider[selectedProviderId] || []).filter((model) =>
        modelSupportsScope(model, scope),
      )
    : [];

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSave(scope, selectedProviderId, selectedModel || null);
      }}
      className={`grid gap-4 px-4 py-4 xl:grid-cols-[220px,1fr,1fr,auto] xl:items-center ${bordered ? "border-glass-border border-b" : ""}`}
    >
      <div className="flex items-start gap-3">
        <div className="theme-chip text-accent-cyan flex h-10 w-10 shrink-0 items-center justify-center rounded-[0.95rem]">
          {scopeIcon(scope)}
        </div>
        <div>
          <div className="theme-chip text-foreground/55 inline-flex items-center gap-2 rounded-full px-2.5 py-1 text-[10px] font-semibold tracking-[0.2em] uppercase">
            {meta.fallback ? <ArrowRightLeft size={11} /> : <Sparkles size={11} />}
            {meta.fallback ? "Fallback" : "Primary"}
          </div>
          <p className="text-foreground mt-2 text-sm font-semibold">{meta.label}</p>
          <p className="text-muted-foreground text-xs">{meta.desc}</p>
        </div>
      </div>

      <ProviderDropdown
        label="Provider"
        value={selectedProviderId}
        onChange={(value) => {
          setSelectedProviderId(value);
          setSelectedModel("");
        }}
        disabled={compatibleProviders.length === 0 && !allowsServerDefault}
        placeholder={
          compatibleProviders.length === 0 && !allowsServerDefault
            ? "No compatible providers"
            : "Select provider"
        }
        name={`provider-${scope}`}
        options={[
          ...(allowsServerDefault
            ? [
                {
                  value: "",
                  label: "Use server default",
                  hint: "No explicit assignment",
                },
              ]
            : []),
          ...compatibleProviders.map((provider) => ({
            value: provider.id,
            label: provider.display_name,
            hint: provider.provider_type,
          })),
        ]}
      />

      <ProviderDropdown
        label="Model override"
        value={selectedModel}
        onChange={setSelectedModel}
        placeholder="Provider default"
        name={`model-${scope}`}
        options={models.map((model) => ({
          value: model.model_name,
          label: model.display_name || model.model_name,
          hint: model.model_kind,
        }))}
      />

      <button
        type="submit"
        disabled={
          saving ||
          (!selectedProviderId && !allowsServerDefault) ||
          (compatibleProviders.length === 0 && !allowsServerDefault)
        }
        className="inline-flex items-center justify-center rounded-full bg-[linear-gradient(135deg,#14b8a6,#0ea5e9)] px-4 py-3 text-sm font-semibold text-slate-950 disabled:opacity-50"
      >
        {saving ? "Saving..." : allowsServerDefault && !selectedProviderId ? "Use default" : "Save"}
      </button>
    </form>
  );
}
