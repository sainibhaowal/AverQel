import Link from "next/link";
import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function DeepSpaceDocsPage() {
  return (
    <DocsShell
      title="DeepSpace workspace"
      intro="DeepSpace is AverQel’s conversation-led workspace for research, writing, analysis, and continuing work. It brings the conversation and DeepSpace-owned working files together, while using optional providers and tools only when the deployment and user permissions allow them."
    >
      <DocsCards
        items={[
          {
            title: "Conversations",
            body: "Open and continue saved conversations. Responses may stream, and work that uses background execution can show queued or running state.",
          },
          {
            title: "Research & tools",
            body: "Configured web research, approved MCP tools, and other enabled capabilities can extend a conversation. Provider choice, policy, approvals, and service availability determine which actions can run.",
          },
          {
            title: "Working Library & notes",
            body: "DeepSpace has a Library and editor for files and deliverables associated with DeepSpace work. This is distinct from the source-file Documents Hub.",
          },
          {
            title: "Optional capabilities",
            body: "Sandbox execution, schedules, voice, and some integrations require additional services or credentials. See each guide for its limits and setup needs.",
          },
        ]}
      />
      <DocsSection title="Choose the right area">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Documents Hub:</strong> upload, inspect, organize, and manage source documents.
          </li>
          <li>
            <strong>Query:</strong> ask focused questions over accessible source documents and
            inspect cited evidence.
          </li>
          <li>
            <strong>DeepSpace:</strong> conduct broader conversational work and use supported tools,
            notes, or DeepSpace Library files when available.
          </li>
          <li>
            <strong>Collections:</strong> collaborate with invited members around explicitly shared
            content.
          </li>
        </ul>
      </DocsSection>
      <DocsSection title="Choose a model in DeepSpace">
        <p>
          The model picker searches across available models from your connected chat providers. It
          groups results under each provider&apos;s display name, sorts provider groups and model
          names alphabetically, and lets you search by provider, model name, model ID, or
          quantization. The first provider group opens by default; opening another group closes the
          previous one. The selected model is marked within its provider group.
        </p>
        <p>
          The Think menu follows the selected model&apos;s advertised reasoning levels. For a local
          Codex CLI account, DeepSpace reads the per-model catalog, including Codex&apos;s{" "}
          <code>minimal</code> and <code>ultra</code> levels, and sends the selected model&apos;s
          native value. Other safe levels advertised by a model are shown with readable labels. The
          browser ChatGPT model catalog may omit per-model effort metadata; when it does, DeepSpace
          uses the existing OpenAI reasoning profile and does not present it as an exact
          account-specific list.
        </p>
        <p>
          Other providers use the selected model&apos;s verified capability profile or the effort
          levels advertised by its model catalog. LM Studio&apos;s model catalog can provide native
          reasoning options, and Ollama&apos;s model detail endpoint provides each installed
          model&apos;s named thinking values or On/Off support. Models without reliable metadata
          keep their provider default. If the selected model&apos;s metadata is missing or stale,
          DeepSpace refreshes that provider&apos;s catalog in the background and updates the menu
          when it completes. The configured default and current chat assignment are included even
          before their first model-catalog cache entry exists. For example, NVIDIA NIM Nemotron 3
          Ultra offers Off, Medium, and High; Nemotron 3 Super offers Off, Low, and High. DeepSpace
          sends the provider&apos;s native request values for those choices. When a model&apos;s
          capabilities remain unknown, the menu shows the provider default instead of suggesting
          unsupported levels. If a model always reasons and cannot disable that behavior, DeepSpace
          shows its available levels or On without offering a misleading Off choice.
        </p>
      </DocsSection>
      <DocsSection title="Provider health and conversation details">
        <p>
          The compact provider-health summary is based on your recent DeepSpace usage, not a live
          connection check. Expand it to see recent usage by provider and model, including sample
          count, failure rate, and p50/p95 latency. P50 is the median; p95 shows the slower end of
          recent requests. If there are no samples yet, DeepSpace says{" "}
          <strong>No recent usage yet</strong>.
        </p>
        <p>
          The expanded details also show the selected conversation&apos;s existing Conversation ID,
          which you can copy for support. It is the same ID used by the chat system; there is no
          separate Chat ID or DeepSpace ID.
        </p>
      </DocsSection>
      <DocsSection title="Response speed and first-token time">
        <p>
          Completed DeepSpace replies show output speed, end-to-end TTFT, and provider first-output
          time beside the response actions. End-to-end TTFT runs from the server starting the
          DeepSpace request to the first visible answer text. It includes routing, context
          preparation, provider waiting, and any reasoning or tool work before the answer. Provider
          first-output time starts when the first provider request begins and ends when the server
          receives its first output event. It includes network and connector overhead; Codex also
          includes the local desktop relay, so it is not the model vendor&apos;s internal compute
          time.
        </p>
        <p>
          Output speed divides exact provider-reported completion tokens by the measured interval
          between the first and last output events in each generation round. Provider counts may
          include hidden reasoning or tool-call tokens, but DeepSpace never displays reasoning text
          in this metric. If exact usage is missing, the provider sends only one output event, or a
          response uses a buffered fallback, speed is shown as unavailable instead of being guessed
          from text. The tooltip explains why. These measurements are saved with the reply and
          remain visible when you reopen its conversation.
        </p>
      </DocsSection>
      <DocsSection title="Use files and images in a chat">
        <p>
          Attach files to a message when you want DeepSpace to use them as context. The selected
          model can use the file-reading tools that fit your request, including reading extracted
          text, searching a longer document, comparing files, or analyzing tabular data. DeepSpace
          checks that attached files belong to your account and conversation before using them.
        </p>
        <p>
          Images are sent directly to the model only when that model supports image input. If it
          does not, DeepSpace uses the text saved by upload-time extraction or OCR when available.
          If a model explicitly rejects an image, DeepSpace retries once without the image and uses
          saved OCR text. If visual input is unavailable and extraction found no readable text, the
          attachment shows that status and the assistant is told not to guess. Very large image sets
          may be limited.
        </p>
        <p>
          After upload, each attachment shows whether text was extracted, OCR was used, no readable
          text was found, or extraction was unavailable. Short whole-file reads use saved text
          directly; targeted questions and large documents can use document search.
        </p>
      </DocsSection>
      <DocsSection title="Prompt and queue status">
        <p>
          Replies with saved versions have previous and next controls. Choosing a version shows it
          immediately and saves it as the active reply; all saved versions remain available. If
          saving the selection fails, DeepSpace reloads the saved reply. When you switch
          conversations, the old thread is temporarily read-only until the selected history loads. A
          background run continues on the server and can reconnect when you return to its chat. If
          history cannot be loaded, use <strong>Try again</strong> to retry without replacing the
          thread you were viewing.
        </p>
        <p>
          Use <strong>Regenerate</strong> on a saved reply to start a fresh generation for that
          response. DeepSpace keeps the previous reply as a version, uses the saved prompt and its
          Library attachments, and queues the work with the rest of the conversation. You can
          regenerate while another reply is running; the current reply remains visible until the
          regeneration starts. Regenerating an older reply uses only the conversation context that
          came before that reply. If the browser reconnects or the app is reopened, the response
          continues from its saved event stream. A queued regeneration can be canceled, but its
          source prompt cannot be edited.
        </p>
        <p>
          The message field grows with multiline text up to five visible rows; longer drafts scroll
          inside the field.
        </p>
        <p>
          For a saved conversation, DeepSpace stores each turn in its durable queue before a
          background worker starts it. While your current turn is waiting in that queue, its
          activity panel says <strong>Queued</strong>. After a worker claims it, the panel changes
          to <strong>Thinking &amp; activity</strong>. The composer queue is for other pending
          turns, so the current prompt is not listed there a second time.
        </p>
        <p>
          If a prompt remains queued, the worker has not claimed it yet. Workspace administrators
          should check DeepSpace worker availability; users can keep other pending prompts in the
          composer queue while they wait.
        </p>
        <p>
          Use <strong>Edit</strong> beside a queued prompt to bring it back into the composer.
          Saving updates that same queue entry and keeps its place in line; canceling restores the
          text you had in the composer before editing. Existing Library attachments remain on the
          queued prompt. A prompt cannot be edited after a worker starts it, or after it fails; in
          those cases the edited text stays in the composer and a failed prompt can be retried as a
          separate attempt.
        </p>
        <p>
          If a turn fails, DeepSpace keeps its error and advances to the next queued prompt. Use
          <strong> Retry</strong> on the red error card or <strong>Retry prompt</strong> in the
          queue to create a new attempt from the exact saved prompt and its original Library
          attachments. It resumes from a saved checkpoint when one is available; if that checkpoint
          has expired, DeepSpace restarts the saved prompt and completed external actions could run
          again. <strong>Continue queued prompts</strong> resumes a manually paused queue without
          retrying the failed turn.
        </p>
        <p>
          If a background worker stops unexpectedly, DeepSpace closes the old live stream, keeps any
          partial text, and marks the turn as retryable instead of leaving it labeled as running.
          Use <strong>Retry</strong> or <strong>Regenerate</strong> to start a new attempt.
        </p>
        <p>
          When DeepSpace resumes a clarification, approval, or failed run, it restores the original
          saved task even if it is older than the normal chat context window. Some providers also
          require private continuation data after a tool call; DeepSpace stores that data encrypted
          for resuming and does not return it in chat history.
        </p>
        <p>
          Error headings describe the failure type. <strong>Request rejected</strong> means the
          provider received but refused the request, while <strong>Provider unavailable</strong>
          means a provider timeout or server outage. A request rejection usually needs the provider
          message or selected model settings to be checked; waiting alone may not fix it.
        </p>
      </DocsSection>
      <DocsSection title="DeepSpace guides">
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <Link className="text-primary underline" href="/documentation/deepspace-library">
              DeepSpace Library
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/editor-files">
              Notes and editor
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/web-research">
              Web research
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/sandbox">
              Sandbox and data analysis
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/artifacts">
              Artifacts and exports
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/automation">
              Schedules and automation
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/memory-workspace">
              Memory
            </Link>
          </li>
          <li>
            <Link className="text-primary underline" href="/documentation/voice">
              Voice
            </Link>
          </li>
        </ul>
      </DocsSection>
      <DocsSection title="Availability and limits">
        <p>
          DeepSpace behavior depends on a configured model provider. Tool use is constrained by
          connection ownership, provider and tool policy, approval settings, and backend
          authorization. A model response is not itself proof that an external action completed;
          review the tool result or generated artifact status shown in the app.
        </p>
        <p>
          Durability and feature availability depend on the running API, database, workers, and any
          optional services used by a particular action. This guide does not claim a deployment is
          production-ready solely because the feature exists in the repository.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
