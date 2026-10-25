import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function ProvidersPage() {
  return (
    <DocsShell
      title="Providers"
      intro="AverQel has model providers for AI generation and retrieval, plus a separate Composio setup for connecting your own external app accounts to DeepSpace."
    >
      <DocsCards
        items={[
          {
            title: "Model Providers",
            body: "LarpRouter, OpenRouter, OpenAI-compatible endpoints, Cline, Mistral, Meta, Anthropic, Google, Ollama, LM Studio, embeddings, rerankers, and search runtimes power AI generation and retrieval.",
          },
          {
            title: "Self-hosted SearXNG",
            body: "DeepSpace can use a configured SearXNG JSON endpoint for server-side web search without a third-party search API key.",
          },
          {
            title: "MCP Providers",
            body: "Under Providers → MCP, choose + to browse provider families, then select Composio and add your own project key. Then browse the live app and tool catalog in MCP Marketplace.",
          },
          {
            title: "Your account connections",
            body: "Each AverQel account stores its own encrypted Composio key and connects its own external app accounts.",
          },
          {
            title: "Explicit Ownership",
            body: "Provider credentials and MCP connections are scoped to the current tenant and user. They are never treated as a shared global account.",
          },
        ]}
      />

      <DocsSection title="Model providers versus MCP providers">
        <p>
          Model providers answer questions or create embeddings. The MCP integration is separate:
          Composio connects external apps whose tools DeepSpace can call under your saved policy. An
          AI model provider key and a Composio project key have different settings and purposes.
        </p>
        <p>
          In Providers, open the <strong>MCP</strong> section, choose <strong>+</strong> to browse
          provider families, then select <strong>Composio</strong> to open its setup panel. Add your
          Composio project API key there. Do not put it in a model-provider form. AverQel encrypts
          it and scopes it to your signed-in tenant and account; the running server uses it to make
          Composio requests.
        </p>
      </DocsSection>

      <DocsSection title="LarpRouter">
        <p>
          Add <strong>LarpRouter</strong> from Providers and enter your LarpRouter API key. AverQel
          uses the OpenAI-compatible API root <code>https://larprouter.com/v1</code> by default and
          loads chat model IDs from the key&apos;s <code>/models</code> catalog. Choose a discovered
          model, then assign the connection to Query or DeepSpace. LarpRouter controls which model
          pools are available to each key, so the model catalog depends on the key and its pool.
        </p>
        <p>
          Model catalog refresh uses the provider&apos;s saved timeout, capped at 30 seconds. If the
          provider does not respond in time, AverQel reports a refresh timeout and keeps the last
          successfully loaded model catalog available.
        </p>
        <p>
          The integration uses LarpRouter&apos;s OpenAI-compatible Chat Completions protocol,
          including streaming, function tools, and image inputs when the selected model supports
          them. DeepSpace uses the selected model&apos;s context and output limits, and requests
          provider-reported token usage for streamed responses. The LarpRouter API reference does
          not list an embeddings endpoint, so AverQel does not offer this connection for embeddings.
          For current routes and model availability, see the{" "}
          <a href="https://larprouter.com/docs">LarpRouter API reference</a>.
        </p>
        <p>
          DeepSpace also uses verified model-specific reasoning controls for known LarpRouter
          routes. DeepSeek V4.1 Flash offers Low, High, and Max, defaults to High, and supports
          turning thinking off. GLM-5.3 offers Low, High, and Max, defaults to Max, and always
          thinks. Other LarpRouter models show only capabilities returned by the model catalog or a
          verified model profile.
        </p>
      </DocsSection>

      <DocsSection title="Thinking levels and context limits">
        <p>
          The Thinking selector is model-aware. DeepSpace uses provider-advertised model metadata
          when available and falls back to a verified model-family profile. If the selected
          model&apos;s cached metadata is missing or stale, DeepSpace refreshes that provider&apos;s
          model catalog in the background and updates the selector when the response arrives. It
          shows only levels confirmed for that model, including provider-specific names with
          readable labels.
        </p>
        <p>
          Each provider receives its own native reasoning control. For example, a provider may map
          the displayed levels to low, high, and maximum effort internally. Selecting Off sends an
          explicit disable request where the provider supports disabling reasoning. A model that
          does not support a setting is never forced into it. A provider catalog that omits
          reasoning details cannot prove which effort levels an unfamiliar model accepts, so
          DeepSpace keeps that model on its provider default until a verified profile or explicit
          metadata is available.
        </p>
        <p>
          The composer context meter uses the selected model&apos;s current context limit when the
          provider exposes it, then verified provider metadata as a fallback. It is an estimate of
          the serialized request and output budget, not a billing counter. Unknown model limits are
          shown as unavailable rather than guessed.
        </p>
      </DocsSection>

      <DocsSection title="Cline, Mistral, and Meta model providers">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Cline API</strong> uses a Cline API key and its OpenAI Chat Completions route.
            AverQel loads model IDs from Cline&apos;s public OpenAI-style <code>/models</code>{" "}
            route; exact <code>provider/model-name</code> IDs can also be entered manually. Cline
            does not publish an embeddings route. Streaming and function tools use the documented
            Chat Completions format. Model discovery reads the public catalog without sending the
            API key and does not validate the key or model access. AverQel&apos;s runtime check is
            degraded because it does not send a billable chat request; model availability still
            depends on the Cline account.
          </li>
          <li>
            <strong>Mistral AI</strong> uses a Mistral API key, lists account-accessible models, and
            supports chat and embeddings. Its current reasoning models use Mistral&apos;s
            <code> reasoning_effort</code> field; Off maps to <code>none</code> where the model
            exposes that control.
          </li>
          <li>
            <strong>Meta AI</strong> uses a Meta Model API key, lists available models, and routes
            chat through the Responses API. The provider omits image, voice, and segmentation models
            from the chat picker, does not offer embeddings, and sends <code>store: false</code> for
            stateless Meta responses. DeepSpace currently sends text, attached images, and tools;
            Meta-specific video, audio, PDF, and image-generation routes are not exposed. Muse Spark
            keeps its reasoning private and uses Meta&apos;s sampling defaults; Off omits the effort
            field because Muse Spark rejects <code>none</code> and may still reason at its default
            level. Extreme High maps to
            <code> max</code> on Standard Muse Spark 1.3 and to <code> xhigh</code> on contributor
            or older models.
          </li>
        </ul>
      </DocsSection>

      <DocsSection title="Moonshot, Z.AI, NVIDIA NIM, and Manus">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Moonshot AI (Kimi)</strong> uses the OpenAI Chat Completions API at
            <code> https://api.moonshot.ai/v1</code>. AverQel loads models and keeps the
            vendor&apos;s safe context, modality, and reasoning metadata. Kimi does not expose an
            embeddings route in its API reference. Reasoning controls follow the selected model:
            Kimi K3 maps Low, High, and Extreme High to its supported effort values; Kimi K2.6
            supports its thinking switch; K2.7-Code always thinks.
          </li>
          <li>
            <strong>Z.AI (GLM)</strong> uses the documented OpenAI-compatible chat route at
            <code> https://api.z.ai/api/paas/v4</code>. Enter the exact GLM model ID in the provider
            settings because Z.AI&apos;s API reference does not publish a model-list endpoint.
            GLM-5.3 supports Low, High, and Max effort and always reasons; GLM-5.2 supports effort
            plus an Off switch; earlier supported GLM families use the documented thinking toggle.
            The integration does not advertise embeddings.
          </li>
          <li>
            <strong>NVIDIA NIM</strong> uses the NVIDIA-hosted OpenAI-compatible API by default at
            <code> https://integrate.api.nvidia.com/v1</code>. The provider supports chat, model
            discovery, and the documented embeddings route. Some NVIDIA embedding models require an{" "}
            <code>input_type</code>; AverQel sends <code>query</code> for retrieval and
            <code>passage</code> for indexing for the model families that document that field. NIM
            serves multiple model families. AverQel uses model metadata or verified family profiles
            for reasoning controls; for example, Nemotron 3 Ultra exposes Off, Medium, and High,
            while Super exposes Off, Low, and High. Other NIM models keep their provider default
            unless the catalog or a verified profile describes their controls. A self-hosted NIM can
            use its own base URL.
          </li>
          <li>
            <strong>Manus Agent API</strong> creates private asynchronous tasks through Manus API
            v2. Its model choices are agent profiles (Standard, Lite, and Max with supported Max
            thinking levels), not independently selectable LLM model IDs. AverQel polls the task
            until it finishes and then returns the final answer; Manus does not stream answer tokens
            through this API. Stopping generation requests cancellation of the remote Manus task.
            User image attachments are uploaded to Manus and attached to the task. A task waiting
            for a question or action is reported with a link to continue in Manus; AverQel does not
            approve actions automatically. The integration does not provide embeddings, token usage,
            or AverQel function-tool calls. The API key and prompt are sent to Manus to run the
            task.
          </li>
        </ul>
      </DocsSection>

      <DocsSection title="OpenAI Codex Login in AverQel Desktop">
        <p>
          AverQel Desktop includes a Codex Login tab under the OpenAI provider. It first checks
          whether the local Codex CLI is signed in to a ChatGPT account. When it is, AverQel uses
          Codex&apos;s local app-server for account/model discovery and inference; it does not read
          the CLI credential file or copy its tokens. A CLI API-key session is not treated as
          ChatGPT plan access. If no usable CLI ChatGPT session is available, the user can sign in
          through OpenAI in the system browser. Those OAuth credentials are encrypted with the
          operating system&apos;s desktop credential storage and stay on that desktop. Browser
          sign-in is unavailable if secure operating-system storage is unavailable. Removing a
          browser-signed-in account clears its local credentials; AverQel reports whether OpenAI
          confirmed token revocation and directs users to ChatGPT Settings → Usage if it could not.
        </p>
        <p>
          The CLI path uses Codex app-server&apos;s account and model-list methods. Its model list
          is a catalog, not proof that every model is enabled for the account; OpenAI checks model
          access when a request is made. The browser sign-in path loads visible models from
          OpenAI&apos;s <code> /v1/models</code> endpoint and streams Responses API requests with
          <code> store: false</code>. Both paths run through the Electron main process. Provider
          settings store an opaque local-account identifier and discovered model metadata; the raw
          CLI email and credentials stay on the desktop. The backend relays inference through a
          one-use WebSocket ticket and transient request/response frames. DeepSpace still stores
          conversation history under its existing retention settings. The desktop must remain open
          and the account must remain signed in while this provider is in use.
        </p>
        <p>
          Codex app-server starts outside the project in the operating system&apos;s temporary
          directory, and each inference gets a private temporary workspace. Inference is enabled
          only when the installed CLI supports AverQel&apos;s restricted permission profile, which
          denies filesystem access except for minimal runtime paths. Shell, MCP, hooks, apps,
          plugins, subagents, web search, and Codex&apos;s local conversation history are disabled.
          API keys and other token-like environment variables are removed from the Codex subprocess.
          Older or incompatible CLI versions fall back to browser sign-in.
        </p>
        <p>
          This option is available only in the AverQel desktop packages for Windows, Linux, and
          macOS. It is a DeepSpace chat connection; it does not provide API-key billing, embeddings,
          general Codex CLI agent access, or every hosted Responses API tool. The CLI app-server
          protocol is experimental; older or incompatible CLI versions use the browser sign-in
          option instead. Model capabilities and account eligibility come from OpenAI and can
          change. OpenAI&apos;s{" "}
          <a href="https://developers.openai.com/siwc/token-sharing-open-source">
            Sign in with ChatGPT guidance
          </a>
          describes this integration as a preview and requires its eligibility process for paid or
          remotely hosted apps. Users may be unable to authorize an account until OpenAI approves
          the application.
        </p>
        <p>
          Local OAuth storage does not make DeepSpace conversations local-only. The existing
          DeepSpace backend receives and stores prompts and conversation history. OpenAI requests
          use <code>store: false</code>, but AverQel&apos;s conversation retention settings still
          apply.
        </p>
        <p>
          OpenAI account and usage restrictions are reported as provider errors. A ChatGPT plan
          usage-limit response is not automatically retried or sent through a different billing
          path; check ChatGPT settings and retry only when the account can make another request.
        </p>
      </DocsSection>

      <DocsSection title="LM Studio and Ollama on AverQel Desktop">
        <p>
          AverQel Desktop can use LM Studio or Ollama installed on the same computer. Start LM
          Studio&apos;s OpenAI-compatible server at <code>http://127.0.0.1:1234/v1</code> or Ollama
          at <code>http://127.0.0.1:11434</code>, choose the provider, and select{" "}
          <strong>This computer</strong>. The Electron main process validates the loopback URL and
          streams chat, model discovery, health, embeddings, and Ollama pulls through the existing
          authenticated desktop relay.
        </p>
        <p>
          LM Studio and Ollama are shown as unavailable in the hosted web app because its browser
          cannot reach a user&apos;s loopback process. Open AverQel Desktop to configure them. The
          desktop option does not make the complete application offline: authentication,
          conversation storage, DeepSpace orchestration, and tools continue to use the AverQel
          backend. AverQel does not bundle either runtime or download LM Studio models.
        </p>
      </DocsSection>

      <DocsSection title="Search available models">
        <p>
          Every model selector in provider settings includes a search field. Search by model ID,
          display name, model type, context size, or discovered capability metadata such as runtime
          and quantization. Matching ignores letter case and punctuation, and multiple words narrow
          the results together. The search covers models AverQel has discovered for that provider;
          when model discovery is disabled, enter the endpoint&apos;s model ID in the search field
          and choose the exact-ID option.
        </p>
      </DocsSection>

      <DocsSection title="OpenAI-compatible custom endpoints">
        <p>
          Add a custom provider for an endpoint that follows either the Chat Completions or
          Responses request and response format. Enter the API root URL, such as
          <code> https://gateway.example/v1</code>, then select the protocol that the server
          implements. AverQel converts its conversation, image, and function-tool data to the
          selected protocol. A custom route changes the URL path; it does not translate an unrelated
          API schema. Responses may use the standard protocol object directly or wrap a successful
          result in a <code>{`{ success: true, data: ... }`}</code> envelope.
        </p>
        <table>
          <thead>
            <tr>
              <th>Setting</th>
              <th>What it controls</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Protocol and routes</td>
              <td>
                Choose Chat Completions or Responses and set the chat, model-list, and embedding
                paths. Leave the model-list path blank to enter model IDs manually. Leave the
                embedding path blank when the endpoint does not offer embeddings.
              </td>
            </tr>
            <tr>
              <td>Authentication</td>
              <td>
                The API key is stored using AverQel&apos;s encrypted provider-secret storage. Set
                the key header name and choose Bearer or raw value formatting for gateways that use
                a header such as <code>X-API-Key</code>.
              </td>
            </tr>
            <tr>
              <td>Request fields</td>
              <td>
                Select the output-token field used by the endpoint or omit that limit, omit
                temperature when it is not accepted, and opt in to sending the requested embedding
                dimensions when supported.
              </td>
            </tr>
            <tr>
              <td>Reasoning</td>
              <td>
                Configure only documented field paths and values for that endpoint. Enable the
                standard choices or add a model-specific level using the endpoint&apos;s documented
                option name, then set its exact native value. DeepSpace offers only the configured
                names. Off sends the configured disable value; if no disable value is set, AverQel
                omits reasoning fields and the model may keep its own default.
              </td>
            </tr>
          </tbody>
        </table>
        <p>
          Model discovery uses the configured models route. If discovery is disabled, the provider
          health status is shown as degraded because AverQel cannot verify chat connectivity without
          sending a potentially billable generation request. Existing cached models remain
          available, and you can set the exact chat or embedding model ID in the provider form.
        </p>
        <p>
          When an endpoint rejects a request field, turn off temperature or select its documented
          output-token field. For a reasoning error such as{" "}
          <code>Unsupported parameter(s): enable_thinking</code>, leave the reasoning controls
          unconfigured unless the endpoint explicitly documents them. AverQel does not infer custom
          endpoint controls from a model name.
        </p>
      </DocsSection>

      <DocsSection title="Self-hosted SearXNG web search">
        <p>
          Add <strong>SearXNG (Self-hosted)</strong> from the Web provider tab and enter the URL
          reachable by the AverQel API, for example <code>http://searxng:8080</code> when both
          services share a private Docker network. SearXNG must have its JSON search format enabled.
          No API key is required.
        </p>
        <p>
          DeepSpace invokes the bounded <code>web_search</code> tool only when the selected model
          requests it. Results are fetched server-side, filtered by the configured domain policy,
          and returned with titles, URLs, snippets, source engines, and available publication dates.
          The final Markdown response receives a Sources section with links.
        </p>
        <p>
          Requests use bounded timeouts, Redis-backed per-user rate limits, redirect blocking, URL
          validation, and endpoint SSRF checks. The model never receives shell or cURL access; it
          receives only the typed web-search tool and sanitized result data. MCP remains a separate
          integration surface.
        </p>
      </DocsSection>

      <DocsSection title="Composio app setup">
        <ol className="list-decimal space-y-2 pl-6">
          <li>Create or select your own Composio project and copy its project API key.</li>
          <li>
            In AverQel, open <strong>Providers → MCP</strong>, choose <strong>+</strong> to browse
            provider families, then select <strong>Composio</strong>. Enter the key in its setup
            panel and choose <strong>Validate and save</strong>.
          </li>
          <li>
            Open <strong>MCP Marketplace</strong> to browse the live app catalog, inspect tools, and
            connect an app to your external account.
          </li>
          <li>
            Open <strong>Installed</strong> to check connection status and use the app&apos;s tools
            in DeepSpace.
          </li>
        </ol>
        <p>
          The marketplace shows Composio&apos;s live native toolkit catalog. App and tool counts can
          change. AverQel&apos;s eight bundled Google, GitHub, Notion, and Slack cards are no longer
          marketplace choices; existing installed connection records are retained.
        </p>
      </DocsSection>

      <DocsSection title="OAuth and callback requirements">
        <p>
          OAuth apps require the deployment operator to configure AverQel&apos;s public HTTPS
          origin. Local development may use an HTTP localhost origin. Users do not register a
          callback verifier in their Composio projects. After Composio returns the connected-account
          ID, AverQel checks it against the account&apos;s pending request and confirms the
          connected account belongs to the requested app.
        </p>
        <p>
          Composio and the app provider handle the authorization flow. AverQel checks the returned
          connection against the signed-in account before enabling its tools. Some apps or projects
          may require additional consent or permissions. Composio-marked no-auth apps do not use
          OAuth.
        </p>
      </DocsSection>

      <DocsSection title="Isolation, privacy, and tool approvals">
        <p>
          AverQel encrypts each user&apos;s Composio project key and scopes it to that user&apos;s
          tenant and account. The running AverQel server decrypts it when calling Composio, so the
          key is not end-to-end encrypted from the server. Other AverQel users cannot use that key
          or claim the account&apos;s app sessions. Composio and the external app provider process
          the actions and data you send to them.
        </p>
        <p>
          DeepSpace routes tools through the MCP broker and checks the saved connection policy.
          Reads may run under that policy; writes, deletions, and external messages require an
          approval card before execution. Always allow cannot bypass this safety requirement.
        </p>
        <p>
          Removing the Composio key disables only that account&apos;s Composio sessions in AverQel.
          It does not revoke grants held remotely by Composio or the external provider; revoke those
          in the relevant service when required.
        </p>
      </DocsSection>

      <DocsSection title="MCP connection limits">
        <p>
          Composio supplies the app catalog and hosted MCP endpoints. App availability, tool
          schemas, authentication methods, and permissions can change. The catalog does not
          guarantee that every listed app is enabled for a given Composio project or connected
          account.
        </p>
        <p>
          Existing AI model, embedding, reranking, and web-search providers remain separate from
          MCP. Composio configuration does not replace or share their credentials.
        </p>
      </DocsSection>

      <DocsSection title="Existing AI provider support">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            Chat runtimes include LarpRouter, OpenRouter, OpenAI-compatible providers, Cline,
            Mistral, Meta, Anthropic, Google, Ollama, LM Studio, and OpenCode Zen.
          </li>
          <li>
            Embedding runtimes include local deterministic paths, sentence-transformers, OpenRouter,
            Mistral, Ollama, LM Studio, and embedding-capable OpenAI-compatible providers.
          </li>
          <li>Reranking and web search use their own provider routing and secret boundaries.</li>
        </ul>
        <p>
          These model-provider flows remain separate from the remote MCP marketplace and are not
          replaced by it.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
