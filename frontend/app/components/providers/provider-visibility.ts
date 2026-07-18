import type { ProviderConfig } from "@/lib/providers-api";

export type ProviderInventoryTab = "chat" | "embedding" | "reranker" | "web" | "all";

function hasConfiguredModel(modelName: string | null | undefined): boolean {
  return typeof modelName === "string" && modelName.trim().length > 0;
}

function supportsWebSearch(provider: ProviderConfig): boolean {
  return Boolean(provider.supports_web_search) || provider.provider_type === "tavily";
}

function supportsReranking(provider: ProviderConfig): boolean {
  return Boolean(provider.supports_reranking);
}

export function providerMatchesInventoryTab(
  provider: ProviderConfig,
  tab: ProviderInventoryTab,
): boolean {
  if (tab === "all") return true;
  if (tab === "chat") {
    return Boolean(provider.supports_chat) && hasConfiguredModel(provider.default_chat_model);
  }
  if (tab === "embedding") {
    return (
      Boolean(provider.supports_embeddings) && hasConfiguredModel(provider.default_embedding_model)
    );
  }
  if (tab === "reranker") {
    return supportsReranking(provider) && hasConfiguredModel(provider.default_reranker_model);
  }
  if (tab === "web") return supportsWebSearch(provider);
  return true;
}

export function providerHasConfiguredRuntime(provider: ProviderConfig): boolean {
  return (
    (Boolean(provider.supports_chat) && hasConfiguredModel(provider.default_chat_model)) ||
    (Boolean(provider.supports_embeddings) &&
      hasConfiguredModel(provider.default_embedding_model)) ||
    (supportsReranking(provider) && hasConfiguredModel(provider.default_reranker_model)) ||
    supportsWebSearch(provider)
  );
}
