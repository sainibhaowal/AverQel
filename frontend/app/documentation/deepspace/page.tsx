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
            body: "Configured web research, connected Composio MCP apps, and other enabled capabilities can extend a conversation. Provider choice, account ownership, tool policy, approvals, and service availability determine which actions can run.",
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
      <DocsSection title="Load saved conversation history">
        <p>
          DeepSpace opens a recent page of a saved conversation and keeps large, changing agent
          responses in a small rendered window to avoid layout jumps. Use{" "}
          <strong>Show older messages</strong> to reveal earlier messages already loaded, then{" "}
          <strong>Load older messages</strong> to fetch the next page. Older conversation history
          stays available.
        </p>
      </DocsSection>
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
            <strong>Qel Connect:</strong> collaborate with invited members around explicitly shared
            content.
          </li>
        </ul>
      </DocsSection>
      <DocsSection title="Context and token diagnostics">
        <p>
          The composer keeps two scopes visible: the latest serialized context sent to the provider
          and the cumulative serialized input/output estimate for the whole DeepSpace turn. Tool
          calls and recovery rounds can make the turn total larger than the latest request. These
          local estimates use a provider-neutral serialization because each model family has its own
          tokenizer.
        </p>
        <p>
          When an adapter returns usage, the panel shows the provider&apos;s exact input, output,
          cache-read, and cache-write fields and labels them as the latest reported model round.
          When every round reports a field, DeepSpace also shows the exact provider turn total;
          otherwise it marks that field incomplete. Codex, hosted OpenAI-compatible providers,
          Anthropic, Gemini, LM Studio, and Ollama are normalized into the same view. Local
          providers that do not return usage remain marked as unreported; DeepSpace does not invent
          a token count for them. Cache eligibility is also kept separate from a confirmed provider
          cache read.
        </p>
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
        <p>
          For LarpRouter, DeepSeek V4.1 Flash exposes Low, High, and Max (default High) with an Off
          choice. GLM-5.3 routes expose Low, High, and Max (default Max) and do not offer Off. Other
          LarpRouter models use their advertised capabilities or stay on Provider default. The
          separate <strong>Thinking &amp; activity</strong> panel appears in an assistant reply when
          the provider streams reasoning or DeepSpace has activity to show; click its heading to
          expand or collapse it.
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
          While a reply is streaming, the composer shows a live output-token estimate and an
          estimated tokens-per-second rate. The live estimate includes answer, reasoning, and
          streamed function-argument chunks and refreshes as chunks arrive; it is intentionally
          marked as an estimate because the provider tokenizer and final usage are not available
          yet. Completed DeepSpace replies show output speed, end-to-end TTFT, and provider
          first-output time beside the response actions. End-to-end TTFT runs from the server
          starting the DeepSpace request to the first visible answer text. It includes routing,
          context preparation, provider waiting, and any reasoning or tool work before the answer.
          Provider first-output time starts when the first provider request begins and ends when the
          server receives its first output event. It includes network and connector overhead; Codex
          also includes the local desktop relay, so it is not the model vendor&apos;s internal
          compute time.
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
          DeepSpace checks the selected provider and model&apos;s saved capabilities before sending
          a prompt. Supported images go directly to a model with image input. For text-only or
          unknown models, DeepSpace uses saved Library OCR or runs its bounded Library extractor
          when extraction is still pending; the original image bytes are not sent to that model. If
          a provider explicitly rejects image input before returning output, DeepSpace retries once
          with OCR text. When OCR is unavailable or finds no readable text, DeepSpace reports the
          limitation and does not infer the image&apos;s contents. Very large image sets may be
          limited.
        </p>
        <p>
          An attachment becomes ready as soon as its private file is stored and appears under your
          sent message immediately. Text extraction and OCR continue in the background; the composer
          shows “Uploaded · reading text” while that work is pending. Supported images can be sent
          to a model with visual input before OCR finishes. For other files, DeepSpace reports
          pending extraction instead of treating missing text as proof that the file is empty. When
          processing finishes, it shows whether text was extracted, OCR was used, no readable text
          was found, or extraction was unavailable. Short whole-file reads use saved text directly;
          targeted questions and large documents can use document search.
        </p>
      </DocsSection>
      <DocsSection title="Rich answers, charts, and diagrams">
        <p>
          DeepSpace keeps normal Markdown as the source format and promotes supported fenced blocks
          into interactive surfaces. A <code>chart</code> fence accepts JSON with a title, a chart
          type (<code>line</code>, <code>bar</code>, <code>area</code>, <code>scatter</code>, or
          <code>pie</code>), and a series of labeled values. Bar charts center each category in its
          own slot and draw positive and negative values from zero. Completed charts support hover
          details, value editing, named multi-series data, left/right axes, annotations, interactive
          legends, a payload view, JSON download, and revisioned save back to the conversation. Add
          an <code>equation</code> field when a chart needs its formula shown beside the visual.
          Recalculating refreshes the chart JSON source from the same values and returns to the
          visual view. If the revision cannot be saved, the editor stays open so you can retry.
          Optional
          <code>x_label</code> and <code>y_label</code> fields appear as axis titles.
        </p>
        <p>
          Use Mermaid for flowcharts, sequence diagrams, UML, architecture, business models, and
          schedules such as Gantt charts. Gantt source can use a <code>gantt</code> fence or a
          <code>mermaid</code> fence beginning with <code>gantt</code>; make the{" "}
          <code>dateFormat</code>
          match task dates (for example, <code>YYYY-MM-DD</code> for <code>2026-01-05</code>).
          Mermaid diagrams include copy, Save artifact, JSON and Mermaid-source downloads, plus
          SVG/PNG/PDF exports. SVG stays vector-based; PNG and PDF use the SVG viewBox and render at
          up to 2× resolution within browser canvas limits. Labels use native SVG text so raster
          exports remain self-contained. UML class diagrams and Gantt schedules also expose
          structured controls that regenerate the Mermaid source. Use a <code>card</code> fence for
          a finding, recommendation, source, or media summary; cards can contain safe Markdown,
          metrics, an approved image URL, a source link, copy/download controls, and explicit
          actions. Use <code>layout: &quot;feature&quot;</code> for a larger image or logo card, or{" "}
          <code>layout: &quot;place&quot;</code> for source-linked place details with an optional
          photo. Place details and images must come from authorized search or read results.
          DeepSpace verifies page-declared photos through image reading; unavailable hours, contact
          details, or photos are omitted rather than guessed. Cards also support a bounded set of
          named icons; common detail labels such as address, hours, and email receive a matching
          icon automatically when one is omitted. Card tones are info, success, warning, error, or
          neutral; common model labels such as positive and caution are normalized automatically.
          Raw HTML and scripts are not rendered. In chat, card edits stay open until the revision is
          saved; validation, conflict, and Library-save failures are shown beside the card controls.
        </p>
        <p>
          Cards also support two data-focused layouts. <code>layout: &quot;evaluation&quot;</code>{" "}
          displays a bounded <code>score: &#123;value, max, tone&#125;</code> as an accessible
          progress bar followed by aligned supporting metrics.{" "}
          <code>layout: &quot;referral&quot;</code> displays a featured <code>primary_metric</code>,
          a copyable optional <code>code</code>, and responsive label/value rows for{" "}
          <code>details</code>. Both layouts can include a concise caveat in <code>content</code>{" "}
          and show supplied HTTP(S) source links as badges. Evaluation cards need a score and at
          least one metric; referral cards need a primary metric and at least one detail row.
        </p>
        <p>
          An <code>infographic</code> fence creates a responsive visual explainer with a selected
          layout: <code>steps</code>, <code>timeline</code>, <code>comparison</code>,{" "}
          <code>feature_grid</code>, or <code>stats</code>. Each layout validates its required
          fields, uses allowlisted icons, and shows supplied source links. A complete visual fence
          can appear while later answer text is still streaming. DeepSpace chooses among these,
          cards, charts, diagrams, and normal Markdown based on the request and available evidence.
          Process infographics can set <code>direction</code> to <code>LR</code>, <code>RL</code>,{" "}
          <code>TD</code>, or <code>DT</code>; it defaults to left-to-right and adapts to narrow
          screens. Use vertical directions when step descriptions need more room. Invalid or
          incomplete infographic data stays readable as code instead of breaking the answer.
          Infographics remain editable when inserted into workspace notes and can be saved as
          revisioned visual artifacts. Timeline labels support up to 300 characters; keep the date
          or period short and put its explanation in the item description. In edit mode,
          <strong>Save changes</strong> updates the conversation, while{" "}
          <strong>Save to Library</strong> commits the current draft and stores it as a reusable
          artifact.
        </p>
        <p>
          A <code>graph</code> fence opens the portable canvas editor: nodes can be moved and
          resized, connected, grouped, aligned, zoomed, or annotated with freehand paths, then
          copied or downloaded as DeepSpace <code>.draw.json</code>; that portable JSON is not an
          Excalidraw file. You can import the same format directly into the chat canvas. Mermaid
          source can be downloaded as <code>.mmd</code> or edited in place, which makes UML,
          business-model, and Gantt diagrams practical inside the chat and notes. A{" "}
          <code>gallery</code> fence creates a safe image sequence with captions, next/previous
          controls, source links, and downloads. DeepSpace copies usable raster images into private
          conversation storage so previews and exports do not rely on third-party CORS. These
          temporary copies expire after 30 days; choose <strong>Save image to Library</strong> to
          keep a photo. Temporary copies stay out of the regular Library list and are removed by
          scheduled storage cleanup. Visual revisions update the authenticated message and active
          note. If a visual is saved as a Library artifact, later chat, note, or artifact edits
          advance its version and synchronize the revision to the linked views. Delayed note
          refreshes preserve the latest saved visual revision. If a chat visual changes in another
          session while you edit it, DeepSpace keeps your draft open and refreshes its revision;
          save again to apply your edit to the latest version. Library files keep their own version
          guard. Providers may use a generic
          <code>json</code> fence for these same payloads; DeepSpace recognizes unambiguous card,
          chart, graph, infographic, and gallery JSON automatically. Invalid visual JSON is kept as
          plain code instead of being executed. DeepSpace repairs a mismatched outer fence around
          valid visual JSON and a shortened closing fence after a recognizable Mermaid diagram, so
          following prose remains readable. A missing image or non-image URL shows a recoverable
          fallback and does not terminate the answer. JSON, SVG, PNG, and PDF exports are available
          for visual blocks; gallery SVG/PNG exports embed owned images when available and show a
          placeholder for a missing image. PNG/PDF export strips external SVG resources before
          rasterization; if a browser still blocks rasterization, the error is shown inline instead
          of escaping as an exception. Saved rich blocks in notes are restored as rendered visuals
          when the note is reopened, so the note preview does not fall back to raw visual-fence
          code.
        </p>
        <p>
          Markdown tables show a copy button, <strong>Save to Library</strong>, and an{" "}
          <strong>Export</strong> menu above the table when you hover it or focus the controls with
          the keyboard. Export offers CSV and XLSX in a floating menu below the Export button. The
          menu overlays the content without moving the table rows. Saving stores the table as a
          private, versioned visual artifact. If clipboard access is blocked, DeepSpace tries a
          browser fallback and shows an error if copying still cannot complete. Export and
          Library-save failures are reported beside the controls.
        </p>
        <pre className="overflow-x-auto rounded-xl border border-white/10 bg-black/20 p-4 text-xs leading-6">
          <code>{`\`\`\`chart
{"title":"Quarterly revenue","chart_type":"line","equation":"y = mx + b","series":[{"label":"Q1","value":12},{"label":"Q2","value":19}]}
\`\`\`

\`\`\`card
{"title":"Decision brief","tone":"success","content":"**Ship** the verified workflow.","metrics":[{"label":"Confidence","value":"92%"}]}
\`\`\``}</code>
        </pre>
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
          Use <strong>Edit</strong> on the latest completed prompt to revise it and regenerate its
          reply. DeepSpace saves each prompt revision and queues each generation with the
          conversation, preserving the earlier prompt and reply versions. You can edit and submit
          that same prompt again after each generation finishes. Older prompts, active turns, and
          prompts with pending queue work cannot be edited.
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
          composer queue while they wait. A queued prompt is shown as active only after a worker
          claims it, and the chat reconnects after that state change. If a worker claims a prompt
          just before you choose <strong>Steer</strong>, the queue refresh explains that it has
          already started; a running prompt cannot be reordered.
        </p>
        <p>
          A queue submission that meets a temporary service interruption is retried once; if it
          still cannot be saved, the draft stays in the composer and the error explains what
          happened. An initial stream HTTP error also gets one retry, then automatic reconnect stops
          so the activity panel does not stay live through a retry loop. This reports a connection
          failure; it does not confirm that an already-started server worker stopped. Reopen the
          conversation after service recovers to attach to its saved run. When you stop a running
          response, the activity panel waits briefly for the server confirmation. If that terminal
          event is unavailable, it stops the local timer and reloads saved history so an interrupted
          worker cannot remain displayed as running.
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
          When a response creates a saved task plan, a collapsible task drawer appears immediately
          above the composer. It opens as the plan is created, shows each task&apos;s live status,
          and can be collapsed to a one-row progress summary that keeps the active task and its
          running indicator visible. The task drawer is the single place that shows plan progress;
          <strong>Thinking &amp; activity</strong> continues to show only the tool activity.
          DeepSpace checks the saved task ledger before it reports the final answer.
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
