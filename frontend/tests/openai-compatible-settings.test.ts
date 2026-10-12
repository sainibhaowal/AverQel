import { createElement } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import OpenAICompatibleSettingsPanel, {
  buildOpenAICompatibleMetadata,
  DEFAULT_OPENAI_COMPATIBLE_SETTINGS,
  normalizeConfiguredReasoningEffort,
  readOpenAICompatibleSettings,
  type OpenAICompatibleFormSettings,
  type ReasoningLevel,
} from "../app/components/providers/OpenAICompatibleSettingsPanel";

describe("OpenAI-compatible settings persistence", () => {
  it("round-trips endpoint routes, auth, request fields, and explicit reasoning levels", () => {
    const settings = {
      ...DEFAULT_OPENAI_COMPATIBLE_SETTINGS,
      api_mode: "responses" as const,
      responses_path: "/v2/responses",
      models_path: "",
      auth_header_name: "X-API-Key",
      auth_scheme: "raw" as const,
      send_max_tokens: false,
      send_temperature: false,
      send_embedding_dimensions: true,
      reasoning: {
        ...DEFAULT_OPENAI_COMPATIBLE_SETTINGS.reasoning,
        supported_efforts: ["low", "extreme_high"] as ReasoningLevel[],
        effort_parameter: "reasoning.effort",
        effort_values: {
          ...DEFAULT_OPENAI_COMPATIBLE_SETTINGS.reasoning.effort_values,
          low: "minimal",
          extreme_high: "max",
        },
        toggle_parameter: "enable_thinking",
        toggle_disabled_value: "false",
      },
    };

    const metadata = buildOpenAICompatibleMetadata({ note: "keep" }, settings);
    const roundTrip = readOpenAICompatibleSettings(metadata);

    expect(metadata.note).toBe("keep");
    expect(metadata.supported_reasoning_efforts).toEqual(["low", "extreme_high"]);
    expect(metadata.openai_compatible).toMatchObject({
      api_mode: "responses",
      responses_path: "/v2/responses",
      models_path: null,
      auth_header_name: "X-API-Key",
      auth_scheme: "raw",
      send_max_tokens: false,
      send_temperature: false,
      send_embedding_dimensions: true,
    });
    expect(roundTrip.reasoning.supported_efforts).toEqual(["low", "extreme_high"]);
    expect(roundTrip.reasoning.effort_parameter).toBe("reasoning.effort");
    expect(roundTrip.reasoning.toggle_disabled_value).toBe("false");
    expect(roundTrip.models_path).toBe("");
  });

  it("keeps conservative defaults when no endpoint settings exist", () => {
    expect(readOpenAICompatibleSettings(null)).toEqual(DEFAULT_OPENAI_COMPATIBLE_SETTINGS);
  });

  it("saves native effort values only for levels enabled for the endpoint", () => {
    const metadata = buildOpenAICompatibleMetadata(null, DEFAULT_OPENAI_COMPATIBLE_SETTINGS);
    const endpoint = metadata.openai_compatible as {
      reasoning: { effort_values: Record<string, string> };
    };

    expect(endpoint.reasoning.effort_values).toEqual({});
  });

  it("preserves custom model-advertised levels and exact native values", () => {
    const metadata = {
      openai_compatible: {
        reasoning: {
          supported_efforts: ["minimal", "ultra", "tier-5"],
          effort_parameter: "reasoning.effort",
          effort_values: {
            minimal: "minimal",
            ultra: "ultra",
            tier_5: "vendor-tier-five",
          },
        },
      },
    };

    const settings = readOpenAICompatibleSettings(metadata);
    const roundTrip = readOpenAICompatibleSettings(buildOpenAICompatibleMetadata(null, settings));

    expect(settings.reasoning.supported_efforts).toEqual(["minimal", "ultra", "tier_5"]);
    expect(roundTrip.reasoning.effort_values.tier_5).toBe("vendor-tier-five");
    expect(normalizeConfiguredReasoningEffort("tier-5")).toBe("tier_5");
    expect(normalizeConfiguredReasoningEffort("not/a/level")).toBeNull();
  });

  it("adds a custom level and native mapping in one settings update", () => {
    const onChange = vi.fn<(value: OpenAICompatibleFormSettings) => void>();
    const settings: OpenAICompatibleFormSettings = {
      ...DEFAULT_OPENAI_COMPATIBLE_SETTINGS,
      reasoning: {
        ...DEFAULT_OPENAI_COMPATIBLE_SETTINGS.reasoning,
        effort_parameter: "reasoning.effort",
      },
    };
    render(createElement(OpenAICompatibleSettingsPanel, { value: settings, onChange }));

    fireEvent.change(
      screen.getByRole("textbox", { name: "Add a model-specific reasoning level" }),
      {
        target: { value: "tier-5" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: "Add level" }));

    const next = onChange.mock.calls[0]?.[0];
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(next?.reasoning.supported_efforts).toContain("tier_5");
    expect(next?.reasoning.effort_values.tier_5).toBe("tier_5");
  });

  it("keeps endpoint configuration within the supported 32-level bound", () => {
    const onChange = vi.fn<(value: OpenAICompatibleFormSettings) => void>();
    const settings: OpenAICompatibleFormSettings = {
      ...DEFAULT_OPENAI_COMPATIBLE_SETTINGS,
      reasoning: {
        ...DEFAULT_OPENAI_COMPATIBLE_SETTINGS.reasoning,
        supported_efforts: Array.from({ length: 32 }, (_, index) => `tier_${index}`),
        effort_parameter: "reasoning.effort",
      },
    };
    render(createElement(OpenAICompatibleSettingsPanel, { value: settings, onChange }));

    fireEvent.change(
      screen.getByRole("textbox", { name: "Add a model-specific reasoning level" }),
      { target: { value: "tier_32" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Add level" }));

    expect(screen.getByRole("alert")).toHaveTextContent("up to 32 reasoning levels");
    expect(onChange).not.toHaveBeenCalled();
  });
});
