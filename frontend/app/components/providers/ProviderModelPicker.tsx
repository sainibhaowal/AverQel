"use client";

import { useId } from "react";
import type { ProviderModel } from "@/lib/providers-api";
import ProviderDropdown from "@/app/components/providers/ProviderDropdown";

type ProviderModelKind = "chat" | "embedding" | "reranker" | "other";

function flattenSearchMetadata(value: unknown, depth = 0): string[] {
  if (depth > 6 || value === null || value === undefined) return [];
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return [String(value)];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => flattenSearchMetadata(item, depth + 1));
  }
  if (typeof value === "object") {
    return Object.entries(value).flatMap(([key, item]) => [
      key,
      ...flattenSearchMetadata(item, depth + 1),
    ]);
  }
  return [];
}

interface ProviderModelPickerProps {
  label: string;
  value: string;
  models: ProviderModel[];
  onChange: (value: string) => void;
  kinds?: ("chat" | "embedding" | "reranker" | "other")[];
  allowClear?: boolean;
  clearLabel?: string;
  placeholder?: string;
  disabled?: boolean;
  helperText?: string;
  allowCustomValue?: boolean;
}

/**
 * Service-aware model selector for intelligent routing.
 * Optimized for high-density setup cards with clear, service-specific placeholders.
 */
export default function ProviderModelPicker({
  label,
  value,
  models,
  onChange,
  kinds = [],
  allowClear = false,
  clearLabel = "Not Assigned",
  placeholder,
  disabled = false,
  helperText,
  allowCustomValue = false,
}: ProviderModelPickerProps) {
  const inputId = useId();

  // Scoped list filtering
  const filtered =
    kinds.length === 0
      ? models
      : models.filter((m) => kinds.includes(m.model_kind as ProviderModelKind));
  // Discovery endpoints occasionally return aliases as duplicate descriptors.
  // A provider/model/kind is one selectable target, so never render it twice.
  const uniqueModels = Array.from(
    new Map(
      filtered.map((model) => [`${model.model_kind}\u0000${model.model_name}`, model] as const),
    ).values(),
  );

  // Determine placeholder based on the primary kind
  const getPlaceholder = () => {
    if (kinds.includes("chat")) return "Select chat model";
    if (kinds.includes("embedding")) return "Select embedding interface";
    if (kinds.includes("reranker")) return "Select reranking engine";
    return "Choose model...";
  };

  /**
   * Compact label formatting to reduce setup card noise.
   */
  function formatHint(model: ProviderModel): string | undefined {
    const parts: string[] = [];
    const runtime =
      typeof model.capabilities_json.runtime === "string" ? model.capabilities_json.runtime : null;
    const quantization =
      typeof model.capabilities_json.quantization === "string"
        ? model.capabilities_json.quantization
        : null;

    if (runtime) parts.push(runtime);
    if (quantization) parts.push(quantization);
    if (model.context_window) parts.push(`${Math.floor(model.context_window / 1024)}k`);

    return parts.length > 0 ? parts.join(" · ") : undefined;
  }

  return (
    <div className="flex flex-col space-y-2">
      <ProviderDropdown
        label={label}
        value={value}
        onChange={onChange}
        placeholder={placeholder || getPlaceholder()}
        name={inputId}
        disabled={disabled}
        allowCustomValue={allowCustomValue}
        options={[
          ...(allowClear
            ? [
                {
                  value: "",
                  label: clearLabel,
                  hint: "Uses generic runtime fallback if available",
                },
              ]
            : []),
          ...uniqueModels.map((m) => ({
            value: m.model_name,
            label: m.display_name || m.model_name,
            hint: formatHint(m),
            searchText: flattenSearchMetadata(m).join(" ").slice(0, 4096),
          })),
        ]}
        searchable
        searchPlaceholder="Search by model name, ID, context, or capability"
      />
      {helperText && (
        <p className="text-foreground/35 px-1 text-[10px] leading-relaxed font-medium italic">
          {helperText}
        </p>
      )}
    </div>
  );
}
