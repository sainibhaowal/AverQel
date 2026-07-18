import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function ProvidersPage() {
  return (
    <DocsShell
      title="Providers"
      intro="Providers are the model and search runtimes AverQel can route work through for chat, reasoning, embeddings, reranking, web search, and local execution."
    >
      <DocsCards
        items={[
          {
            title: "Cloud Providers",
            body: "AverQel can use OpenRouter, OpenAI-compatible endpoints, Anthropic, Google, Tavily, Cohere, and other provider families depending on the feature scope.",
          },
          {
            title: "Local Providers",
            body: "Local runtimes such as Ollama, LM Studio, sentence-transformers, and deterministic/local embedding paths give teams a route for private local execution and model control.",
          },
          {
            title: "OpenRouter Coverage",
            body: "OpenRouter is a major flexibility surface because it gives AverQel access to a broad upstream model catalog through one integration point while still preserving provider routing logic inside AverQel.",
          },
          {
            title: "Secret Rules",
            body: "Keys are encrypted, masked, never returned raw, and should not appear in logs, audit details, or UI payloads.",
          },
        ]}
      />

      <DocsSection title="What the provider layer does">
        <p>
          The provider layer does more than store keys. It decides which runtime to use for chat,
          embeddings, reranking, web search, and model discovery. It also resolves whether a task
          should go to a cloud endpoint or a local endpoint based on the configured feature scope
          and available capabilities.
        </p>
      </DocsSection>

      <DocsSection title="What the current codebase supports">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            chat runtimes for OpenRouter, OpenAI-compatible providers, Anthropic, Google, Ollama, LM
            Studio, and OpenCode Zen
          </li>
          <li>
            embedding runtimes for local deterministic, sentence-transformers, OpenRouter, Ollama,
            LM Studio, and OpenAI-compatible providers
          </li>
          <li>reranker support through sentence-transformers and Cohere-style paths</li>
          <li>web search provider routing through Tavily</li>
          <li>
            model discovery and, where relevant, model installation support for local runtimes like
            Ollama
          </li>
        </ul>
      </DocsSection>

      <DocsSection title="Why OpenRouter matters here">
        <p>
          OpenRouter gives AverQel a broad model access surface from one provider integration. That
          makes it especially useful when the platform needs flexibility across many upstream model
          families without hardwiring every one of them into the product UI separately.
        </p>
        <p>
          In AverQel, OpenRouter is still treated as one provider inside the native provider routing
          system. It does not replace AverQel&apos;s own selection logic, safety model, or execution
          preferences.
        </p>
      </DocsSection>

      <DocsSection title="Personal, tenant, and future platform control">
        <p>
          The current safe default is personal provider ownership with tenant-aware scoping and
          encrypted secret storage. Platform-managed or broader shared provider flows can be layered
          in later, but the secure base remains explicit ownership and explicit assignment.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
