"use client";

import { motion } from "framer-motion";
import type { SVGProps } from "react";
import {
  ShieldCheck,
  Slack,
  Github,
  Mail,
  Calendar,
  Cpu,
  Activity,
  Heart,
  Bot,
} from "lucide-react";
import { useLandingSectionMotion } from "./landingMotion";
import {
  landingContentClass,
  landingHeaderWrapClass,
  landingFeatureTitleClass,
  landingSectionLeadClass,
  landingSectionShellClass,
  landingSectionTitleClass,
  landingTitleGradientBySection,
} from "./landingType";

const agents = [
  {
    name: "Research Agent",
    role: "Deep Web & Fact Checking",
    color: "from-blue-500 to-cyan-400",
    accent: "#38bdf8",
    iconKey: "research",
    description:
      "Autonomously crawls, fetches, verifies, and summarizes live web content with streamed progress, source evidence, and mission-level traceability.",
  },
  {
    name: "Analyst Agent",
    role: "Data & Spreadsheet Mastery",
    color: "from-emerald-500 to-teal-400",
    accent: "#14f1b2",
    iconKey: "analyst",
    description:
      "Processes CSV, JSON, Excel, and text data into summaries, tables, diagnostics, and workflow-ready findings across long-running tasks.",
  },
  {
    name: "Executor Agent",
    role: "Stateful System Control",
    color: "from-amber-500 to-orange-400",
    accent: "#ffb11f",
    iconKey: "executor",
    description:
      "Runs builds, streams shell output, and performs surgical code edits directly in your workspace with approval-aware execution control.",
  },
  {
    name: "Connector Agent",
    role: "Workflow Orchestrator",
    color: "from-violet-500 to-purple-400",
    accent: "#b772ff",
    iconKey: "connector",
    description:
      "Scans Gmail, Calendar, Notion, Drive, Slack, and GitHub so the right connector or external handoff is used automatically or with approval.",
  },
];

const integrations = [
  { icon: Slack, label: "Slack", status: "Active" },
  { icon: Github, label: "GitHub", status: "Streaming" },
  { icon: Mail, label: "Gmail", status: "Heartbeat" },
  { icon: Calendar, label: "Calendar", status: "Ready" },
  { icon: Cpu, label: "Ollama / LM Studio", status: "Available" },
];

type AgentIconKey = "research" | "analyst" | "executor" | "connector";

function ResearchVectorIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true" {...props}>
      <circle cx="24" cy="24" r="13.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M10.5 24h27" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path
        d="M24 10.5c4.2 4.4 6.3 8.9 6.3 13.5S28.2 33.1 24 37.5c-4.2-4.4-6.3-8.9-6.3-13.5S19.8 14.9 24 10.5Z"
        stroke="currentColor"
        strokeWidth="1.8"
      />
      <path
        d="M14.8 16.2c2.8 1.8 5.9 2.7 9.2 2.7 3.3 0 6.4-.9 9.2-2.7"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        opacity=".65"
      />
      <path
        d="M14.8 31.8c2.8-1.8 5.9-2.7 9.2-2.7 3.3 0 6.4.9 9.2 2.7"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        opacity=".65"
      />
    </svg>
  );
}

function AnalystVectorIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true" {...props}>
      <path
        d="M9 30c3.8 0 3.8-12 7.6-12s3.8 17 7.6 17 3.8-24 7.6-24S35.6 24 39 24"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M10 37h28"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        opacity=".55"
      />
      <circle cx="16.6" cy="18" r="2" fill="currentColor" />
      <circle cx="24.2" cy="35" r="2" fill="currentColor" opacity=".9" />
      <circle cx="31.8" cy="11" r="2" fill="currentColor" opacity=".75" />
    </svg>
  );
}

function ExecutorVectorIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true" {...props}>
      <path
        d="M12 16l8 8-8 8"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M24 32h12" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
      <rect
        x="8.5"
        y="10.5"
        width="31"
        height="27"
        rx="7"
        stroke="currentColor"
        strokeWidth="1.6"
        opacity=".4"
      />
      <path
        d="M28 19h8"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        opacity=".7"
      />
    </svg>
  );
}

function ConnectorVectorIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 48 48" fill="none" aria-hidden="true" {...props}>
      <rect x="11" y="14" width="26" height="20" rx="5" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M14 18l10 8 10-8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M16 31h16"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        opacity=".55"
      />
    </svg>
  );
}

const vectorIcons = {
  research: ResearchVectorIcon,
  analyst: AnalystVectorIcon,
  executor: ExecutorVectorIcon,
  connector: ConnectorVectorIcon,
} as const;

function AgentVectorBadge({
  iconKey,
  accent,
  glow,
}: {
  iconKey: AgentIconKey;
  accent: string;
  glow: string;
}) {
  const Icon = vectorIcons[iconKey];

  return (
    <div className="relative mb-6 h-14 w-14">
      <motion.div
        aria-hidden="true"
        className={`absolute inset-0 rounded-[1.1rem] bg-gradient-to-br ${glow} opacity-95`}
        animate={{
          boxShadow: [`0 0 0 rgba(0,0,0,0)`, `0 0 24px ${accent}33`, `0 0 0 rgba(0,0,0,0)`],
        }}
        transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut" }}
      />
      <div className="absolute inset-[1px] rounded-[1rem] border border-white/10 bg-[linear-gradient(180deg,rgba(8,12,18,0.92),rgba(4,8,12,0.82))]" />
      <div
        className="absolute inset-[6px] rounded-[0.85rem] border"
        style={{
          borderColor: `${accent}44`,
          background: `linear-gradient(180deg, ${accent}20 0%, rgba(5,10,14,0.2) 100%)`,
        }}
      />
      <motion.div
        className="absolute inset-0 flex items-center justify-center"
        whileHover={{ scale: 1.06 }}
        transition={{ type: "spring", stiffness: 260, damping: 18 }}
      >
        <Icon className="h-7 w-7" style={{ color: accent }} />
      </motion.div>
      <motion.div
        aria-hidden="true"
        className="absolute top-2 left-2 h-2 w-2 rounded-full"
        style={{ backgroundColor: accent }}
        animate={{ opacity: [0.45, 1, 0.45] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
      />
    </div>
  );
}

export default function AutonomousAgenticShowcase() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 16,
    scaleRange: [0.994, 1.008],
  });
  const typedAgents = agents as Array<(typeof agents)[number] & { iconKey: AgentIconKey }>;

  return (
    <motion.section ref={ref} style={style} className={landingSectionShellClass}>
      <div className={landingContentClass}>
        <div className={`${landingHeaderWrapClass} max-w-2xl sm:mb-20`}>
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true, margin: "-50px" }}
            transition={{ type: "spring", stiffness: 100, damping: 20 }}
            className="border-primary/20 bg-primary/10 text-primary mb-6 inline-flex items-center gap-2 rounded-full border px-4 py-1.5 text-[10px] font-bold tracking-[0.2em] uppercase sm:text-[11px]"
          >
            <Bot size={14} />
            The DeepSpace Workforce
          </motion.div>
          <h2 className={`${landingSectionTitleClass} ${landingTitleGradientBySection.autonomous}`}>
            Specialized agents and mission lanes <br className="hidden sm:block" /> on demand
          </h2>
          <p className={landingSectionLeadClass}>
            AverQel isn&apos;t a chatbot wrapper. It&apos;s a durable hierarchical production runtime that
            spawns specialized sub-agents, checkpoints every step, survives browser and worker
            restarts, and keeps workflow state, approvals, replay, and audit logs aligned with the
            live UI through DeepSpace and the mission canvas.
          </p>
        </div>

        {/* Agent Cards - Optimized for 120fps */}
        <div className="mb-16 grid grid-cols-1 gap-5 sm:mb-28 sm:grid-cols-2 lg:grid-cols-4">
          {typedAgents.map((agent, i) => (
            <motion.div
              key={agent.name}
              initial={{ opacity: 0, y: 30 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-100px" }}
              transition={{
                type: "spring",
                stiffness: 80,
                damping: 18,
                delay: i * 0.08,
              }}
              whileHover={{ y: -8, scale: 1.02 }}
              className="group theme-panel hover:bg-primary/5 relative overflow-hidden rounded-3xl p-6 transition-all duration-500 will-change-transform"
              style={{ transform: "translateZ(0)" }}
            >
              <div
                className={`absolute top-0 right-0 h-40 w-40 bg-gradient-to-br ${agent.color} opacity-0 blur-3xl transition-opacity duration-700 group-hover:opacity-20`}
              />
              <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(135deg,rgba(255,255,255,0.04),transparent_38%,transparent)] opacity-0 transition-opacity duration-500 group-hover:opacity-100" />

              <AgentVectorBadge iconKey={agent.iconKey} accent={agent.accent} glow={agent.color} />

              <h3 className="text-foreground mb-1 text-lg font-bold sm:text-xl">{agent.name}</h3>
              <p className="text-primary/80 mb-4 text-[10px] font-bold tracking-wider uppercase sm:text-[11px]">
                {agent.role}
              </p>
              <p className="text-muted-foreground text-sm leading-relaxed">{agent.description}</p>
            </motion.div>
          ))}
        </div>

        {/* Proactive Heartbeat Section - Rich Content & Ultra Responsive */}
        <div className="theme-panel relative grid items-center gap-8 overflow-hidden rounded-[2rem] p-5 sm:gap-10 sm:rounded-[2.5rem] sm:p-8 lg:grid-cols-2 lg:gap-12 lg:p-16">
          <div className="via-primary/50 absolute top-0 left-0 h-1 w-full bg-gradient-to-r from-transparent to-transparent opacity-60" />

          <div className="relative z-10">
            <div className="mb-6 flex items-center gap-2 text-[10px] font-bold tracking-widest text-emerald-400 uppercase sm:text-xs">
              <Heart className="h-4 w-4 animate-pulse" fill="currentColor" />
              Proactive Runtime Layer
            </div>
            <h3
              className={`${landingFeatureTitleClass} mb-6 text-[2rem] sm:text-4xl lg:text-[3.4rem]`}
            >
              Intelligence that works <br className="hidden sm:block" /> while you sleep.
            </h3>
            <p className="text-muted-foreground mb-8 text-sm leading-7 sm:text-base sm:leading-relaxed lg:text-lg">
              AverQel runs automated background scans, sync jobs, and task-ledger updates on the
              backend. It identifies urgent signals across your stack and prepares context, drafts,
              and next actions before you even log in.
            </p>

            <div className="flex flex-wrap gap-2.5 sm:gap-3 lg:gap-4">
              {integrations.map((int, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, scale: 0.9 }}
                  whileInView={{ opacity: 1, scale: 1 }}
                  transition={{ delay: i * 0.1 }}
                  className="theme-chip hover:border-primary/30 flex items-center gap-2 rounded-full border px-3 py-2 text-[10px] transition-colors sm:gap-2.5 sm:px-4 sm:text-[11px]"
                >
                  <int.icon className="text-muted-foreground h-4 w-4" />
                  <span className="text-foreground text-[10px] font-bold sm:text-xs">
                    {int.label}
                  </span>
                  <div className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400 shadow-[0_0_10px_rgba(52,211,153,0.6)]" />
                </motion.div>
              ))}
            </div>
          </div>

          <div className="relative mt-8 lg:mt-0">
            {/* Terminal Mockup - Optimized for 120fps & Mobile Scaling */}
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              whileInView={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.8, type: "spring" }}
              className="theme-code-surface relative overflow-hidden rounded-2xl border border-white/10 p-4 font-mono text-[10px] leading-5 shadow-2xl sm:p-6 sm:text-[11px] sm:leading-6 lg:p-7 lg:text-[13px] lg:leading-7"
            >
              <div className="mb-6 flex items-center justify-between">
                <div className="flex gap-1.5">
                  <div className="h-2.5 w-2.5 rounded-full bg-red-500/50 sm:h-3 sm:w-3" />
                  <div className="h-2.5 w-2.5 rounded-full bg-amber-500/50 sm:h-3 sm:w-3" />
                  <div className="h-2.5 w-2.5 rounded-full bg-green-500/50 sm:h-3 sm:w-3" />
                </div>
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-2">
                    <div className="h-1 w-16 overflow-hidden rounded-full bg-white/5 sm:h-1.5 sm:w-24">
                      <motion.div
                        animate={{ width: ["20%", "45%", "45%"] }}
                        transition={{ duration: 5, repeat: Infinity, ease: "easeInOut" }}
                        className="bg-primary h-full shadow-[0_0_8px_rgba(var(--primary),0.5)]"
                      />
                    </div>
                    <span className="text-[8px] tracking-tighter text-slate-500 uppercase sm:text-[9px]">
                      Context managed
                    </span>
                  </div>
                </div>
              </div>

              <div className="space-y-3 sm:space-y-4">
                <div className="flex gap-2 sm:gap-3">
                  <span className="shrink-0 text-slate-600">STAGE A</span>
                  <span className="text-primary shrink-0 tracking-widest">[PLAN]</span>
                  <span className="min-w-0 break-words text-slate-300 sm:truncate">
                    DeepSpace evaluates the request, the available tools, and the current workspace
                    context.
                  </span>
                </div>
                <div className="flex gap-2 sm:gap-3">
                  <span className="shrink-0 text-slate-600">STAGE B</span>
                  <span className="shrink-0 tracking-widest text-emerald-400">[TOOL]</span>
                  <span className="min-w-0 break-words text-slate-300 italic sm:truncate">
                    Connectors, search, workspace actions, and model calls execute according to
                    mission scope.
                  </span>
                </div>
                <div className="flex gap-2 sm:gap-3">
                  <span className="shrink-0 text-slate-600">STAGE C</span>
                  <span className="shrink-0 tracking-widest text-cyan-400">[APPROVAL]</span>
                  <span className="min-w-0 break-words text-slate-300 sm:truncate">
                    Risky actions pause for user approval before execution continues.
                  </span>
                </div>
                <motion.div
                  initial={{ opacity: 0.6 }}
                  animate={{ opacity: [0.6, 1, 0.6] }}
                  transition={{ duration: 3, repeat: Infinity }}
                  className="bg-primary/10 border-primary/20 mt-2 flex gap-2 rounded-lg border p-2 sm:gap-3"
                >
                  <span className="text-primary mt-0.5 shrink-0">
                    <ShieldCheck size={14} />
                  </span>
                  <span className="text-[10px] text-slate-200 sm:text-xs">
                    Writes and shell actions require explicit user approval before they run.
                  </span>
                </motion.div>
              </div>

              <div className="mt-6 flex flex-col gap-3 border-t border-white/5 pt-4 sm:mt-8 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-center gap-2">
                  <Activity className="h-3 w-3 text-emerald-400" />
                  <span className="text-[9px] font-bold tracking-widest text-slate-500 uppercase sm:text-[10px]">
                    Runtime posture: healthy
                  </span>
                </div>
                <div className="text-[9px] break-words text-slate-600 italic sm:text-right sm:text-[10px]">
                  Auto-compaction, PostgreSQL checkpoints, and reconnectable SSE/WebSocket
                  synchronization stay active in long sessions
                </div>
              </div>
            </motion.div>

            {/* GPU Accelerated Floating Decorative Elements */}
            <div
              className="bg-primary/20 absolute -top-10 -right-10 h-32 w-32 rounded-full opacity-30 blur-[60px] will-change-transform sm:blur-[80px]"
              style={{ transform: "translateZ(0)" }}
            />
            <div
              className="absolute -bottom-10 -left-10 h-32 w-32 rounded-full bg-violet-500/20 opacity-30 blur-[60px] will-change-transform sm:blur-[80px]"
              style={{ transform: "translateZ(0)" }}
            />
          </div>
        </div>
      </div>
    </motion.section>
  );
}
