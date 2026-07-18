"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight,
  BellRing,
  Binary,
  Database,
  Layers3,
  MessageSquareText,
  Network,
  NotebookPen,
  ShieldCheck,
  Terminal,
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
    eyebrow: "Command Surface",
    title: "Grounded Chat & Query",
    icon: MessageSquareText,
    accent: "blue",
    description:
      "Start with grounded answers, broad planning, citations, and live workspace-aware questioning before escalating into heavier DeepSpace execution.",
    bullets: [
      "Grounded answers tied to source evidence",
      "Broad-task planning with model-aware routing",
      "Normal chat and agentic work stay connected",
    ],
  },
  {
    eyebrow: "Execution Surface",
    title: "DeepSpace",
    icon: Terminal,
    accent: "violet",
    description:
      "Run durable-first agentic missions with PostgreSQL-backed state, streamed plans, checkpoints, approvals, memory, verification, repair, and bounded continuation epochs.",
    bullets: [
      "Live SSE timeline, active tool trace, and mission stream",
      "Approval gates for writes, shell actions, and risky operations",
      "Context meter, auto-compaction, rewind, and export controls",
      "Restart recovery, final-answer persistence, event replay, and cursor reconnect",
      "Explicit time, token, cost, retry, concurrency, side-effect, and risk budgets",
    ],
  },
  {
    eyebrow: "Visibility Surface",
    title: "Mission Canvas + Orchestration",
    icon: Binary,
    accent: "emerald",
    description:
      "Inspect the actual mission structure instead of guessing. Lane activity, approvals, planner posture, hook state, diagnostics, and delegated work become visible in the UI.",
    bullets: [
      "Inline mission canvas inside DeepSpace threads",
      "Live orchestration control room for active missions",
      "Lane-level diagnostics, dependencies, and approval queue",
    ],
  },
  {
    eyebrow: "Workspace Surface",
    title: "Editor + Files",
    icon: NotebookPen,
    accent: "blue",
    description:
      "Move from chat into a real working surface with split layout, file-aware tasks, drafts, exports, and note-driven execution support.",
    bullets: [
      "Split chat-plus-notes workflow",
      "Markdown, math blocks, and exportable notes",
      "File-aware editing for repo and document tasks",
    ],
  },
  {
    eyebrow: "Review Surface",
    title: "Memory + Proactive Workspace",
    icon: Layers3,
    accent: "emerald",
    description:
      "Keep recurring rules, durable task state, saved memory, connector-driven follow-ups, and background work alive after the live conversation ends.",
    bullets: [
      "Recurring rules and draft queue",
      "Task ledger, memory facts, and proactive follow-up",
      "Connector coverage and live runtime health",
    ],
  },
  {
    eyebrow: "Runtime Surface",
    title: "Connectors + Providers",
    icon: Network,
    accent: "violet",
    description:
      "Attach live external systems and choose the runtime stack behind the work, from cloud providers to local models and web tooling.",
    bullets: [
      "GitHub, Drive, Gmail, Calendar, Notion, Slack, web tools",
      "OpenRouter, Anthropic, Google, OpenAI-compatible, Ollama, LM Studio",
      "Tenant-scoped configuration with masked secrets and health visibility",
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
};

const guarantees = [
  { icon: ShieldCheck, text: "Tenant-isolated" },
  { icon: CheckCircle2, text: "Approval-gated" },
  { icon: Database, text: "Session-persistent" },
  { icon: TimerReset, text: "Auto-compaction aware" },
  { icon: BellRing, text: "Proactive notifications" },
  { icon: Workflow, text: "Connector automation" },
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
            The landing page now maps the real product surfaces users actually work in
          </h2>
          <p className={landingSectionLeadClass}>
            AverQel is no longer only a single chat interface. It now spans grounded query, the
            DeepSpace execution runtime, inline mission canvas visibility, orchestration oversight,
            editor-plus-files workflows, durable memory, proactive follow-up, connectors, and
            provider control across cloud and local runtimes.
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
              DeepSpace, mission canvas diagnostics, the orchestration control room, the workspace
              editor, proactive follow-up, connectors, provider control, and the security model that
              keeps them isolated. Capacity depends on the selected provider and deployment
              resources, so production rollout should be validated against the expected workload.
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
