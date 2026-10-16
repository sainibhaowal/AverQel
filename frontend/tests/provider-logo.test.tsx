import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import ProviderDropdown from "../app/components/providers/ProviderDropdown";
import ProviderLogo, {
  getProviderLogoDefinition,
  providerLogoRegistry,
} from "../app/components/providers/ProviderLogo";

const supportedProviderTypes = [
  "openai",
  "deepseek",
  "groq",
  "groq-openai-compatible",
  "mistral",
  "meta",
  "cline",
  "moonshot",
  "zai",
  "nvidia-nim",
  "manus",
  "custom",
  "lmstudio",
  "ollama",
  "anthropic",
  "google",
  "opencode-zen",
  "cohere",
  "sentence-transformers",
  "tavily",
  "searxng",
  "openrouter",
];

describe("provider logos", () => {
  it("maps every supported provider type to a local mark or an explicit neutral treatment", () => {
    for (const providerType of supportedProviderTypes) {
      expect(providerLogoRegistry, providerType).toHaveProperty(providerType);
    }

    for (const [providerType, definition] of Object.entries(providerLogoRegistry)) {
      if (definition.kind === "asset") {
        expect(definition.src, providerType).toMatch(/^\/(providers\/|brand\/AverQel_Icon\.svg$)/);
        expect(
          existsSync(resolve(process.cwd(), "public", definition.src.slice(1))),
          providerType,
        ).toBe(true);
      }
    }

    expect(getProviderLogoDefinition("custom").kind).toBe("endpoint");
    expect(getProviderLogoDefinition("groq")).toEqual({ kind: "wordmark", text: "GROQ" });
    expect(getProviderLogoDefinition("tavily")).toEqual({ kind: "wordmark", text: "TAVILY" });
  });

  it("renders a recognizable local logo instead of a numeric or first-letter placeholder", () => {
    const { container } = render(
      <div>
        <ProviderLogo providerType="openai" size={20} />
        <ProviderLogo providerType="custom" size={20} />
        <ProviderLogo providerType="groq" size={20} />
      </div>,
    );

    expect(container.querySelector('img[src="/providers/openai.svg"]')).toBeInTheDocument();
    expect(container.querySelector("svg")).toBeInTheDocument();
    expect(container).toHaveTextContent("GROQ");
    expect(container).not.toHaveTextContent("0");
  });

  it("keeps provider logos visible in the provider assignment dropdown", () => {
    const onChange = vi.fn();

    render(
      <ProviderDropdown
        label="Provider"
        value="openai-id"
        onChange={onChange}
        options={[
          {
            value: "openai-id",
            label: "OpenAI API",
            hint: "openai",
            icon: <ProviderLogo providerType="openai" size={18} />,
          },
        ]}
      />,
    );

    expect(document.querySelector('img[src="/providers/openai.svg"]')).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /OpenAI API/i }));
    expect(document.querySelector('[role="listbox"] [role="option"]')).toHaveTextContent(
      "OpenAI API",
    );
    expect(document.querySelectorAll('img[src="/providers/openai.svg"]').length).toBeGreaterThan(1);
  });
});
