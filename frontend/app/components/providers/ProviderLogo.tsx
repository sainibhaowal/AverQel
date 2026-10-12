import Image from "next/image";
import { Cable } from "lucide-react";

export type ProviderLogoDefinition =
  | { kind: "asset"; src: string; appearance: "brand" | "monochrome" }
  | { kind: "wordmark"; text: string }
  | { kind: "endpoint" };

/**
 * Provider marks are local SVGs so they also render in offline desktop builds.
 * Groq and Tavily use plain text marks because their published brand terms
 * restrict logo use in application interfaces without permission.
 */
export const providerLogoRegistry: Record<string, ProviderLogoDefinition> = {
  anthropic: { kind: "asset", src: "/providers/anthropic.svg", appearance: "monochrome" },
  cline: { kind: "asset", src: "/providers/cline.svg", appearance: "monochrome" },
  cohere: { kind: "asset", src: "/providers/cohere-color.svg", appearance: "brand" },
  deepseek: { kind: "asset", src: "/providers/deepseek-color.svg", appearance: "brand" },
  google: { kind: "asset", src: "/providers/gemini-color.svg", appearance: "brand" },
  groq: { kind: "wordmark", text: "GROQ" },
  "groq-openai-compatible": { kind: "wordmark", text: "GROQ" },
  lmstudio: { kind: "asset", src: "/providers/lmstudio.svg", appearance: "monochrome" },
  manus: { kind: "asset", src: "/providers/manus.svg", appearance: "monochrome" },
  meta: { kind: "asset", src: "/providers/metaai-color.svg", appearance: "brand" },
  mistral: { kind: "asset", src: "/providers/mistral-color.svg", appearance: "brand" },
  moonshot: { kind: "asset", src: "/providers/kimi-color.svg", appearance: "brand" },
  "nvidia-nim": { kind: "asset", src: "/providers/nvidia-color.svg", appearance: "brand" },
  ollama: { kind: "asset", src: "/providers/ollama.svg", appearance: "monochrome" },
  openai: { kind: "asset", src: "/providers/openai.svg", appearance: "monochrome" },
  "opencode-zen": { kind: "asset", src: "/providers/opencode.svg", appearance: "monochrome" },
  openrouter: { kind: "asset", src: "/providers/openrouter-color.svg", appearance: "brand" },
  "sentence-transformers": { kind: "asset", src: "/logo_icon.svg", appearance: "brand" },
  searxng: { kind: "asset", src: "/providers/searxng-color.svg", appearance: "brand" },
  tavily: { kind: "wordmark", text: "TAVILY" },
  zai: { kind: "asset", src: "/providers/zai.svg", appearance: "monochrome" },
  custom: { kind: "endpoint" },
};

export function getProviderLogoDefinition(
  providerType: string | null | undefined,
): ProviderLogoDefinition {
  const normalizedType = providerType?.trim().toLowerCase() ?? "";
  return providerLogoRegistry[normalizedType] ?? { kind: "endpoint" };
}

interface ProviderLogoProps {
  providerType: string | null | undefined;
  size?: number;
  className?: string;
}

export default function ProviderLogo({
  providerType,
  size = 20,
  className = "",
}: ProviderLogoProps) {
  const definition = getProviderLogoDefinition(providerType);
  const logoSize = { width: size, height: size };

  if (definition.kind === "asset") {
    return (
      <Image
        src={definition.src}
        alt=""
        aria-hidden="true"
        width={size}
        height={size}
        unoptimized
        className={`block shrink-0 object-contain ${
          definition.appearance === "monochrome" ? "dark:brightness-0 dark:invert" : ""
        } ${className}`}
      />
    );
  }

  if (definition.kind === "wordmark") {
    const fontSize = Math.max(5, Math.min(8, Math.floor((size / definition.text.length) * 1.7)));
    return (
      <span
        aria-hidden="true"
        className={`inline-flex shrink-0 items-center justify-center overflow-hidden font-mono leading-none font-black tracking-[-0.08em] ${className}`}
        style={{ ...logoSize, fontSize }}
      >
        {definition.text}
      </span>
    );
  }

  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center ${className}`}
      style={logoSize}
    >
      <Cable size={Math.max(12, Math.round(size * 0.72))} strokeWidth={1.8} />
    </span>
  );
}
