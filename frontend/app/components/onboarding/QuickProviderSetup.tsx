"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  KeyRound,
  Laptop,
  LoaderCircle,
  Search,
} from "lucide-react";
import OpenAICodexLoginPanel from "@/app/components/providers/OpenAICodexLoginPanel";
import {
  createProvider,
  listSupportedProviderTypes,
  previewProviderModels,
  type ProviderCatalogEntry,
  type ProviderModel,
} from "@/lib/providers-api";

type Props = {
  onConfigured: (name: string) => void;
  onOpenSettings: () => void;
  onBusyChange: (busy: boolean) => void;
};

const BASE_URLS: Record<string, string> = {
  openai: "https://api.openai.com/v1",
  anthropic: "https://api.anthropic.com/v1",
  google: "https://generativelanguage.googleapis.com/v1beta",
  deepseek: "https://api.deepseek.com",
  groq: "https://api.groq.com/openai/v1",
  mistral: "https://api.mistral.ai/v1",
  openrouter: "https://openrouter.ai/api/v1",
  together: "https://api.together.xyz/v1",
  fireworks: "https://api.fireworks.ai/inference/v1",
  perplexity: "https://api.perplexity.ai",
  moonshot: "https://api.moonshot.ai/v1",
  zai: "https://api.z.ai/api/paas/v4",
  "nvidia-nim": "https://integrate.api.nvidia.com/v1",
  cohere: "https://api.cohere.ai/v1",
  "opencode-zen": "https://opencode.ai/zen/v1",
  lmstudio: "http://localhost:1234/v1",
  ollama: "http://localhost:11434",
};

function normalizeBaseUrl(providerType: string, value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  if (providerType !== "lmstudio" || !trimmed) return trimmed;
  try {
    const parsed = new URL(trimmed);
    if (!parsed.pathname.replace(/\/+$/, "").endsWith("/v1")) {
      parsed.pathname = `${parsed.pathname.replace(/\/+$/, "")}/v1`;
    }
    return parsed.toString().replace(/\/+$/, "");
  } catch {
    return trimmed;
  }
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : "The connection could not be completed.";
}

export default function QuickProviderSetup({ onConfigured, onOpenSettings, onBusyChange }: Props) {
  const [catalog, setCatalog] = useState<ProviderCatalogEntry[]>([]);
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [catalogError, setCatalogError] = useState("");
  const [selectedType, setSelectedType] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [apiBaseUrl, setApiBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [models, setModels] = useState<ProviderModel[]>([]);
  const [modelName, setModelName] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [desktopAvailable, setDesktopAvailable] = useState(false);
  const [localRuntimeAvailable, setLocalRuntimeAvailable] = useState(false);
  const [codexMode, setCodexMode] = useState(false);
  const [codexAccountId, setCodexAccountId] = useState<string | null>(null);
  const [codexModels, setCodexModels] = useState<ElectronCodexModel[]>([]);
  const [codexModelName, setCodexModelName] = useState("");
  const [providerMenuOpen, setProviderMenuOpen] = useState(false);
  const providerPickerRef = useRef<HTMLDivElement>(null);
  const providerListboxId = useId();

  const resetProviderForm = useCallback((provider: ProviderCatalogEntry) => {
    setSelectedType(provider.provider_type);
    setDisplayName(provider.display_name);
    setApiBaseUrl(BASE_URLS[provider.provider_type] || "");
    setApiKey("");
    setModels([]);
    setModelName("");
    setError("");
    setSuccess("");
    setCodexMode(false);
  }, []);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (active) {
        const hasElectron = Boolean(window.electron?.isElectron);
        setDesktopAvailable(Boolean(hasElectron && window.electron?.codex));
        setLocalRuntimeAvailable(Boolean(hasElectron && window.electron?.localRuntime));
      }
    });
    void listSupportedProviderTypes()
      .then((items) => {
        if (!active) return;
        const options = items.filter(
          (item) =>
            item.provider_type !== "custom" &&
            item.supports_chat &&
            (item.auth_modes.includes("api_key") || item.auth_modes.includes("local_no_key")),
        );
        setCatalog(options);
        const first =
          options.find((item) => item.provider_type === "openai") ||
          options.find((item) => !item.is_local) ||
          options[0];
        if (first) resetProviderForm(first);
      })
      .catch((loadError: unknown) => {
        if (active) setCatalogError(describeError(loadError));
      })
      .finally(() => {
        if (active) setLoadingCatalog(false);
      });
    return () => {
      active = false;
    };
  }, [resetProviderForm]);

  useEffect(() => {
    if (!providerMenuOpen) return;
    const closeWhenOutside = (event: MouseEvent) => {
      if (!providerPickerRef.current?.contains(event.target as Node)) setProviderMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setProviderMenuOpen(false);
    };
    document.addEventListener("mousedown", closeWhenOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("mousedown", closeWhenOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [providerMenuOpen]);

  const selectedProvider = useMemo(
    () => catalog.find((item) => item.provider_type === selectedType) || null,
    [catalog, selectedType],
  );
  const isLocal = Boolean(selectedProvider?.is_local);
  const localRuntimeUnavailable = isLocal && !localRuntimeAvailable;
  const authMode = selectedProvider?.auth_modes.includes("local_no_key")
    ? "local_no_key"
    : "api_key";
  const canDiscover = Boolean(selectedProvider?.supports_model_listing);

  const discoverModels = async () => {
    if (!selectedProvider) return;
    if (localRuntimeUnavailable) {
      setError("LM Studio and Ollama connections are available only in the AverQel Desktop app.");
      return;
    }
    setDiscovering(true);
    setError("");
    setSuccess("");
    try {
      const items = await previewProviderModels({
        provider_type: selectedProvider.provider_type,
        api_base_url: normalizeBaseUrl(selectedProvider.provider_type, apiBaseUrl) || null,
        auth_mode: authMode,
        api_key: authMode === "api_key" ? apiKey.trim() || null : null,
        supports_chat: selectedProvider.supports_chat,
        supports_embeddings: selectedProvider.supports_embeddings,
        supports_reranking: selectedProvider.supports_reranking,
        supports_web_search: selectedProvider.supports_web_search,
        supports_model_listing: selectedProvider.supports_model_listing,
        ...(isLocal
          ? { metadata_json: { runtime_target: "desktop", protocol: "desktop_local_runtime" } }
          : {}),
      });
      const chatModels = items.filter(
        (item) => item.model_kind === "chat" || item.model_kind === "other",
      );
      setModels(chatModels);
      setModelName(chatModels[0]?.model_name || "");
      if (chatModels.length === 0)
        setError("No chat models were found. Check the connection and try again.");
    } catch (previewError) {
      setModels([]);
      setModelName("");
      setError(describeError(previewError));
    } finally {
      setDiscovering(false);
    }
  };

  const saveProvider = async () => {
    if (!selectedProvider) return;
    if (localRuntimeUnavailable) {
      setError("LM Studio and Ollama connections are available only in the AverQel Desktop app.");
      return;
    }
    if (!displayName.trim()) {
      setError("Enter a name for this connection.");
      return;
    }
    if (authMode === "api_key" && !apiKey.trim()) {
      setError("Enter an API key to continue.");
      return;
    }
    if (!modelName.trim()) {
      setError("Find and select a chat model before saving this connection.");
      return;
    }

    setSaving(true);
    onBusyChange(true);
    setError("");
    try {
      const created = await createProvider({
        provider_type: selectedProvider.provider_type,
        display_name: displayName.trim(),
        api_base_url: normalizeBaseUrl(selectedProvider.provider_type, apiBaseUrl) || null,
        auth_mode: authMode,
        api_key: authMode === "api_key" ? apiKey.trim() : null,
        enabled: true,
        is_local: selectedProvider.is_local,
        supports_chat: selectedProvider.supports_chat,
        supports_embeddings: selectedProvider.supports_embeddings,
        supports_reranking: selectedProvider.supports_reranking,
        supports_web_search: selectedProvider.supports_web_search,
        supports_model_listing: selectedProvider.supports_model_listing,
        supports_model_install: selectedProvider.supports_model_install,
        default_chat_model: modelName.trim(),
        ...(isLocal
          ? { metadata_json: { runtime_target: "desktop", protocol: "desktop_local_runtime" } }
          : {}),
      });
      setApiKey("");
      setSuccess(`${created.display_name} is connected with ${created.default_chat_model}.`);
      onConfigured(created.display_name);
    } catch (saveError) {
      setError(describeError(saveError));
    } finally {
      setSaving(false);
      onBusyChange(false);
    }
  };

  const saveCodexProvider = async () => {
    if (!codexAccountId || !codexModelName) {
      setError("Sign in and choose a Codex model before saving.");
      return;
    }
    setSaving(true);
    onBusyChange(true);
    setError("");
    try {
      const created = await createProvider({
        provider_type: "openai",
        display_name: "OpenAI Codex",
        auth_mode: "codex_desktop",
        api_base_url: null,
        enabled: true,
        is_local: false,
        supports_chat: true,
        supports_embeddings: false,
        supports_reranking: false,
        supports_web_search: false,
        supports_model_listing: true,
        supports_model_install: false,
        default_chat_model: codexModelName,
        metadata_json: {
          codex_desktop: {
            account_id: codexAccountId,
            models: codexModels.map((model) => ({
              id: model.id,
              name: model.name,
              ...(model.supportedReasoningEfforts
                ? {
                    supported_reasoning_efforts: model.supportedReasoningEfforts,
                    reasoning_effort_values: model.reasoningEffortValues,
                  }
                : {}),
            })),
          },
        },
      });
      setSuccess(`${created.display_name} is connected with ${created.default_chat_model}.`);
      onConfigured(created.display_name);
    } catch (saveError) {
      setError(describeError(saveError));
    } finally {
      setSaving(false);
      onBusyChange(false);
    }
  };

  if (loadingCatalog) {
    return (
      <div className="flex min-h-36 items-center justify-center gap-2 text-sm text-slate-400">
        <LoaderCircle size={16} className="animate-spin" /> Loading available providers…
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2" role="group" aria-label="AI connection method">
        <button
          type="button"
          aria-pressed={!codexMode}
          onClick={() => setCodexMode(false)}
          className={`rounded-lg border px-3 py-2 text-xs font-medium ${!codexMode ? "border-teal-300/40 bg-teal-300/10 text-teal-100" : "border-white/10 text-slate-400"}`}
        >
          API or local model
        </button>
        <button
          type="button"
          aria-pressed={codexMode}
          onClick={() => {
            setCodexMode(true);
            setError("");
            setSuccess("");
          }}
          className={`rounded-lg border px-3 py-2 text-xs font-medium ${codexMode ? "border-teal-300/40 bg-teal-300/10 text-teal-100" : "border-white/10 text-slate-400"}`}
        >
          ChatGPT / Codex
        </button>
      </div>

      {catalogError ? (
        <div
          className="rounded-xl border border-red-400/20 bg-red-400/5 p-3 text-sm text-red-200"
          role="alert"
        >
          Provider choices could not be loaded: {catalogError}
          <button type="button" onClick={onOpenSettings} className="ml-2 underline">
            Open provider settings
          </button>
        </div>
      ) : null}

      {codexMode ? (
        desktopAvailable ? (
          <div className="space-y-4">
            <OpenAICodexLoginPanel
              initialAccountId={null}
              onChange={(accountId, nextModels) => {
                setCodexAccountId(accountId);
                setCodexModels(nextModels);
                setCodexModelName((current) =>
                  nextModels.some((model) => model.id === current)
                    ? current
                    : nextModels[0]?.id || "",
                );
              }}
            />
            {codexModels.length ? (
              <label className="block space-y-2">
                <span className="text-sm font-medium text-slate-200">Default Codex model</span>
                <select
                  value={codexModelName}
                  onChange={(event) => setCodexModelName(event.target.value)}
                  className="h-10 w-full rounded-lg border border-white/10 bg-slate-950 px-3 text-sm text-slate-100"
                >
                  {codexModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            <button
              type="button"
              onClick={() => void saveCodexProvider()}
              disabled={saving || !codexAccountId || !codexModelName}
              className="inline-flex h-10 items-center gap-2 rounded-xl bg-teal-300 px-4 text-sm font-semibold text-slate-950 disabled:opacity-50"
            >
              {saving ? (
                <LoaderCircle size={15} className="animate-spin" />
              ) : (
                <KeyRound size={15} />
              )}
              Save Codex connection
            </button>
          </div>
        ) : (
          <div className="rounded-xl border border-white/10 bg-white/[0.025] p-4">
            <div className="flex items-start gap-3">
              <Laptop size={18} className="mt-0.5 shrink-0 text-teal-200" />
              <div>
                <p className="text-sm font-medium text-slate-100">Use ChatGPT or Codex CLI</p>
                <p className="mt-1 text-xs leading-5 text-slate-400">
                  Secure ChatGPT and Codex CLI sign-in is available in AverQel Desktop. API key
                  connections can be set up in this web app.
                </p>
                <button
                  type="button"
                  onClick={onOpenSettings}
                  className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-teal-200"
                >
                  Open provider settings <ArrowRight size={13} />
                </button>
              </div>
            </div>
          </div>
        )
      ) : catalog.length ? (
        <div className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="relative space-y-1.5" ref={providerPickerRef}>
              <span
                id={`${providerListboxId}-label`}
                className="text-xs font-medium text-slate-300"
              >
                Provider
              </span>
              <button
                type="button"
                aria-labelledby={`${providerListboxId}-label ${providerListboxId}-value`}
                aria-controls={providerListboxId}
                aria-expanded={providerMenuOpen}
                aria-haspopup="listbox"
                onClick={() => setProviderMenuOpen((open) => !open)}
                className="welcome-provider-trigger flex h-10 w-full items-center justify-between gap-3 rounded-xl px-3 text-left text-sm"
              >
                <span id={`${providerListboxId}-value`} className="truncate">
                  {selectedProvider?.display_name || "Choose a provider"}
                </span>
                <ChevronDown
                  size={16}
                  aria-hidden="true"
                  className={`shrink-0 transition-transform ${providerMenuOpen ? "rotate-180" : ""}`}
                />
              </button>
              {providerMenuOpen ? (
                <div
                  id={providerListboxId}
                  role="listbox"
                  aria-labelledby={`${providerListboxId}-label`}
                  className="welcome-provider-menu absolute z-30 mt-2 max-h-64 w-full min-w-[14rem] overflow-y-auto rounded-2xl p-1.5 shadow-2xl"
                >
                  {catalog.map((item) => {
                    const selected = item.provider_type === selectedType;
                    const unavailable = Boolean(item.is_local && !localRuntimeAvailable);
                    return (
                      <button
                        key={item.provider_type}
                        type="button"
                        role="option"
                        aria-selected={selected}
                        aria-disabled={unavailable}
                        disabled={unavailable}
                        onClick={() => {
                          if (unavailable) return;
                          resetProviderForm(item);
                          setProviderMenuOpen(false);
                        }}
                        className={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left text-sm transition ${selected ? "bg-teal-300/15 text-teal-100" : "text-slate-300 hover:bg-white/[0.07]"} ${unavailable ? "cursor-not-allowed text-slate-500 opacity-50 hover:bg-transparent" : ""}`}
                      >
                        <span className="truncate">
                          {item.display_name}
                          {unavailable ? " · Desktop app only" : ""}
                        </span>
                        {selected ? <Check size={15} aria-hidden="true" /> : null}
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>
            {!localRuntimeAvailable && catalog.some((item) => item.is_local) ? (
              <p className="col-span-full rounded-xl border border-slate-400/20 bg-slate-400/5 p-3 text-[11px] leading-5 text-slate-400">
                LM Studio and Ollama run on your computer through AverQel Desktop. Open or install
                the desktop app to configure them.
              </p>
            ) : null}
            <label className="space-y-1.5">
              <span className="text-xs font-medium text-slate-300">Connection name</span>
              <input
                value={displayName}
                maxLength={120}
                onChange={(event) => setDisplayName(event.target.value)}
                disabled={localRuntimeUnavailable}
                className="h-10 w-full rounded-lg border border-white/10 bg-slate-950 px-3 text-sm text-slate-100"
                placeholder="My AI provider"
              />
            </label>
          </div>

          {isLocal ? (
            <div
              className={`block space-y-1.5 ${localRuntimeUnavailable ? "rounded-xl border border-slate-400/20 bg-slate-400/5 p-4" : ""}`}
            >
              {localRuntimeUnavailable ? (
                <p className="mb-3 text-xs leading-5 text-slate-400">
                  LM Studio and Ollama are available only in AverQel Desktop. Open or install the
                  desktop app to connect to a model running on this computer.
                </p>
              ) : null}
              <label
                htmlFor="quick-provider-runtime-url"
                className="text-xs font-medium text-slate-300"
              >
                Runtime URL
              </label>
              <input
                id="quick-provider-runtime-url"
                type="url"
                value={apiBaseUrl}
                onChange={(event) => setApiBaseUrl(event.target.value)}
                disabled={localRuntimeUnavailable}
                className="h-10 w-full rounded-lg border border-white/10 bg-slate-950 px-3 text-sm text-slate-100"
                placeholder="http://localhost:11434"
              />
              {!localRuntimeUnavailable ? (
                <p className="text-[11px] leading-4 text-amber-200/80">
                  The desktop app connects to this runtime on the same computer through its local
                  WebSocket bridge.
                </p>
              ) : null}
            </div>
          ) : (
            <div className="block space-y-1.5">
              <label
                htmlFor="quick-provider-api-key"
                className="text-xs font-medium text-slate-300"
              >
                API key
              </label>
              <input
                id="quick-provider-api-key"
                type="password"
                autoComplete="new-password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                className="h-10 w-full rounded-lg border border-white/10 bg-slate-950 px-3 text-sm text-slate-100"
                placeholder="Paste your provider key"
              />
              <p className="text-[11px] leading-4 text-slate-500">
                Sent over the authenticated connection and stored by AverQel&apos;s encrypted
                provider credential store.
              </p>
            </div>
          )}

          {selectedProvider && !BASE_URLS[selectedProvider.provider_type] ? (
            <div className="block space-y-1.5">
              <label
                htmlFor="quick-provider-api-base-url"
                className="text-xs font-medium text-slate-300"
              >
                API base URL
              </label>
              <input
                id="quick-provider-api-base-url"
                type="url"
                value={apiBaseUrl}
                onChange={(event) => setApiBaseUrl(event.target.value)}
                disabled={localRuntimeUnavailable}
                className="h-10 w-full rounded-lg border border-white/10 bg-slate-950 px-3 text-sm text-slate-100"
                placeholder="https://api.example.com/v1"
              />
            </div>
          ) : null}

          {canDiscover ? (
            <div className="flex flex-wrap items-end gap-2">
              <button
                type="button"
                onClick={() => void discoverModels()}
                disabled={
                  localRuntimeUnavailable ||
                  discovering ||
                  (authMode === "api_key" && !apiKey.trim()) ||
                  !apiBaseUrl.trim()
                }
                className="inline-flex h-10 items-center gap-2 rounded-lg border border-white/10 px-3 text-xs font-medium text-slate-200 hover:bg-white/5 disabled:opacity-50"
              >
                {discovering ? (
                  <LoaderCircle size={14} className="animate-spin" />
                ) : (
                  <Search size={14} />
                )}
                Find chat models
              </button>
              {models.length ? (
                <label className="min-w-[180px] flex-1 space-y-1.5">
                  <span className="text-xs font-medium text-slate-300">Default chat model</span>
                  <select
                    value={modelName}
                    onChange={(event) => setModelName(event.target.value)}
                    disabled={localRuntimeUnavailable}
                    className="h-10 w-full rounded-lg border border-white/10 bg-slate-950 px-3 text-sm text-slate-100"
                  >
                    {models.map((model) => (
                      <option key={model.model_name} value={model.model_name}>
                        {model.display_name || model.model_name}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
            </div>
          ) : (
            <label className="block space-y-1.5">
              <span className="text-xs font-medium text-slate-300">Default chat model</span>
              <input
                value={modelName}
                onChange={(event) => setModelName(event.target.value)}
                disabled={localRuntimeUnavailable}
                className="h-10 w-full rounded-lg border border-white/10 bg-slate-950 px-3 text-sm text-slate-100"
                placeholder="Model name from your provider"
              />
            </label>
          )}

          <button
            type="button"
            onClick={() => void saveProvider()}
            disabled={
              saving ||
              localRuntimeUnavailable ||
              !selectedProvider ||
              (canDiscover && !models.length)
            }
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-teal-300 px-4 text-sm font-semibold text-slate-950 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? <LoaderCircle size={15} className="animate-spin" /> : <KeyRound size={15} />}
            Save connection
          </button>
        </div>
      ) : (
        <div className="rounded-xl border border-white/10 bg-white/[0.025] p-4 text-sm text-slate-400">
          This account has no provider types available for quick setup.
        </div>
      )}

      {error ? (
        <p
          role="alert"
          className="rounded-lg border border-red-400/20 bg-red-400/5 p-3 text-xs leading-5 text-red-200"
        >
          {error}
        </p>
      ) : null}
      {success ? (
        <p
          role="status"
          className="flex items-start gap-2 rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-3 text-xs leading-5 text-emerald-200"
        >
          <CheckCircle2 size={15} className="mt-0.5 shrink-0" /> {success}
        </p>
      ) : null}

      <button
        type="button"
        onClick={onOpenSettings}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-400 underline decoration-white/20 underline-offset-4 hover:text-white"
      >
        More provider options and assignments <ArrowRight size={13} />
      </button>
    </div>
  );
}
