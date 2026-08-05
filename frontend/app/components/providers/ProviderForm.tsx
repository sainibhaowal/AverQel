"use client";

import { motion } from "framer-motion";
import { Activity, Link2, Link2Off } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import {
  type CreateProviderInput,
  type ProviderCatalogEntry,
  type ProviderConfig,
  type UpdateProviderInput,
  type ProviderModel,
  previewProviderModels,
} from "@/lib/providers-api";

import ProviderAuthFields from "./ProviderAuthFields";
import ProviderModelPicker from "./ProviderModelPicker";

interface ProviderFormProps {
  catalogEntry: ProviderCatalogEntry | null;
  provider: ProviderConfig | null;
  models: ProviderModel[];
  loadingModels?: boolean;
  kind: "chat" | "embedding" | "reranker" | "web" | "all";
  saving: boolean;
  busyAction: string | null;
  onCancel: () => void;
  onSubmit: (payload: CreateProviderInput | UpdateProviderInput) => Promise<void>;
  onTest?: (provider: ProviderConfig) => Promise<void>;
  onDelete?: (provider: ProviderConfig) => void;
  onDisconnect?: (provider: ProviderConfig) => void;
  onReconnect?: (provider: ProviderConfig) => void;
  onRefreshModels?: () => void;
  onPullModel?: () => void;
  pullModelName?: string;
  onPullModelNameChange?: (v: string) => void;
  pullingModel?: boolean;
}

const PROVIDER_BASE_URL_PRESETS: Record<string, string> = {
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com/v1",
  google: "https://generativelanguage.googleapis.com/v1beta",
  groq: "https://api.groq.com/openai/v1",
  mistral: "https://api.mistral.ai/v1",
  lmstudio: "http://localhost:1234/v1",
  together: "https://api.together.xyz/v1",
  fireworks: "https://api.fireworks.ai/inference/v1",
  perplexity: "https://api.perplexity.ai",
  "opencode-zen": "https://opencode.ai/zen/v1",
  cohere: "https://api.cohere.ai/v1",
  tavily: "https://api.tavily.com",
  searxng: "http://searxng:8080",
};

const INVISIBLE_INPUT_CHARS = /[\u200B-\u200D\u2060\uFEFF]/g;

function sanitizeInput(value: string): string {
  return value.replace(INVISIBLE_INPUT_CHARS, "").replace(/`+/g, "").trim();
}

function isValidHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}

function previewCanOmitBaseUrl(providerType: string): boolean {
  return providerType === "sentence-transformers";
}

export default function ProviderForm({
  catalogEntry,
  provider,
  models,
  kind,
  saving,
  onSubmit,
  onTest,
  onDisconnect,
  onReconnect,
}: ProviderFormProps) {
  const activeProviderType = provider?.provider_type || catalogEntry?.provider_type || "";

  const [apiBaseUrl, setApiBaseUrl] = useState(
    provider?.api_base_url || PROVIDER_BASE_URL_PRESETS[activeProviderType] || "",
  );
  const [authMode, setAuthMode] = useState(provider?.auth_mode || "api_key");
  const [secretValue, setSecretValue] = useState("");
  const [searchLanguage, setSearchLanguage] = useState(
    typeof provider?.metadata_json?.language === "string"
      ? provider.metadata_json.language
      : "auto",
  );
  const [allowedDomains, setAllowedDomains] = useState(
    Array.isArray(provider?.metadata_json?.allowed_domains)
      ? provider.metadata_json.allowed_domains.join(", ")
      : "",
  );
  const [blockedDomains, setBlockedDomains] = useState(
    Array.isArray(provider?.metadata_json?.blocked_domains)
      ? provider.metadata_json.blocked_domains.join(", ")
      : "",
  );

  const [defaultChatModel, setDefaultChatModel] = useState(provider?.default_chat_model || "");
  const [defaultEmbeddingModel, setDefaultEmbeddingModel] = useState(
    provider?.default_embedding_model || "",
  );
  const [defaultRerankerModel, setDefaultRerankerModel] = useState(
    provider?.default_reranker_model || "",
  );

  const [previewModels, setPreviewModels] = useState<ProviderModel[]>(provider ? models : []);
  const [discoveringModels, setDiscoveringModels] = useState(false);
  const [discoverError, setDiscoverError] = useState<string | null>(null);

  // Sync when switching to an existing provider
  useEffect(() => {
    if (provider) {
      setApiBaseUrl(provider.api_base_url || "");
      setAuthMode(provider.auth_mode || "none");
      setDefaultChatModel(provider.default_chat_model || "");
      setDefaultEmbeddingModel(provider.default_embedding_model || "");
      setDefaultRerankerModel(provider.default_reranker_model || "");
      setPreviewModels(models);
      setSecretValue("");
      setSearchLanguage(
        typeof provider.metadata_json?.language === "string"
          ? provider.metadata_json.language
          : "auto",
      );
      setAllowedDomains(
        Array.isArray(provider.metadata_json?.allowed_domains)
          ? provider.metadata_json.allowed_domains.join(", ")
          : "",
      );
      setBlockedDomains(
        Array.isArray(provider.metadata_json?.blocked_domains)
          ? provider.metadata_json.blocked_domains.join(", ")
          : "",
      );
      setDiscoverError(null);
    }
  }, [provider, models]);

  // Reset when switching to a different catalog entry (new provider flow)
  useEffect(() => {
    if (!provider && catalogEntry) {
      setAuthMode(catalogEntry.auth_modes[0] || "api_key");
      setApiBaseUrl(PROVIDER_BASE_URL_PRESETS[catalogEntry.provider_type] || "");
      setSecretValue("");
      setSearchLanguage("auto");
      setAllowedDomains("");
      setBlockedDomains("");
      setPreviewModels([]);
      setDefaultChatModel("");
      setDefaultEmbeddingModel("");
      setDefaultRerankerModel("");
      setDiscoverError(null);
    }
  }, [catalogEntry?.provider_type]); // eslint-disable-line react-hooks/exhaustive-deps

  const normalizeApiBaseUrl = useCallback(
    (value: string): string => {
      const trimmed = sanitizeInput(value);
      if (!trimmed || activeProviderType !== "lmstudio") return trimmed;
      try {
        const parsed = new URL(trimmed);
        const path = parsed.pathname.replace(/\/+$/, "");
        if (path.endsWith("/v1")) return parsed.toString().replace(/\/+$/, "");
        parsed.pathname = path ? `${path}/v1` : "/v1";
        return parsed.toString().replace(/\/+$/, "");
      } catch {
        return trimmed;
      }
    },
    [activeProviderType],
  );

  const normalizedPreviewUrl = useMemo(
    () => normalizeApiBaseUrl(apiBaseUrl),
    [apiBaseUrl, normalizeApiBaseUrl],
  );
  const normalizedSecretValue = useMemo(() => sanitizeInput(secretValue), [secretValue]);

  const supportsModelListing = Boolean(
    catalogEntry?.supports_model_listing ?? provider?.supports_model_listing,
  );

  // Model discovery
  useEffect(() => {
    if (!activeProviderType || !supportsModelListing) return;
    // For api_key auth, need a secret before calling (unless editing existing provider)
    if (authMode === "api_key" && !normalizedSecretValue && !provider) return;
    // For editing existing provider with no new secret, skip (models already loaded)
    if (authMode === "api_key" && !normalizedSecretValue && provider) return;
    if (!authMode) return;

    if (authMode !== "api_key" && normalizedSecretValue) {
      setDiscoverError("Clear the secret value for the selected auth mode.");
      setDiscoveringModels(false);
      return;
    }

    if (!normalizedPreviewUrl && !previewCanOmitBaseUrl(activeProviderType)) {
      setDiscoverError(null);
      setDiscoveringModels(false);
      return;
    }

    if (normalizedPreviewUrl && !isValidHttpUrl(normalizedPreviewUrl)) {
      setDiscoverError("Enter a valid http(s) runtime URL to preview models.");
      setDiscoveringModels(false);
      return;
    }

    let cancelled = false;
    const timeoutId = setTimeout(async () => {
      setDiscoveringModels(true);
      setDiscoverError(null);
      try {
        const items = await previewProviderModels({
          provider_type: activeProviderType,
          api_base_url: normalizedPreviewUrl || null,
          auth_mode: authMode,
          api_key: normalizedSecretValue || null,
          supports_chat: catalogEntry?.supports_chat ?? provider?.supports_chat ?? false,
          supports_embeddings:
            catalogEntry?.supports_embeddings ?? provider?.supports_embeddings ?? false,
          supports_reranking:
            catalogEntry?.supports_reranking ?? provider?.supports_reranking ?? false,
          supports_model_listing: true,
        });
        if (!cancelled) {
          setPreviewModels(items);
          setDiscoverError(items.length === 0 ? "No models detected." : null);
        }
      } catch (error) {
        if (!cancelled) {
          setDiscoverError(error instanceof Error ? error.message : "Discovery failed.");
        }
      } finally {
        if (!cancelled) setDiscoveringModels(false);
      }
    }, 600);

    return () => {
      cancelled = true;
      clearTimeout(timeoutId);
    };
  }, [
    activeProviderType,
    authMode,
    normalizedPreviewUrl,
    normalizedSecretValue,
    supportsModelListing,
    catalogEntry?.supports_chat,
    catalogEntry?.supports_embeddings,
    catalogEntry?.supports_reranking,
    provider,
  ]);

  const handleLocalSubmit = async () => {
    const searchMetadata =
      activeProviderType === "searxng"
        ? {
            language: sanitizeInput(searchLanguage) || "auto",
            allowed_domains: allowedDomains
              .split(",")
              .map((item) => sanitizeInput(item).toLowerCase())
              .filter(Boolean)
              .slice(0, 50),
            blocked_domains: blockedDomains
              .split(",")
              .map((item) => sanitizeInput(item).toLowerCase())
              .filter(Boolean)
              .slice(0, 50),
          }
        : undefined;
    const basePayload: CreateProviderInput = {
      display_name: provider?.display_name || catalogEntry?.display_name || "",
      provider_type: activeProviderType,
      api_base_url: normalizeApiBaseUrl(apiBaseUrl) || null,
      auth_mode: authMode,
      enabled: provider?.enabled ?? true,
      supports_chat: catalogEntry?.supports_chat ?? provider?.supports_chat ?? false,
      supports_embeddings:
        catalogEntry?.supports_embeddings ?? provider?.supports_embeddings ?? false,
      supports_reranking: catalogEntry?.supports_reranking ?? provider?.supports_reranking ?? false,
      supports_web_search:
        catalogEntry?.supports_web_search ?? provider?.supports_web_search ?? false,
      supports_model_listing:
        catalogEntry?.supports_model_listing ?? provider?.supports_model_listing ?? false,
      supports_model_install:
        catalogEntry?.supports_model_install ?? provider?.supports_model_install ?? false,
      is_local: catalogEntry?.is_local ?? provider?.is_local ?? false,
      ...(searchMetadata ? { metadata_json: searchMetadata } : {}),
    };

    if (normalizedSecretValue) basePayload.api_key = normalizedSecretValue;
    if (kind === "chat" || kind === "all")
      basePayload.default_chat_model = defaultChatModel || null;
    if (kind === "embedding" || kind === "all")
      basePayload.default_embedding_model = defaultEmbeddingModel || null;
    if (kind === "reranker" || kind === "all")
      basePayload.default_reranker_model = defaultRerankerModel || null;

    if (provider) {
      const updatePayload: UpdateProviderInput = {
        display_name: basePayload.display_name,
        api_base_url: basePayload.api_base_url,
        enabled: basePayload.enabled,
        default_chat_model: basePayload.default_chat_model,
        default_embedding_model: basePayload.default_embedding_model,
        default_reranker_model: basePayload.default_reranker_model,
        ...(searchMetadata ? { metadata_json: searchMetadata } : {}),
      };
      if (basePayload.api_key) updatePayload.api_key = basePayload.api_key;
      await onSubmit(updatePayload);
      return;
    }

    await onSubmit(basePayload);
  };

  const activeModelName =
    kind === "chat"
      ? defaultChatModel
      : kind === "embedding"
        ? defaultEmbeddingModel
        : kind === "reranker"
          ? defaultRerankerModel
          : "";

  const filteredModels = useMemo(() => {
    const visibleModels = previewModels.length > 0 ? previewModels : provider ? models : [];
    if (kind === "all") return visibleModels;
    return visibleModels.filter((m) => {
      if (kind === "chat") return m.model_kind === "chat" || m.model_kind === "other";
      if (kind === "embedding") return m.model_kind === "embedding";
      if (kind === "reranker") return m.model_kind === "reranker";
      if (kind === "web") return false;
      return true;
    });
  }, [kind, models, previewModels, provider]);

  const isHealthy = provider?.latest_health?.status === "healthy";
  const requiresApiKey = authMode === "api_key";
  const waitingForToken = requiresApiKey && !secretValue && !provider;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex min-h-0 flex-1 flex-col"
    >
      <div className="scrollbar-thin min-h-0 flex-1 space-y-6 overflow-y-auto pb-2">
        {/* scrollable content */}
        {/* Header */}
        <div>
          <p className="text-muted-foreground/60 font-mono text-[10px] font-bold tracking-[0.24em] uppercase">
            {kind.toUpperCase()} Setup
          </p>
          <h2 className="text-foreground mt-1 text-3xl font-black tracking-tight">
            {provider?.display_name || catalogEntry?.display_name || "New Connection"}
          </h2>
          <p className="text-muted-foreground mt-1.5 max-w-xl text-sm">
            Connect this {kind === "all" ? "provider" : kind} provider, enter the API key, then link
            it.
          </p>
          <div className="settings-divider mt-3" style={{ maxWidth: "50%" }} />
        </div>

        {/* Fields */}
        <div className="space-y-6">
          <ProviderAuthFields
            providerType={activeProviderType}
            catalogEntry={catalogEntry || undefined}
            authMode={authMode}
            onAuthModeChange={setAuthMode}
            apiBaseUrl={apiBaseUrl}
            onApiBaseUrlChange={setApiBaseUrl}
            secretValue={secretValue}
            onSecretValueChange={setSecretValue}
            maskedSummary={provider?.secrets?.[0]?.masked_value || null}
          />

          {activeProviderType === "searxng" && (
            <div className="theme-panel-muted grid gap-4 rounded-2xl p-5 ring-1 ring-white/5 md:grid-cols-3">
              <div className="space-y-1.5">
                <label className="text-muted-foreground/60 px-0.5 font-mono text-[9px] tracking-[0.2em] uppercase">
                  Search language
                </label>
                <input
                  value={searchLanguage}
                  onChange={(event) => setSearchLanguage(event.target.value)}
                  placeholder="auto"
                  className="border-glass-border bg-surface-1 text-foreground h-10 w-full rounded-xl border px-3 text-xs outline-none"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-muted-foreground/60 px-0.5 font-mono text-[9px] tracking-[0.2em] uppercase">
                  Allowed domains
                </label>
                <input
                  value={allowedDomains}
                  onChange={(event) => setAllowedDomains(event.target.value)}
                  placeholder="example.com, docs.example.org"
                  className="border-glass-border bg-surface-1 text-foreground h-10 w-full rounded-xl border px-3 text-xs outline-none"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-muted-foreground/60 px-0.5 font-mono text-[9px] tracking-[0.2em] uppercase">
                  Blocked domains
                </label>
                <input
                  value={blockedDomains}
                  onChange={(event) => setBlockedDomains(event.target.value)}
                  placeholder="ads.example.com"
                  className="border-glass-border bg-surface-1 text-foreground h-10 w-full rounded-xl border px-3 text-xs outline-none"
                />
              </div>
            </div>
          )}

          {kind !== "web" ? (
            <div className="space-y-2">
              <label className="text-muted-foreground/60 px-1 font-mono text-[10px] font-bold tracking-[0.2em] uppercase">
                {kind.toUpperCase()} Model
              </label>
              <ProviderModelPicker
                label=""
                value={activeModelName}
                models={filteredModels}
                onChange={(v) => {
                  if (kind === "chat" || kind === "all") setDefaultChatModel(v);
                  if (kind === "embedding" || kind === "all") setDefaultEmbeddingModel(v);
                  if (kind === "reranker" || kind === "all") setDefaultRerankerModel(v);
                }}
                kinds={kind === "all" ? ["chat", "embedding", "reranker"] : [kind]}
                allowClear
              />
            </div>
          ) : null}
        </div>

        {/* Model Discovery Status */}
        {kind !== "web" ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between px-1">
              <span className="text-muted-foreground/60 font-mono text-[10px] font-bold tracking-[0.2em] uppercase">
                Model Discovery
              </span>
              {waitingForToken ? (
                <span className="animate-pulse rounded-full border border-amber-500/40 bg-amber-500/15 px-3 py-1 font-mono text-[9px] font-black tracking-widest text-amber-700 uppercase dark:text-amber-400">
                  ⊙ Waiting for token
                </span>
              ) : discoveringModels ? (
                <span className="border-primary/20 bg-primary/10 text-primary rounded-full border px-3 py-1 font-mono text-[9px] font-bold tracking-widest uppercase">
                  Discovery active
                </span>
              ) : previewModels.length > 0 ? (
                <span className="rounded-full border border-teal-500/40 bg-teal-500/15 px-3 py-1 font-mono text-[9px] font-black tracking-widest text-teal-700 uppercase dark:text-teal-400">
                  {previewModels.length} models found
                </span>
              ) : null}
            </div>
            <div className="text-muted-foreground/60 rounded-2xl border border-white/5 bg-white/[0.02] p-4 text-xs">
              {discoverError ? (
                <p className="text-red-400/80">{discoverError}</p>
              ) : discoveringModels ? (
                <p>Inspecting endpoint and validating credentials...</p>
              ) : (
                <p>
                  When you enter the token, supported {kind === "all" ? "provider" : kind} models
                  are fetched automatically for this provider.
                </p>
              )}
            </div>
          </div>
        ) : null}

        {/* 3 Status Cards */}
        <div className="grid gap-4 md:grid-cols-3">
          <StatusPanel
            label="Current Target"
            value={
              kind === "web"
                ? catalogEntry?.display_name || provider?.display_name || "Web Search"
                : activeModelName || "No model selected"
            }
            subtext={`${(catalogEntry?.is_local ?? provider?.is_local) ? "Managed" : "Hosted"} ${kind} runtime`}
          />
          <StatusPanel label="Runtime URL" value={apiBaseUrl || "Not set"} />
          <StatusPanel
            label="Status"
            value={provider ? (isHealthy ? "Healthy" : "Unknown") : "Not connected"}
            indicator={provider ? (isHealthy ? "success" : "warning") : undefined}
            subtext={provider ? "Last runtime check." : "No runtime check yet."}
          />
        </div>
      </div>
      {/* end scrollable content */}

      {/* Sticky footer — always visible regardless of scroll position */}
      <div className="mt-2 flex shrink-0 items-center justify-between border-t border-white/5 pt-5">
        <button
          onClick={() => provider && onTest?.(provider)}
          disabled={!provider}
          className="text-foreground/40 hover:text-foreground flex items-center gap-2 text-xs font-bold tracking-widest uppercase transition-colors disabled:opacity-20"
        >
          <Activity size={14} />
          Test ping
        </button>

        {provider ? (
          <button
            onClick={() => onDisconnect?.(provider)}
            className="flex items-center gap-2 text-xs font-bold tracking-widest text-amber-400/80 uppercase transition-colors hover:text-amber-300"
          >
            <Link2Off size={14} />
            Terminate
          </button>
        ) : (
          <span className="text-foreground/25 text-[10px] font-bold tracking-[0.22em] uppercase">
            Configure and link
          </span>
        )}

        <button
          onClick={handleLocalSubmit}
          disabled={saving}
          className="to-primary/80 flex items-center gap-3 rounded-xl bg-gradient-to-r from-teal-500/80 px-8 py-3.5 text-sm font-bold text-white shadow-xl transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
        >
          <Link2 size={16} />
          {saving ? "Saving..." : provider ? "Update Connectivity" : "Link Family"}
        </button>
      </div>

      {/* Disabled overlay */}
      {provider && !provider.enabled && (
        <div className="absolute inset-0 z-20 flex flex-col items-center justify-center rounded-2xl bg-slate-950/80 backdrop-blur-md">
          <p className="font-bold tracking-widest text-amber-400 uppercase">
            Connection Interrupted
          </p>
          <button
            onClick={() => onReconnect?.(provider)}
            className="bg-primary mt-6 flex items-center gap-2 rounded-full px-8 py-3 text-sm font-bold text-slate-950 shadow-xl transition-transform hover:scale-[1.05]"
          >
            <Link2 size={16} />
            Resume Connectivity
          </button>
        </div>
      )}
    </motion.div>
  );
}

function StatusPanel({
  label,
  value,
  subtext,
  indicator,
}: {
  label: string;
  value: string;
  subtext?: string;
  indicator?: "success" | "warning" | "error";
}) {
  return (
    <div className="theme-panel-muted flex flex-col justify-between space-y-3 rounded-2xl p-5 ring-1 ring-white/5">
      <span className="text-foreground/30 font-mono text-[9px] font-bold tracking-widest uppercase">
        {label}
      </span>
      <div>
        <div className="flex items-center gap-2">
          {indicator && (
            <div
              className={`h-1.5 w-1.5 rounded-full ${
                indicator === "success"
                  ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]"
                  : indicator === "warning"
                    ? "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]"
                    : "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]"
              }`}
            />
          )}
          <p className="text-foreground text-[13px] font-black">{value || "None"}</p>
        </div>
        {subtext && <p className="text-foreground/60 mt-1 text-[10px] font-bold">{subtext}</p>}
      </div>
    </div>
  );
}
