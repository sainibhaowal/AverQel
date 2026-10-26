"use client";

import { useState } from "react";
import RoundedSelect from "@/app/components/ui/RoundedSelect";

export const REASONING_LEVELS = [
  "minimal",
  "low",
  "medium",
  "high",
  "very_high",
  "extreme_high",
  "ultra",
] as const;
export type ReasoningLevel = string;

const SAFE_REASONING_EFFORT = /^[a-z][a-z0-9_-]{0,19}$/;
const MAX_REASONING_LEVELS = 32;
const REASONING_EFFORT_ALIASES: Record<string, string> = {
  xhigh: "very_high",
  max: "extreme_high",
};

export function normalizeConfiguredReasoningEffort(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const native = value.trim().toLowerCase();
  if (!SAFE_REASONING_EFFORT.test(native)) return null;
  const normalized = REASONING_EFFORT_ALIASES[native] ?? native.replaceAll("-", "_");
  return SAFE_REASONING_EFFORT.test(normalized) ? normalized : null;
}

export type OpenAICompatibleFormSettings = {
  api_mode: "chat_completions" | "responses";
  chat_completions_path: string;
  responses_path: string;
  models_path: string;
  embeddings_path: string;
  auth_header_name: string;
  auth_scheme: "bearer" | "raw";
  max_tokens_parameter: "" | "max_tokens" | "max_completion_tokens" | "max_output_tokens";
  send_max_tokens: boolean;
  send_temperature: boolean;
  send_embedding_dimensions: boolean;
  reasoning: {
    supported_efforts: ReasoningLevel[];
    effort_parameter: string;
    effort_values: Record<string, string>;
    effort_off_value: string;
    toggle_parameter: string;
    toggle_enabled_value: string;
    toggle_disabled_value: string;
    expose_response_reasoning: boolean;
  };
};

const DEFAULT_REASONING_VALUES: Record<string, string> = {
  minimal: "minimal",
  low: "low",
  medium: "medium",
  high: "high",
  very_high: "xhigh",
  extreme_high: "max",
  ultra: "ultra",
};

export const DEFAULT_OPENAI_COMPATIBLE_SETTINGS: OpenAICompatibleFormSettings = {
  api_mode: "chat_completions",
  chat_completions_path: "/chat/completions",
  responses_path: "/responses",
  models_path: "/models",
  embeddings_path: "/embeddings",
  auth_header_name: "Authorization",
  auth_scheme: "bearer",
  max_tokens_parameter: "",
  send_max_tokens: true,
  send_temperature: true,
  send_embedding_dimensions: false,
  reasoning: {
    supported_efforts: [],
    effort_parameter: "",
    effort_values: DEFAULT_REASONING_VALUES,
    effort_off_value: "",
    toggle_parameter: "",
    toggle_enabled_value: "true",
    toggle_disabled_value: "false",
    expose_response_reasoning: true,
  },
};

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function formatConfiguredReasoningEffort(level: string): string {
  return level
    .replaceAll("-", "_")
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function isValidNativeEffortValue(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.trim().length > 0 &&
    value.trim().length <= 128 &&
    !/[\u0000-\u001f\u007f]/.test(value)
  );
}

export function readOpenAICompatibleSettings(
  metadata: Record<string, unknown> | null | undefined,
): OpenAICompatibleFormSettings {
  const stored = asRecord(metadata?.openai_compatible);
  const reasoning = asRecord(stored.reasoning);
  const storedValues = asRecord(reasoning.effort_values);
  const levels = Array.isArray(reasoning.supported_efforts)
    ? [
        ...new Set(
          reasoning.supported_efforts
            .map(normalizeConfiguredReasoningEffort)
            .filter((item): item is string => item !== null),
        ),
      ]
    : [];
  const text = (value: unknown, fallback: string) => (typeof value === "string" ? value : fallback);
  const effortValues = { ...DEFAULT_REASONING_VALUES };
  for (const [key, mapped] of Object.entries(storedValues)) {
    const level = normalizeConfiguredReasoningEffort(key);
    if (level && isValidNativeEffortValue(mapped)) effortValues[level] = mapped.trim();
  }
  for (const level of levels) {
    effortValues[level] ??= level;
  }
  return {
    ...DEFAULT_OPENAI_COMPATIBLE_SETTINGS,
    api_mode: stored.api_mode === "responses" ? "responses" : "chat_completions",
    chat_completions_path: text(
      stored.chat_completions_path,
      DEFAULT_OPENAI_COMPATIBLE_SETTINGS.chat_completions_path,
    ),
    responses_path: text(stored.responses_path, DEFAULT_OPENAI_COMPATIBLE_SETTINGS.responses_path),
    models_path:
      stored.models_path === null
        ? ""
        : text(stored.models_path, DEFAULT_OPENAI_COMPATIBLE_SETTINGS.models_path),
    embeddings_path:
      stored.embeddings_path === null
        ? ""
        : text(stored.embeddings_path, DEFAULT_OPENAI_COMPATIBLE_SETTINGS.embeddings_path),
    auth_header_name: text(
      stored.auth_header_name,
      DEFAULT_OPENAI_COMPATIBLE_SETTINGS.auth_header_name,
    ),
    auth_scheme: stored.auth_scheme === "raw" ? "raw" : "bearer",
    max_tokens_parameter: ["max_tokens", "max_completion_tokens", "max_output_tokens"].includes(
      String(stored.max_tokens_parameter),
    )
      ? (stored.max_tokens_parameter as OpenAICompatibleFormSettings["max_tokens_parameter"])
      : "",
    send_max_tokens:
      typeof stored.send_max_tokens === "boolean"
        ? stored.send_max_tokens
        : DEFAULT_OPENAI_COMPATIBLE_SETTINGS.send_max_tokens,
    send_temperature:
      typeof stored.send_temperature === "boolean"
        ? stored.send_temperature
        : DEFAULT_OPENAI_COMPATIBLE_SETTINGS.send_temperature,
    send_embedding_dimensions:
      typeof stored.send_embedding_dimensions === "boolean"
        ? stored.send_embedding_dimensions
        : DEFAULT_OPENAI_COMPATIBLE_SETTINGS.send_embedding_dimensions,
    reasoning: {
      supported_efforts: levels,
      effort_parameter: text(reasoning.effort_parameter, ""),
      effort_values: effortValues,
      effort_off_value: text(reasoning.effort_off_value, ""),
      toggle_parameter: text(reasoning.toggle_parameter, ""),
      toggle_enabled_value: String(reasoning.toggle_enabled_value ?? "true"),
      toggle_disabled_value: String(reasoning.toggle_disabled_value ?? "false"),
      expose_response_reasoning:
        typeof reasoning.expose_response_reasoning === "boolean"
          ? reasoning.expose_response_reasoning
          : true,
    },
  };
}

function parseToggleValue(value: string): boolean | string {
  if (value === "true") return true;
  if (value === "false") return false;
  return value;
}

export function buildOpenAICompatibleMetadata(
  metadata: Record<string, unknown> | null | undefined,
  settings: OpenAICompatibleFormSettings,
): Record<string, unknown> {
  const enabledEffortValues = Object.fromEntries(
    settings.reasoning.supported_efforts.map((effort) => [
      effort,
      settings.reasoning.effort_values[effort] ?? effort,
    ]),
  );
  return {
    ...asRecord(metadata),
    supported_reasoning_efforts: settings.reasoning.supported_efforts,
    openai_compatible: {
      api_mode: settings.api_mode,
      chat_completions_path: settings.chat_completions_path.trim() || "/chat/completions",
      responses_path: settings.responses_path.trim() || "/responses",
      models_path: settings.models_path.trim() || null,
      embeddings_path: settings.embeddings_path.trim() || null,
      auth_header_name: settings.auth_header_name.trim() || "Authorization",
      auth_scheme: settings.auth_scheme,
      max_tokens_parameter: settings.max_tokens_parameter || null,
      send_max_tokens: settings.send_max_tokens,
      send_temperature: settings.send_temperature,
      send_embedding_dimensions: settings.send_embedding_dimensions,
      reasoning: {
        supported_efforts: settings.reasoning.supported_efforts,
        effort_parameter: settings.reasoning.effort_parameter.trim() || null,
        effort_values: enabledEffortValues,
        effort_off_value: settings.reasoning.effort_off_value.trim() || null,
        toggle_parameter: settings.reasoning.toggle_parameter.trim() || null,
        toggle_enabled_value: parseToggleValue(settings.reasoning.toggle_enabled_value),
        toggle_disabled_value: parseToggleValue(settings.reasoning.toggle_disabled_value),
        expose_response_reasoning: settings.reasoning.expose_response_reasoning,
      },
    },
  };
}

function Field({
  label,
  value,
  onChange,
  placeholder,
  help,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  help?: string;
}) {
  return (
    <label className="space-y-1.5">
      <span className="text-muted-foreground/70 block font-mono text-[9px] font-bold tracking-[0.16em] uppercase">
        {label}
      </span>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="border-glass-border bg-surface-1 text-foreground placeholder:text-muted-foreground/35 h-9 w-full rounded-lg border px-3 text-xs outline-none focus:border-teal-500/50"
      />
      {help ? <span className="text-muted-foreground/60 block text-[10px]">{help}</span> : null}
    </label>
  );
}

function Checkbox({
  checked,
  label,
  onChange,
  disabled = false,
}: {
  checked: boolean;
  label: string;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <label className={`flex items-center gap-2 text-xs ${disabled ? "opacity-40" : ""}`}>
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(event) => onChange(event.target.checked)}
        className="accent-teal-500"
      />
      <span>{label}</span>
    </label>
  );
}

export default function OpenAICompatibleSettingsPanel({
  value,
  onChange,
}: {
  value: OpenAICompatibleFormSettings;
  onChange: (value: OpenAICompatibleFormSettings) => void;
}) {
  const [newReasoningEffort, setNewReasoningEffort] = useState("");
  const [reasoningEffortError, setReasoningEffortError] = useState("");
  const update = (changes: Partial<OpenAICompatibleFormSettings>) =>
    onChange({ ...value, ...changes });
  const updateReasoning = (changes: Partial<OpenAICompatibleFormSettings["reasoning"]>) =>
    onChange({ ...value, reasoning: { ...value.reasoning, ...changes } });
  const handleModeChange = (apiMode: string) => {
    update({ api_mode: apiMode as OpenAICompatibleFormSettings["api_mode"] });
  };
  const setSupportedEfforts = (next: ReasoningLevel[]) => {
    const builtInOrder = new Map<string, number>(
      REASONING_LEVELS.map((item, index) => [item, index]),
    );
    const supportedEfforts = [...new Set(next)].sort(
      (left, right) =>
        (builtInOrder.get(left) ?? REASONING_LEVELS.length) -
          (builtInOrder.get(right) ?? REASONING_LEVELS.length) || left.localeCompare(right),
    );
    const effortValues = { ...value.reasoning.effort_values };
    for (const effort of supportedEfforts) effortValues[effort] ??= effort;
    updateReasoning({ supported_efforts: supportedEfforts, effort_values: effortValues });
  };
  const toggleEffort = (level: ReasoningLevel, checked: boolean) => {
    const next = checked
      ? [...value.reasoning.supported_efforts, level]
      : value.reasoning.supported_efforts.filter((item) => item !== level);
    setSupportedEfforts(next);
  };
  const addReasoningEffort = () => {
    const level = normalizeConfiguredReasoningEffort(newReasoningEffort);
    if (!level) {
      setReasoningEffortError("Use letters, numbers, underscores, or hyphens for the model level.");
      return;
    }
    if (value.reasoning.supported_efforts.includes(level)) {
      setReasoningEffortError("That reasoning level is already listed.");
      return;
    }
    if (value.reasoning.supported_efforts.length >= MAX_REASONING_LEVELS) {
      setReasoningEffortError("This endpoint can define up to 32 reasoning levels.");
      return;
    }
    setReasoningEffortError("");
    setNewReasoningEffort("");
    setSupportedEfforts([...value.reasoning.supported_efforts, level]);
  };

  return (
    <details className="theme-panel-muted rounded-xl border border-white/10 p-4">
      <summary className="cursor-pointer text-xs font-bold">
        Advanced OpenAI-compatible settings
      </summary>
      <p className="text-muted-foreground mt-2 text-[11px] leading-relaxed">
        Configure the endpoint dialect explicitly. Model names alone never enable vendor-specific
        reasoning fields for this connection.
      </p>

      <div className="mt-4 space-y-5">
        <section className="space-y-3">
          <h3 className="font-mono text-[10px] font-bold tracking-widest uppercase">
            Protocol and routes
          </h3>
          <label className="space-y-1.5">
            <span className="text-muted-foreground/70 block font-mono text-[9px] font-bold tracking-[0.16em] uppercase">
              API protocol
            </span>
            <RoundedSelect
              label="API protocol"
              value={value.api_mode}
              onChange={handleModeChange}
              options={[
                { value: "chat_completions", label: "Chat Completions" },
                { value: "responses", label: "Responses" },
              ]}
              className="w-full"
              triggerClassName="h-9 w-full"
            />
          </label>
          <div className="grid gap-3 md:grid-cols-2">
            {value.api_mode === "chat_completions" ? (
              <Field
                label="Chat route"
                value={value.chat_completions_path}
                onChange={(chat_completions_path) => update({ chat_completions_path })}
                placeholder="/chat/completions"
              />
            ) : (
              <Field
                label="Responses route"
                value={value.responses_path}
                onChange={(responses_path) => update({ responses_path })}
                placeholder="/responses"
              />
            )}
            <Field
              label="Models route (blank disables discovery)"
              value={value.models_path}
              onChange={(models_path) => update({ models_path })}
              placeholder="/models"
            />
            <Field
              label="Embeddings route (blank disables embeddings)"
              value={value.embeddings_path}
              onChange={(embeddings_path) => update({ embeddings_path })}
              placeholder="/embeddings"
            />
            <label className="space-y-1.5">
              <span className="text-muted-foreground/70 block font-mono text-[9px] font-bold tracking-[0.16em] uppercase">
                Output token field
              </span>
              <RoundedSelect
                label="Output token field"
                value={value.max_tokens_parameter}
                onChange={(nextValue) =>
                  update({
                    max_tokens_parameter:
                      nextValue as OpenAICompatibleFormSettings["max_tokens_parameter"],
                  })
                }
                options={[
                  { value: "", label: "Protocol default" },
                  { value: "max_tokens", label: "max_tokens" },
                  { value: "max_completion_tokens", label: "max_completion_tokens" },
                  { value: "max_output_tokens", label: "max_output_tokens" },
                ]}
                className="w-full"
                triggerClassName="h-9 w-full"
              />
            </label>
          </div>
          <Checkbox
            checked={value.send_max_tokens}
            label="Send output-token limit"
            onChange={(send_max_tokens) => update({ send_max_tokens })}
          />
          <Checkbox
            checked={value.send_temperature}
            label="Send temperature"
            onChange={(send_temperature) => update({ send_temperature })}
          />
          <Checkbox
            checked={value.send_embedding_dimensions}
            label="Send dimensions to the embeddings route"
            onChange={(send_embedding_dimensions) => update({ send_embedding_dimensions })}
          />
        </section>

        <section className="space-y-3 border-t border-white/10 pt-4">
          <h3 className="font-mono text-[10px] font-bold tracking-widest uppercase">
            Authentication
          </h3>
          <div className="grid gap-3 md:grid-cols-2">
            <Field
              label="API key header name"
              value={value.auth_header_name}
              onChange={(auth_header_name) => update({ auth_header_name })}
              placeholder="Authorization"
              help="The API key remains encrypted in AverQel; this only changes its header name."
            />
            <label className="space-y-1.5">
              <span className="text-muted-foreground/70 block font-mono text-[9px] font-bold tracking-[0.16em] uppercase">
                API key format
              </span>
              <RoundedSelect
                label="API key format"
                value={value.auth_scheme}
                onChange={(nextValue) =>
                  update({ auth_scheme: nextValue === "raw" ? "raw" : "bearer" })
                }
                options={[
                  { value: "bearer", label: "Bearer <key>" },
                  { value: "raw", label: "Raw key value" },
                ]}
                className="w-full"
                triggerClassName="h-9 w-full"
              />
            </label>
          </div>
        </section>

        <section className="space-y-3 border-t border-white/10 pt-4">
          <h3 className="font-mono text-[10px] font-bold tracking-widest uppercase">
            Reasoning controls
          </h3>
          <p className="text-muted-foreground text-[10px] leading-relaxed">
            Set only fields your endpoint documents. Off sends the disabled value when a toggle is
            configured; otherwise it omits reasoning controls and the model may follow its own
            default.
          </p>
          <div className="grid gap-3 md:grid-cols-2">
            <Field
              label="Effort field path"
              value={value.reasoning.effort_parameter}
              onChange={(effort_parameter) => updateReasoning({ effort_parameter })}
              placeholder={value.api_mode === "responses" ? "reasoning.effort" : "reasoning_effort"}
              help="Dotted paths create nested JSON objects, for example reasoning.effort."
            />
            <Field
              label="Thinking toggle field path"
              value={value.reasoning.toggle_parameter}
              onChange={(toggle_parameter) => updateReasoning({ toggle_parameter })}
              placeholder="enable_thinking"
            />
            <Field
              label="Enabled value"
              value={value.reasoning.toggle_enabled_value}
              onChange={(toggle_enabled_value) => updateReasoning({ toggle_enabled_value })}
              placeholder="true"
            />
            <Field
              label="Disabled value (Think Off)"
              value={value.reasoning.toggle_disabled_value}
              onChange={(toggle_disabled_value) => updateReasoning({ toggle_disabled_value })}
              placeholder="false"
            />
            <Field
              label="Effort field value when Off (optional)"
              value={value.reasoning.effort_off_value}
              onChange={(effort_off_value) => updateReasoning({ effort_off_value })}
              placeholder="none"
            />
          </div>
          <div className="space-y-2">
            <p className="text-muted-foreground text-[10px] font-bold">
              Levels supported by this model
            </p>
            <div className="flex flex-wrap gap-x-4 gap-y-2">
              {[...new Set([...REASONING_LEVELS, ...value.reasoning.supported_efforts])].map(
                (level) => (
                  <Checkbox
                    key={level}
                    checked={value.reasoning.supported_efforts.includes(level)}
                    label={formatConfiguredReasoningEffort(level)}
                    disabled={!value.reasoning.effort_parameter.trim()}
                    onChange={(checked) => toggleEffort(level, checked)}
                  />
                ),
              )}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input
                aria-label="Add a model-specific reasoning level"
                value={newReasoningEffort}
                onChange={(event) => setNewReasoningEffort(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    addReasoningEffort();
                  }
                }}
                maxLength={20}
                placeholder="e.g. tier_5"
                className="theme-input h-8 min-w-0 flex-1 rounded-md border px-2 text-xs"
              />
              <button
                type="button"
                onClick={addReasoningEffort}
                disabled={!value.reasoning.effort_parameter.trim() || !newReasoningEffort.trim()}
                className="h-8 rounded-md border border-white/15 px-3 text-xs disabled:cursor-not-allowed disabled:opacity-50"
              >
                Add level
              </button>
            </div>
            {reasoningEffortError ? (
              <p role="alert" className="text-xs text-red-400">
                {reasoningEffortError}
              </p>
            ) : null}
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {value.reasoning.supported_efforts.map((level) => (
                <Field
                  key={level}
                  label={`${formatConfiguredReasoningEffort(level)} value`}
                  value={value.reasoning.effort_values[level]}
                  onChange={(mappedValue) =>
                    updateReasoning({
                      effort_values: { ...value.reasoning.effort_values, [level]: mappedValue },
                    })
                  }
                />
              ))}
            </div>
          </div>
          <Checkbox
            checked={value.reasoning.expose_response_reasoning}
            label="Display reasoning text returned by the endpoint"
            onChange={(expose_response_reasoning) => updateReasoning({ expose_response_reasoning })}
          />
        </section>
      </div>
    </details>
  );
}
