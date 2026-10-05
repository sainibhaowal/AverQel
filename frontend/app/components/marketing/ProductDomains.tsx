"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  Archive,
  ArrowUpRight,
  BellRing,
  Blocks,
  BookOpenCheck,
  BrainCircuit,
  Cable,
  CalendarClock,
  CheckCheck,
  Database,
  FileArchive,
  FileSearch,
  FileText,
  FolderKanban,
  HardDrive,
  KeyRound,
  LifeBuoy,
  LockKeyhole,
  MessageSquareText,
  ScanText,
  SearchCheck,
  Settings2,
  ShieldCheck,
  UsersRound,
  Workflow,
} from "lucide-react";

type Accent = "cyan" | "blue" | "emerald" | "violet" | "amber";

type DomainCard = {
  title: string;
  description: string;
  points: string[];
  icon: LucideIcon;
  accent: Accent;
  href: string;
  linkLabel: string;
  status?: string;
};

type ProductDomain = {
  id: string;
  name: string;
  eyebrow: string;
  title: string;
  description: string;
  cards: DomainCard[];
};

const accentClasses: Record<Accent, { text: string; border: string; background: string }> = {
  cyan: { text: "text-cyan-300", border: "border-cyan-400/25", background: "bg-cyan-400/[0.08]" },
  blue: { text: "text-sky-300", border: "border-sky-400/25", background: "bg-sky-400/[0.08]" },
  emerald: {
    text: "text-emerald-300",
    border: "border-emerald-400/25",
    background: "bg-emerald-400/[0.08]",
  },
  violet: {
    text: "text-violet-300",
    border: "border-violet-400/25",
    background: "bg-violet-400/[0.08]",
  },
  amber: {
    text: "text-amber-300",
    border: "border-amber-400/25",
    background: "bg-amber-400/[0.08]",
  },
};

const productDomains: ProductDomain[] = [
  {
    id: "documents-hub",
    name: "Documents Hub",
    eyebrow: "01 · Source documents",
    title: "Bring documents in, make them usable, and keep them organized.",
    description:
      "Documents Hub owns source files from upload through extraction, indexing, organization, and sharing. Its folders, tags, and document smart collections organize source material here.",
    cards: [
      {
        title: "File intake and extraction",
        description:
          "Upload supported source files and extract searchable text or structured content for workspace use.",
        points: [
          "PDF and common Office files: DOCX, PPTX, XLSX",
          "Text, Markdown, CSV, TSV, JSON, XML, YAML, and notebooks",
          "Image OCR for supported PNG, JPEG, TIFF, WEBP, BMP, and GIF files",
        ],
        icon: FileArchive,
        accent: "cyan",
        href: "/documentation/library",
        linkLabel: "Documents Hub guide",
      },
      {
        title: "Processing you can inspect",
        description:
          "Follow ingestion status and review what the system extracted before relying on a document in a query.",
        points: [
          "Visible parse, chunk, embedding, and indexing states",
          "Preview pages, extracted text, and indexed chunks",
          "Quality signals, quarantine review, and retry paths",
        ],
        icon: ScanText,
        accent: "blue",
        href: "/documentation/library",
        linkLabel: "See the document lifecycle",
      },
      {
        title: "Organization and document automation",
        description:
          "Organize source files in the Documents Hub using document-level tools and saved ways to find them.",
        points: [
          "Folders, tags, saved views, and document smart collections",
          "Classification rules and document automation schedules",
          "Advanced saved views and automation follow workspace permissions",
          "Version history, diffs, and restore where available",
        ],
        icon: FolderKanban,
        accent: "emerald",
        href: "/dashboard/documents/organization",
        linkLabel: "Explore document organization",
      },
      {
        title: "Document actions and sharing",
        description:
          "Work with a source, share it deliberately, and keep related document activity visible.",
        points: [
          "Comments, controlled shares, and expiring share links",
          "Summaries, fact extraction, FAQs, and document comparison",
          "Bulk recovery, exports, and duplicate review",
          "Webhook setup and management require admin permission",
        ],
        icon: Workflow,
        accent: "amber",
        href: "/documentation/library",
        linkLabel: "Review Documents Hub features",
      },
    ],
  },
  {
    id: "query",
    name: "Query",
    eyebrow: "02 · Evidence retrieval",
    title: "Ask questions over sources you are allowed to use.",
    description:
      "Query is AverQel’s retrieval-first answer experience. It searches permitted document context, streams the response, and keeps source evidence visible with the answer.",
    cards: [
      {
        title: "Scoped retrieval",
        description:
          "Choose relevant sources and refine retrieval without crossing the access boundary of your workspace.",
        points: [
          "Filter by selected documents or an accessible collection",
          "Narrow by source type, date, and extraction coverage",
          "Workspace permissions remain in force during retrieval",
        ],
        icon: SearchCheck,
        accent: "blue",
        href: "/documentation/grounded-query",
        linkLabel: "Query guide",
      },
      {
        title: "Answers with evidence",
        description:
          "Inspect the passages supporting a response instead of treating a generated answer as an untraceable result.",
        points: [
          "Stream answers as they are produced",
          "Review citations, source snippets, and relevance signals",
          "Use supported structured outputs and follow-up prompts",
          "Send feedback on citation quality",
        ],
        icon: BookOpenCheck,
        accent: "cyan",
        href: "/documentation/grounded-query",
        linkLabel: "How grounded answers work",
      },
      {
        title: "Query conversations",
        description:
          "Return to persisted Query conversations and manage the history associated with this answer workflow.",
        points: [
          "Conversation history belongs to Query",
          "Edit or regenerate supported messages and manage conversations",
          "Review and provide feedback on source citations",
          "Query remains distinct from DeepSpace agent runs and Library files",
        ],
        icon: MessageSquareText,
        accent: "violet",
        href: "/dashboard/query",
        linkLabel: "Open Query",
      },
    ],
  },
  {
    id: "collections",
    name: "Collections",
    eyebrow: "03 · Shared project space",
    title: "Share selected sources with people you invite.",
    description:
      "Collections are explicit membership spaces for project documents and collaboration. They are a separate product area from Documents Hub’s document smart collections.",
    cards: [
      {
        title: "Membership and source access",
        description:
          "Keep project access scoped to the people and material approved for that collection.",
        points: [
          "Collection owners manage invites and membership",
          "Join requests require owner approval",
          "Shared sources are governed by collection and document access",
        ],
        icon: UsersRound,
        accent: "emerald",
        href: "/documentation/collections-sharing",
        linkLabel: "Collections guide",
        status: "Experimental beta",
      },
      {
        title: "Project conversation and media",
        description:
          "Keep messages and supported collection media with the project context they belong to.",
        points: [
          "Collection chat, reactions, and presence features",
          "Supported attachment sharing within the collection",
          "Device verification and security details are documented in the guide",
        ],
        icon: MessageSquareText,
        accent: "cyan",
        href: "/documentation/collections-sharing",
        linkLabel: "Review collaboration details",
        status: "Experimental beta",
      },
      {
        title: "One source, shared deliberately",
        description:
          "Add an existing document to a collection so its members can work from the same source.",
        points: [
          "Access is checked against collection membership",
          "Query can use a collection only when the member has permission",
          "Tenant and membership boundaries remain in force for shared sources",
        ],
        icon: LockKeyhole,
        accent: "violet",
        href: "/documentation/collections-sharing",
        linkLabel: "Understand collection access",
        status: "Experimental beta",
      },
      {
        title: "Member security and alerts",
        description:
          "Use member-facing collection safety and device controls for collaboration where enabled.",
        points: [
          "Manage registered devices and encryption setup",
          "Block or report a member from a collection",
          "Configure supported collection notification subscriptions",
        ],
        icon: ShieldCheck,
        accent: "amber",
        href: "/documentation/collections-sharing",
        linkLabel: "Collection security guide",
        status: "Experimental beta",
      },
    ],
  },
  {
    id: "deepspace",
    name: "DeepSpace",
    eyebrow: "04 · Research and deliverables",
    title: "Continue a task from research through saved work.",
    description:
      "DeepSpace is the durable AI work area. Its conversations, agent runs, Memory, working Library, artifacts, sandbox, and schedules all belong to this product area.",
    cards: [
      {
        title: "Agent conversations and runs",
        description:
          "Work through longer tasks in DeepSpace conversations with run state that can survive interruptions.",
        points: [
          "Pause, resume, steer, retry, or cancel supported runs",
          "Review queued work and approval requests",
          "Attach relevant files to a task where supported",
          "Conversation and run state stays separate from Query history",
        ],
        icon: Activity,
        accent: "violet",
        href: "/documentation/simple-system-walkthrough",
        linkLabel: "DeepSpace workflow guide",
      },
      {
        title: "DeepSpace Memory",
        description: "Review and manage saved context used to make continuing work more useful.",
        points: [
          "Inspect and search saved memory",
          "Edit or remove saved facts and preferences",
          "Some memory candidates can require approval",
        ],
        icon: BrainCircuit,
        accent: "blue",
        href: "/documentation/memory-workspace",
        linkLabel: "Memory guide",
      },
      {
        title: "DeepSpace Library",
        description:
          "Keep notes, working files, and deliverables close to DeepSpace work. This Library is separate from source documents in Documents Hub.",
        points: [
          "Create folders and save or upload working files",
          "Preview and edit supported text and office formats",
          "Manage file versions and export workspace files",
        ],
        icon: Archive,
        accent: "cyan",
        href: "/documentation/editor-files",
        linkLabel: "DeepSpace Library guide",
      },
      {
        title: "Research and isolated analysis",
        description:
          "Use supported research and bounded analysis tools as part of a DeepSpace task.",
        points: [
          "Evidence-oriented web research where enabled",
          "Python or SQL execution through a separately isolated sandbox",
          "Availability depends on the configured deployment services",
        ],
        icon: FileSearch,
        accent: "emerald",
        href: "/documentation/web-research",
        linkLabel: "Research and sandbox guides",
      },
      {
        title: "Artifacts and exports",
        description:
          "Keep useful outputs from DeepSpace work available as reviewable artifacts and exports.",
        points: [
          "Structured answers and supported generated media",
          "Save or export deliverables when the output supports it",
          "Provider capabilities determine which media formats are available",
        ],
        icon: FileText,
        accent: "amber",
        href: "/documentation/artifacts",
        linkLabel: "Artifacts and exports guide",
      },
      {
        title: "Schedules and voice",
        description:
          "Extend DeepSpace work with recurring prompts or voice features when the deployment supports them.",
        points: [
          "Create, pause, and inspect schedule runs",
          "Recurring execution needs the configured worker and scheduler services",
          "Voice and realtime features are deployment-gated",
        ],
        icon: CalendarClock,
        accent: "blue",
        href: "/documentation/automation",
        linkLabel: "Schedules and voice guides",
      },
      {
        title: "Datasets and derived analysis",
        description:
          "Work with supported tabular files inside DeepSpace and save useful derived results with the task.",
        points: [
          "Page through and query supported CSV or spreadsheet data",
          "Run bounded aggregates and supported joins",
          "Create charts and save derived files to the DeepSpace Library",
        ],
        icon: Database,
        accent: "emerald",
        href: "/documentation/editor-files",
        linkLabel: "DeepSpace file and dataset guide",
      },
    ],
  },
  {
    id: "providers",
    name: "AI Providers",
    eyebrow: "05 · Model connections",
    title: "Choose and manage the models used by workspace features.",
    description:
      "Provider configuration is its own shared platform area. Query and DeepSpace use assigned provider roles; provider setup does not itself connect an external app or grant MCP tool access.",
    cards: [
      {
        title: "Provider configuration",
        description:
          "Connect supported cloud or local model services using the provider settings available to your workspace.",
        points: [
          "Configure supported local or hosted provider types and model endpoints",
          "Use supported OAuth or secret-based setup for the selected provider",
          "Secrets are returned in masked form in provider views",
          "Provider availability depends on valid credentials and service health",
        ],
        icon: Settings2,
        accent: "blue",
        href: "/documentation/providers",
        linkLabel: "Provider setup guide",
      },
      {
        title: "Model roles and capabilities",
        description:
          "Assign compatible models to supported workspace tasks and inspect their reported capabilities.",
        points: [
          "Chat, embeddings, reranking, and web-search support where available",
          "Model discovery and preview for supported providers",
          "Assignments determine which runtime features can use a model",
        ],
        icon: Blocks,
        accent: "cyan",
        href: "/dashboard/settings/providers",
        linkLabel: "Manage provider assignments",
      },
      {
        title: "Connection health",
        description:
          "Check configured provider health and review the operational status available to your account.",
        points: [
          "Test and refresh supported model listings",
          "Review provider health and capability status",
          "Missing credentials or provider outages remain visible setup requirements",
        ],
        icon: Activity,
        accent: "emerald",
        href: "/documentation/providers",
        linkLabel: "Provider operations guide",
      },
    ],
  },
  {
    id: "mcp",
    name: "MCP Servers",
    eyebrow: "06 · Approved external tools",
    title: "Connect supported tools with explicit access and action controls.",
    description:
      "MCP manages approved server connections and their tools. A catalog entry, supported authorization, connection policy, and any required action approval are part of the flow.",
    cards: [
      {
        title: "Curated marketplace",
        description:
          "Discover reviewed catalog entries and inspect the available server and tool information.",
        points: [
          "Connections start from approved catalog entries",
          "Inspect supported tools and connection requirements",
          "Arbitrary endpoint registration is not part of this release",
        ],
        icon: Cable,
        accent: "cyan",
        href: "/documentation/connectors-mcp",
        linkLabel: "MCP guide",
      },
      {
        title: "Authorization and connection health",
        description:
          "Authorize a supported server and manage the user-owned connection from the MCP area.",
        points: [
          "Provider-specific OAuth or setup requirements apply",
          "Inspect tools in the MCP Inspector; refresh or disconnect connections",
          "Live use depends on deployment credentials and external service health",
        ],
        icon: KeyRound,
        accent: "blue",
        href: "/dashboard/mcp",
        linkLabel: "Open MCP servers",
      },
      {
        title: "Tool policies and approvals",
        description:
          "Review what a connected tool can do before making it available to an AI workflow.",
        points: [
          "Server and tool policies control availability",
          "Read-only restrictions and approvals apply to side-effecting actions",
          "Connections can be scoped to DeepSpace or a supported conversation",
        ],
        icon: ShieldCheck,
        accent: "amber",
        href: "/documentation/connectors-mcp",
        linkLabel: "Understand MCP policies",
      },
    ],
  },
  {
    id: "workspace-controls",
    name: "Workspace controls",
    eyebrow: "07 · Account, trust, and help",
    title: "Manage your account and find help in one place.",
    description:
      "These account and help resources apply across the workspace, so they stay together without mixing into product-specific workflows.",
    cards: [
      {
        title: "Profile and sign-in",
        description: "Review your profile and available account security and session settings.",
        points: [
          "Manage account profile information",
          "Review sign-in security and active sessions",
          "Controls depend on your account and workspace configuration",
        ],
        icon: LockKeyhole,
        accent: "cyan",
        href: "/documentation/profile",
        linkLabel: "Account guide",
      },
      {
        title: "Plan and storage",
        description:
          "Review the plan assigned to your account and inspect workspace storage usage.",
        points: [
          "Check plan limits and current storage usage",
          "Inspect usage across files, chats, Memory, queues, and activity",
          "Available account actions follow your assigned permissions",
        ],
        icon: HardDrive,
        accent: "emerald",
        href: "/dashboard/settings",
        linkLabel: "Open workspace settings",
      },
      {
        title: "Trust and privacy",
        description:
          "Understand how account security, privacy, retention, and workspace access are handled.",
        points: [
          "Review privacy, retention, and security policies",
          "Manage account security and linked sessions",
          "Access follows your authenticated account scope",
        ],
        icon: LockKeyhole,
        accent: "cyan",
        href: "/documentation/privacy-security",
        linkLabel: "Trust and privacy details",
      },
      {
        title: "Notifications",
        description:
          "Review workspace updates and choose notification preferences available to your account.",
        points: [
          "Read and dismiss in-app notifications",
          "Set digest preferences and mute supported notification domains",
          "Email delivery depends on deployment configuration",
        ],
        icon: BellRing,
        accent: "blue",
        href: "/dashboard/settings/notifications",
        linkLabel: "Manage notification preferences",
      },
      {
        title: "Support and feedback",
        description: "Ask for help or send product feedback through the user-facing support areas.",
        points: [
          "Reply to support tickets and attach supported files",
          "Submit feedback, continue the conversation, and review status",
          "Help and feedback are available to signed-in users",
        ],
        icon: LifeBuoy,
        accent: "violet",
        href: "/documentation/support",
        linkLabel: "Support and feedback guide",
      },
    ],
  },
];

export default function ProductDomains() {
  return (
    <div aria-label="AverQel product areas">
      {productDomains.map((domain, domainIndex) => (
        <motion.section
          key={domain.id}
          id={domain.id}
          aria-labelledby={`${domain.id}-heading`}
          initial={{ opacity: 0, y: 18 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ duration: 0.45, delay: domainIndex === 0 ? 0 : 0.02 }}
          className="landing-trace-frame relative scroll-mt-8 border-t border-white/[0.055] py-16 sm:py-20 lg:py-24"
        >
          <div className="relative mx-auto w-full max-w-[1800px] px-4 sm:px-8 lg:px-12">
            <header className="mb-8 max-w-4xl sm:mb-10">
              <p className="text-primary/80 text-[11px] font-bold tracking-[0.3em] uppercase">
                {domain.eyebrow}
              </p>
              <h2
                id={`${domain.id}-heading`}
                className="mt-3 [font-family:var(--font-landing-display),var(--font-display),var(--font-inter),sans-serif] text-3xl leading-tight font-semibold tracking-[-0.02em] text-white sm:text-4xl lg:text-5xl"
              >
                {domain.title}
              </h2>
              <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-400 sm:text-base sm:leading-8">
                {domain.description}
              </p>
            </header>

            <div className="grid auto-rows-fr gap-4 md:grid-cols-2 2xl:grid-cols-3">
              {domain.cards.map((card, cardIndex) => {
                const Icon = card.icon;
                const accent = accentClasses[card.accent];
                return (
                  <motion.article
                    key={card.title}
                    initial={{ opacity: 0, y: 14 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, margin: "-60px" }}
                    transition={{ duration: 0.35, delay: Math.min(cardIndex * 0.035, 0.1) }}
                    className="theme-panel flex h-full min-w-0 flex-col rounded-2xl border border-white/[0.08] p-5 transition-colors duration-300 hover:border-white/[0.16] sm:p-6"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <span
                        className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border ${accent.border} ${accent.background} ${accent.text}`}
                        aria-hidden="true"
                      >
                        <Icon size={18} />
                      </span>
                      {card.status && (
                        <span className="rounded-full border border-amber-300/20 bg-amber-300/[0.07] px-2.5 py-1 text-[10px] font-semibold text-amber-200">
                          {card.status}
                        </span>
                      )}
                    </div>
                    <h3 className="mt-5 text-lg font-bold tracking-tight text-white sm:text-xl">
                      {card.title}
                    </h3>
                    <p className="mt-2 text-sm leading-6 text-slate-400">{card.description}</p>
                    <ul className="mt-4 flex-1 space-y-2.5 border-t border-white/[0.06] pt-4">
                      {card.points.map((point) => (
                        <li key={point} className="flex gap-2.5 text-xs leading-5 text-slate-300">
                          <CheckCheck
                            size={14}
                            className={`mt-0.5 shrink-0 ${accent.text}`}
                            aria-hidden="true"
                          />
                          <span>{point}</span>
                        </li>
                      ))}
                    </ul>
                    <Link
                      href={card.href}
                      className={`mt-5 inline-flex w-fit items-center gap-1.5 text-xs font-bold ${accent.text} transition-colors hover:text-white focus-visible:ring-2 focus-visible:ring-cyan-300/70 focus-visible:outline-none`}
                    >
                      {card.linkLabel}
                      <ArrowUpRight size={14} aria-hidden="true" />
                    </Link>
                  </motion.article>
                );
              })}
            </div>
          </div>
        </motion.section>
      ))}
    </div>
  );
}
