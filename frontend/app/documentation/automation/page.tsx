import { DocsCards, DocsSection, DocsShell } from "../_components/DocsShell";

export default function AutomationDocsPage() {
  return (
    <DocsShell
      title="Schedules & Automation"
      intro="Run tenant-owned DeepSpace prompts on a controlled interval, keep durable run history, and pause or cancel work without losing auditability."
    >
      <DocsCards
        items={[
          {
            title: "User-owned schedules",
            body: "Each schedule stores a name, prompt, interval, active state, next-run time, owner, and tenant boundary.",
          },
          {
            title: "Durable run history",
            body: "Runs move through queued, running, completed, failed, or cancelled states and remain queryable through the schedule history API.",
          },
          {
            title: "Worker-safe dispatch",
            body: "Celery Beat checks due schedules and workers claim work with database locking so two workers do not execute the same run.",
          },
          {
            title: "Control and audit",
            body: "Pause, resume, update, delete, and cancellation actions remain authenticated, rate-limited, tenant-scoped, and auditable.",
          },
        ]}
      />

      <DocsSection title="Lifecycle">
        <pre className="overflow-x-auto rounded-2xl border border-white/10 bg-black/30 p-5 text-xs leading-6 text-slate-300">
          <code>{`active schedule → Beat dispatch → queued run → worker claim
       → DeepSpace execution → result/artifact → next-run update`}</code>
        </pre>
      </DocsSection>

      <DocsSection title="How to use it">
        <ol className="list-decimal space-y-2 pl-6">
          <li>Open Schedules from the DeepSpace header.</li>
          <li>Enter a focused prompt and interval, then create the schedule.</li>
          <li>Pause it while editing, or cancel a run that is still in progress.</li>
          <li>Open run history to inspect the outcome and any generated artifacts.</li>
        </ol>
      </DocsSection>

      <DocsSection title="Operational requirements">
        <p>
          The API can be deployed without enabling schedules, but automatic dispatch requires the
          worker and Celery Beat services to be running against the same database and broker. Every
          deployment should set its own rate, retention, notification, and concurrency limits before
          exposing schedules to a large tenant population.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
