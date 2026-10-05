import { DocsCards, DocsSection, DocsShell } from "./_components/DocsShell";
import { docsNavGroups } from "./_components/docsNav";

const descriptions: Record<string, string> = {
  "What is AverQel?":
    "How the workspace areas fit together, what they do, and where optional services apply.",
  "Getting started":
    "A practical first-use path from account setup to documents, Query, and DeepSpace.",
  "Product overview": "A map of the current product areas with links to their dedicated guides.",
  "Documents Hub":
    "Upload, process, inspect, organize, and manage source documents in your workspace.",
  "Organization & collaboration":
    "Tags, folders, saved views, versions, comments, sharing, and role-dependent controls.",
  "Grounded queries":
    "Ask retrieval-first questions over documents you are authorized to access and review their sources.",
  "DeepSpace workspace":
    "Conversation-led research and work, with its own Library, notes, tools, and optional services.",
  "DeepSpace Library":
    "Files attached to DeepSpace work, datasets, and outputs created during analysis.",
  "Notes & editor": "Draft, edit, and export notes and deliverables from the DeepSpace workspace.",
  "Web research":
    "How configured search and page-fetching services gather evidence, and what they cannot verify.",
  "Sandbox & data analysis":
    "The deployment-gated isolated Python and read-only SQL workflow and its limits.",
  "Artifacts & exports":
    "Review and download supported generated outputs through authenticated workspace routes.",
  "Schedules & automation":
    "Recurring DeepSpace work when scheduler and worker services are enabled.",
  Memory: "Review and manage DeepSpace memory controls and saved facts available to your account.",
  Voice:
    "Optional speech input and spoken responses when the realtime voice services are configured.",
  Collections:
    "Invite members, share selected documents, and collaborate within a collection boundary.",
  "AI providers":
    "Configure supported model providers and understand which features depend on each provider.",
  "MCP connectors":
    "Connect supported remote MCP services and control tool permissions and approvals.",
  "Profile & sessions":
    "Account security, password and two-factor settings, and session management.",
  "Plans, storage & settings":
    "Understand role-based limits, storage usage, retention controls, and account privacy actions.",
  Notifications:
    "In-app notification behavior, user preferences, and deployment-dependent email delivery.",
  "Privacy & security":
    "Tenant and user boundaries, credentials, integrations, and operational limits.",
  "Support centre":
    "Open a ticket, reply to support, attach supported files, and follow its status.",
  "Share feedback":
    "Submit product feedback and follow the status and discussion for your submissions.",
  "Release notes & roadmap":
    "Where to find verified releases and how to submit suggestions; no delivery dates are implied.",
  "Architecture overview":
    "A source-oriented view of the frontend, API, data services, workers, and optional integrations.",
  "System walkthrough":
    "Follow a document from upload to Query or DeepSpace without conflating the two workflows.",
};

export default function DocsIndex() {
  return (
    <DocsShell
      title="AverQel documentation"
      intro="Guides for the complete AverQel workspace. Each product area has one home here, with optional features and deployment requirements called out where they matter."
    >
      {docsNavGroups.map((group) => (
        <section key={group.group} className="space-y-4">
          <h2 className="text-foreground flex items-center gap-3 text-lg font-black tracking-tight">
            <span className="bg-primary h-4 w-1 rounded-full" />
            {group.group}
          </h2>
          <DocsCards
            items={group.items
              .filter((item) => item.href !== "/documentation")
              .map((item) => ({
                title: item.title,
                href: item.href,
                body: descriptions[item.title] ?? `Guide to ${item.title.toLowerCase()}.`,
              }))}
          />
        </section>
      ))}
      <DocsSection title="How to read feature availability">
        <p>
          The interface and backend contain optional integrations, but an available setting does not
          mean the service is configured for every deployment. Provider credentials, OAuth clients,
          workers, schedulers, storage services, malware scanning, email delivery, browser research,
          sandbox execution, and realtime voice can each have separate requirements. The relevant
          guide identifies those dependencies.
        </p>
        <p>
          These guides describe behavior implemented in this repository. They do not certify that a
          particular public deployment has applied its migrations, configured every secret, passed
          staging, or enabled every optional service. Check the deployment&apos;s release evidence
          for those facts.
        </p>
      </DocsSection>
    </DocsShell>
  );
}
