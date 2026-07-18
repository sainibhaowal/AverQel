import { DocsSection, DocsShell } from "../_components/DocsShell";

export default function SimpleSystemWalkthroughPage() {
  return (
    <DocsShell
      title="Simple System Walkthrough"
      intro="A human-simple, step-by-step explanation of how the AverQel UI and backend work together from one user request to the final result."
    >
      <DocsSection title="How it works, in plain language">
        <ol className="list-decimal space-y-3 pl-6">
          <li>You type a request into AverQel or DeepSpace.</li>
          <li>
            The backend loads your tenant, your user, your conversation, and your execution mode.
          </li>
          <li>
            The master orchestrator decides the mission plan and splits work into the right lanes.
          </li>
          <li>The main chat lane still uses the normal agent loop for reasoning and tool use.</li>
          <li>
            The tool executor runs the real tools: files, shell, web, memory, connectors, and
            subagents.
          </li>
          <li>
            The UI shows the live stream in AverQel and the mission graph in the orchestration
            control room.
          </li>
          <li>If something risky appears, the system pauses and asks for approval.</li>
          <li>
            Approved work resumes, and finished work is saved in history, memory, and task storage.
          </li>
        </ol>
      </DocsSection>

      <DocsSection title="The short version">
        <p>
          You ask once, the orchestrator decides the plan, the executor does the detailed tool work,
          and the UI shows the live result while the backend keeps the state.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
