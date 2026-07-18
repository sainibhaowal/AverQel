"use client";

import { Cpu, Database, Server } from "lucide-react";
import type { ReactNode } from "react";

export default function ProviderLocalRuntimeHelp({ providerType }: { providerType: string }) {
  if (!providerType) return null;

  if (providerType === "ollama") {
    return (
      <RuntimeHelpCard
        icon={<Server size={16} />}
        title="Ollama local runtime"
        items={[
          "Start Ollama locally.",
          "Use the default base URL `http://127.0.0.1:11434` unless you changed it.",
          "Save the provider, then refresh models or pull a model from the UI through Ollama's official API.",
          "Choose separate chat and embedding defaults where the runtime/model supports them.",
        ]}
      />
    );
  }

  if (providerType === "lmstudio") {
    return (
      <RuntimeHelpCard
        icon={<Cpu size={16} />}
        title="LM Studio local runtime"
        items={[
          "Start LM Studio and enable the OpenAI-compatible server.",
          "Use a base URL the AverQel backend can reach: `http://127.0.0.1:1234/v1` only when both run on the same machine, `http://host.docker.internal:1234/v1` when Docker shares that host, or a public/VPN/reverse-proxied URL for remote hosted AverQel.",
          "Load a model inside LM Studio, then refresh models from AverQel.",
          "AverQel can discover and select models exposed by LM Studio, but it does not install or download LM Studio models directly.",
        ]}
      />
    );
  }

  if (providerType === "sentence-transformers") {
    return (
      <RuntimeHelpCard
        icon={<Database size={16} />}
        title="AverQel server embeddings"
        items={[
          "This runtime is built into the AverQel backend, so there is no external server URL to manage.",
          "Choose one of the available embedding models and save it as the default retrieval model.",
          "Document uploads and query retrieval will use the selected embedding model automatically.",
          "Switching the embedding model later is supported, but already-indexed documents may need re-embedding to fully align.",
        ]}
      />
    );
  }

  return (
    <RuntimeHelpCard
      icon={<Database size={16} />}
      title="Provider guidance"
      items={[
        "Choose a base URL that the AverQel backend can reach.",
        "Save and test the provider before assigning it to chat or embeddings.",
        "Refresh models when the provider supports listing or discovery.",
      ]}
    />
  );
}

function RuntimeHelpCard({
  icon,
  title,
  items,
}: {
  icon: ReactNode;
  title: string;
  items: string[];
}) {
  return (
    <div className="theme-panel text-muted-foreground rounded-[1.6rem] p-5 text-sm">
      <div className="text-foreground mb-4 flex items-center gap-3">
        <div className="theme-chip text-accent-cyan flex h-10 w-10 items-center justify-center rounded-[1rem]">
          {icon}
        </div>
        <span className="font-semibold">{title}</span>
      </div>
      <ol className="space-y-2 pl-5">
        {items.map((item) => (
          <li key={item} className="list-decimal leading-6">
            {item}
          </li>
        ))}
      </ol>
    </div>
  );
}
