"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight,
  Activity,
  Cable,
  Database,
  FileText,
  FolderKanban,
  MessageSquareText,
  Network,
  NotebookPen,
  ShieldCheck,
  Workflow,
  CheckCircle2,
  TimerReset,
} from "lucide-react";
import { useLandingSectionMotion } from "./landingMotion";
import {
  landingContentClass,
  landingEyebrowClass,
  landingHeaderWrapClass,
  landingSectionLeadClass,
  landingSectionShellClass,
  landingSectionTitleClass,
  landingTitleGradientBySection,
} from "./landingType";

const surfaces = [
  {
    eyebrow: "Document Surface",
    title: "Documents Hub",
    icon: FileText,
    accent: "cyan",
    description:
      "Bring supported files into one private workspace. Follow processing progress, inspect extracted text and chunks, review document state, and download the original file.",
    bullets: [
      "Upload, processing progress, retry, and reingest support",
      "Document text, chunks, versions, and extraction signals",
      "A source workspace for grounded questions and notes",
    ],
  },
  {
    eyebrow: "Retrieval Surface",
    title: "Grounded Query",
    icon: MessageSquareText,
    accent: "blue",
    description:
      "Ask evidence-backed questions over the documents you can access. Results stay connected to source material, citations, and inspection flows.",
    bullets: [
      "Grounded answers tied to source evidence",
      "Rich answers, diagrams, charts, and structured output",
      "Save selected research into DeepSpace notes",
    ],
  },
  {
    eyebrow: "Organization Surface",
    title: "Collections",
    icon: FolderKanban,
    accent: "emerald",
    description:
      "Create focused document sets for projects, teams, or topics. Collection ownership and sharing rules keep the scope deliberate rather than making all content globally visible.",
    bullets: [
      "Focused reusable document groups",
      "Explicit invitations and owner-controlled access",
      "Distinct roles and selective document inclusion",
    ],
  },
  {
    eyebrow: "Execution Surface",
    title: "DeepSpace",
    icon: Activity,
    accent: "violet",
    description:
      "Use DeepSpace as a focused productivity chat for research, drafting, analysis, memory, and safe tool-assisted work.",
    bullets: [
      "Streaming answers and saved conversation history",
      "Approval gates for external actions and risky operations",
      "Notes, exports, memory, and provider controls",
      "Tenant-scoped persistence after reload",
    ],
  },
  {
    eyebrow: "Deliverable Surface",
    title: "Notes + Exports",
    icon: NotebookPen,
    accent: "blue",
    description:
      "Move from chat into a real working surface with split layout, drafts, exports, and note-driven execution support.",
    bullets: [
      "Split chat-plus-notes workflow",
      "Markdown, math blocks, and exportable notes",
      "Research drafting, notes, and document deliverables",
    ],
  },
  {
    eyebrow: "Integration Surface",
    title: "MCP Connections",
    icon: Cable,
    accent: "amber",
    description:
      "Authorize supported remote apps through OAuth. Each external tool is checked for ownership, connection health, catalog freshness, policy, and approval before use.",
    bullets: [
      "Supported apps such as GitHub, Drive, Gmail, Calendar, Notion, and Slack",
      "Per-tool permissions, read-only mode, risk limits, and approvals",
      "Connection status and health are visible, not assumed",
    ],
  },
  {
    eyebrow: "Runtime Surface",
    title: "Providers",
    icon: Network,
    accent: "rose",
    description:
      "Choose the configured cloud or local runtime behind your work. Provider credentials are private to the account that adds them and are not exposed in the interface.",
    bullets: [
      "Cloud and local routes for chat, retrieval, and web work",
      "OpenRouter, Anthropic, Google, OpenAI-compatible, Ollama, and LM Studio",
      "Masked credentials, health visibility, and capability-aware selection",
    ],
  },
];

const accentStyles: Record<
  string,
  { border: string; bg: string; glow: string; text: string; chip: string }
> = {
  blue: {
    border: "border-blue-400/20",
    bg: "bg-blue-500/[0.08]",
    glow: "bg-blue-500/[0.08]",
    text: "text-blue-300",
    chip: "bg-blue-500/[0.08] border-blue-400/20 text-blue-200",
  },
  violet: {
    border: "border-violet-400/20",
    bg: "bg-violet-500/[0.08]",
    glow: "bg-violet-500/[0.08]",
    text: "text-violet-300",
    chip: "bg-violet-500/[0.08] border-violet-400/20 text-violet-200",
  },
  emerald: {
    border: "border-emerald-400/20",
    bg: "bg-emerald-500/[0.08]",
    glow: "bg-emerald-500/[0.08]",
    text: "text-emerald-300",
    chip: "bg-emerald-500/[0.08] border-emerald-400/20 text-emerald-200",
  },
  amber: {
    border: "border-amber-400/20",
    bg: "bg-amber-500/[0.08]",
    glow: "bg-amber-500/[0.08]",
    text: "text-amber-300",
    chip: "bg-amber-500/[0.08] border-amber-400/20 text-amber-100",
  },
  cyan: {
    border: "border-cyan-400/20",
    bg: "bg-cyan-500/[0.08]",
    glow: "bg-cyan-500/[0.08]",
    text: "text-cyan-300",
    chip: "bg-cyan-500/[0.08] border-cyan-400/20 text-cyan-100",
  },
  rose: {
    border: "border-rose-400/20",
    bg: "bg-rose-500/[0.08]",
    glow: "bg-rose-500/[0.08]",
    text: "text-rose-300",
    chip: "bg-rose-500/[0.08] border-rose-400/20 text-rose-100",
  },
};

const guarantees = [
  { icon: ShieldCheck, text: "Tenant-isolated" },
  { icon: CheckCircle2, text: "Approval-gated" },
  { icon: Database, text: "Session-persistent" },
  { icon: TimerReset, text: "Reload-recoverable" },
  { icon: Workflow, text: "Policy-controlled" },
];

export default function PlatformSurfaces() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 18,
    scaleRange: [0.993, 1.008],
  });

  return (
    <motion.section
      ref={ref}
      style={style}
      id="platform-surfaces"
      className={landingSectionShellClass}
    >
      <div className={landingContentClass}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ type: "spring", stiffness: 100, damping: 20 }}
          className={landingHeaderWrapClass}
        >
          <p className={landingEyebrowClass}>Current Production Surfaces</p>
          <h2
            className={`${landingSectionTitleClass} ${landingTitleGradientBySection.platformSurfaces}`}
          >
            Six connected surfaces for document-first AI work
          </h2>
          <p className={landingSectionLeadClass}>
            Start with documents and evidence, then move into DeepSpace for deeper work.
            Collections, MCP connections, and provider control remain visible parts of the same
            workspace.
          </p>
        </motion.div>

        <div className="grid gap-5 md:grid-cols-2 2xl:grid-cols-3">
          {surfaces.map((surface, index) => {
            const Icon = surface.icon;
            const accent = accentStyles[surface.accent];

            return (
              <motion.article
                key={surface.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{
                  type: "spring",
                  stiffness: 80,
                  damping: 18,
                  delay: index * 0.06,
                }}
                whileHover={{ y: -6 }}
                className="group theme-panel relative overflow-hidden rounded-2xl border p-4 transition-all duration-500 hover:border-white/[0.14] hover:shadow-[0_24px_70px_rgba(0,0,0,0.26)] sm:p-6 lg:p-7"
              >
                <div
                  className={`pointer-events-none absolute -top-16 -right-16 h-44 w-44 rounded-full ${accent.glow} opacity-0 blur-[90px] transition-opacity group-hover:opacity-100`}
                />
                <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(135deg,rgba(255,255,255,0.05),transparent_24%,transparent_72%,rgba(255,255,255,0.02))] opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
                <div className="relative">
                  <div className="mb-5 flex items-start justify-between gap-4">
                    <div className="min-w-0">
                      <motion.p
                        className="text-muted-foreground text-[10px] font-bold tracking-[0.28em] uppercase"
                        transition={{ duration: 0.28 }}
                      >
                        {surface.eyebrow}
                      </motion.p>
                      <motion.h3
                        className="text-foreground mt-2 text-xl font-black tracking-tight transition-colors duration-300 group-hover:text-white sm:text-2xl"
                        transition={{ type: "spring", stiffness: 240, damping: 18 }}
                      >
                        {surface.title}
                      </motion.h3>
                    </div>
                    <motion.div
                      className={`flex h-12 w-12 items-center justify-center rounded-2xl border ${accent.border} ${accent.bg}`}
                      transition={{ type: "spring", stiffness: 260, damping: 18 }}
                      whileHover={{ scale: 1.06, rotate: -4 }}
                    >
                      <Icon
                        size={20}
                        className={`${accent.text} transition-transform duration-300 group-hover:scale-110`}
                      />
                    </motion.div>
                  </div>

                  <p className="text-muted-foreground text-sm leading-6 transition-colors duration-300 group-hover:text-slate-300 sm:leading-7">
                    {surface.description}
                  </p>

                  <div className="mt-6 space-y-2.5">
                    {surface.bullets.map((bullet, bulletIndex) => (
                      <motion.div
                        key={bullet}
                        className={`border-glass-border bg-surface-1 relative flex items-start gap-2.5 overflow-hidden rounded-xl border px-3.5 py-3 ${accent.chip} transition-all duration-300 group-hover:border-white/[0.08]`}
                        initial={false}
                        whileHover={{ x: 4 }}
                        transition={{
                          type: "spring",
                          stiffness: 240,
                          damping: 18,
                          delay: bulletIndex * 0.02,
                        }}
                      >
                        <span className="pointer-events-none absolute inset-y-0 left-0 w-[3px] scale-y-0 rounded-full bg-current opacity-70 transition-transform duration-300 group-hover:scale-y-100" />
                        <CheckCircle2
                          size={14}
                          className={`mt-0.5 shrink-0 ${accent.text} transition-all duration-300 group-hover:scale-110 group-hover:drop-shadow-[0_0_8px_currentColor]`}
                        />
                        <span className="text-xs leading-5 transition-transform duration-300 group-hover:translate-x-0.5">
                          {bullet}
                        </span>
                      </motion.div>
                    ))}
                  </div>
                </div>
              </motion.article>
            );
          })}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
          className="mt-5 grid gap-5 xl:grid-cols-[1.05fr_0.95fr]"
        >
          <div className="border-glass-border theme-panel rounded-2xl border p-4 sm:p-5 lg:p-6">
            <p className="text-primary/80 text-[11px] font-bold tracking-[0.3em] uppercase">
              Runtime Commitments
            </p>
            <div className="mt-4 flex flex-wrap gap-2.5">
              {guarantees.map((item) => {
                const Icon = item.icon;
                return (
                  <div
                    key={item.text}
                    className="bg-surface-0 border-glass-border text-muted-foreground flex items-center gap-2 rounded-full border px-3.5 py-2 text-xs font-semibold shadow-sm"
                  >
                    <Icon size={13} className="text-primary" />
                    {item.text}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="border-glass-border bg-surface-0 rounded-2xl border p-4 sm:p-5 lg:p-6">
            <p className="text-foreground text-sm font-bold">Live from the current build</p>
            <p className="text-muted-foreground mt-2 text-sm leading-6 sm:leading-7">
              The homepage points users toward the actual shipped surfaces: grounded query,
              DeepSpace, the workspace editor, memory, connectors, provider control, and the
              security model that keeps them isolated.
            </p>
            <Link
              href="/documentation"
              className="text-primary mt-4 inline-flex items-center gap-2 text-sm font-bold"
            >
              Read the current product docs
              <ArrowRight size={14} />
            </Link>
          </div>
        </motion.div>
      </div>
    </motion.section>
  );
}
