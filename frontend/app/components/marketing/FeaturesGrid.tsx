"use client";

import { motion } from "framer-motion";
import {
  FileStack,
  BrainCircuit,
  ShieldCheck,
  Cpu,
  FileText,
  FileCode,
  ScanSearch,
  BarChart3,
  Shield,
  Lock,
  KeyRound,
  Database,
  Workflow,
  HeartHandshake,
  Bot,
  Search,
  Sparkles,
  NotebookPen,
  Volume2,
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

const features = [
  {
    title: "Documents + Grounded Retrieval",
    description:
      "AverQel turns supported documents into inspectable, retrievable context. Processing state, extracted text, chunks, source details, retry paths, and quality signals remain visible.",
    icon: FileStack,
    accent: "blue",
    size: "large",
    capabilities: [
      { icon: ScanSearch, text: "Source-backed grounded answers" },
      { icon: FileText, text: "Document text, chunks, versions, and downloads" },
      { icon: BarChart3, text: "Processing, retry, and extraction-quality visibility" },
      { icon: Shield, text: "Accessible-document boundaries enforced server-side" },
    ],
  },
  {
    title: "DeepSpace Productivity Workspace",
    description:
      "DeepSpace is the focused workspace for research, drafting, analysis, notes, memory, and tool-assisted work. Users can follow visible activity, preserve useful work, and recover saved conversation history.",
    icon: BrainCircuit,
    accent: "violet",
    size: "large",
    capabilities: [
      { icon: Bot, text: "Research, drafting, analysis, and structured task work" },
      { icon: Search, text: "Available web and workspace tools when appropriate" },
      { icon: BrainCircuit, text: "Visible activity, approval prompts, and saved progress" },
      {
        icon: FileText,
        text: "Streaming answers, approvals, and saved conversation history",
      },
    ],
  },
  {
    title: "Notes + Deliverables",
    description:
      "Move from an answer into editable notes, drafts, equations, diagrams, and exportable deliverables without leaving the workspace.",
    icon: NotebookPen,
    accent: "cyan",
    size: "medium",
    capabilities: [
      { icon: FileText, text: "Split chat-plus-notes and focused workspace modes" },
      { icon: FileCode, text: "Markdown and HTML import with rich block editing" },
      { icon: Sparkles, text: "Math, diagrams, and exports to PDF, DOCX, or Markdown" },
    ],
  },
  {
    title: "Permissioned MCP Connections",
    description:
      "Connect supported remote MCP services through OAuth. Every external call remains subject to ownership, connection status, tool policy, risk limits, and approvals.",
    icon: Workflow,
    accent: "emerald",
    size: "medium",
    capabilities: [
      {
        icon: FileStack,
        text: "Reviewed services: GitHub, Drive, Gmail, Calendar, Chat, and People",
      },
      { icon: HeartHandshake, text: "OAuth authorization with encrypted credential storage" },
      { icon: BarChart3, text: "Health, catalog, scope, and permission visibility" },
    ],
  },
  {
    title: "Flexible AI Providers",
    description:
      "Use configured cloud providers or local runtimes without exposing secret values. Each provider belongs to the account that added it and can be selected for the relevant workflow.",
    icon: Cpu,
    accent: "rose",
    size: "medium",
    capabilities: [
      {
        icon: Workflow,
        text: "OpenRouter, OpenAI-compatible, Anthropic, Google, LM Studio, Ollama",
      },
      { icon: KeyRound, text: "Encrypted secrets with masked display only" },
      { icon: HeartHandshake, text: "Health visibility and capability-aware model selection" },
    ],
  },
  {
    title: "Security + Control Boundaries",
    description:
      "AverQel keeps ownership, tenant isolation, encrypted provider and OAuth credentials, workspace policy, approval controls, and audit-safe execution boundaries in the product path.",
    icon: Lock,
    accent: "emerald",
    size: "large",
    capabilities: [
      {
        icon: ShieldCheck,
        text: "Tenant- and user-scoped workspaces, conversations, and connections",
      },
      {
        icon: Database,
        text: "Encrypted provider secrets and connector OAuth credentials",
      },
      {
        icon: Lock,
        text: "Read-only modes, risk ceilings, and per-tool permission controls",
      },
      {
        icon: Volume2,
        text: "Approval gates for external writes, deletes, and messages",
      },
    ],
  },
];

// ─── Accent System ────────────────────────────────────────────────────────────
// Richer than original: adds topBar gradient, monospace counter color,
// left-accent bar for capability rows, and per-card hover glow blob.
const accentMap: Record<
  string,
  {
    topBar: string;
    iconBorder: string;
    iconBg: string;
    iconText: string;
    capBar: string;
    capIconText: string;
    glowBlob: string;
    counterText: string;
    tagBg: string;
    tagText: string;
  }
> = {
  blue: {
    topBar: "from-blue-500 via-blue-400/50 to-transparent",
    iconBorder: "border-blue-400/30",
    iconBg: "from-blue-500/20 to-blue-600/5",
    iconText: "text-blue-300",
    capBar: "bg-blue-400/50",
    capIconText: "text-blue-400",
    glowBlob: "bg-blue-500/10",
    counterText: "text-blue-400/40",
    tagBg: "bg-blue-500/10 border-blue-500/20",
    tagText: "text-blue-400/80",
  },
  violet: {
    topBar: "from-violet-500 via-violet-400/50 to-transparent",
    iconBorder: "border-violet-400/30",
    iconBg: "from-violet-500/20 to-violet-600/5",
    iconText: "text-violet-300",
    capBar: "bg-violet-400/50",
    capIconText: "text-violet-400",
    glowBlob: "bg-violet-500/10",
    counterText: "text-violet-400/40",
    tagBg: "bg-violet-500/10 border-violet-500/20",
    tagText: "text-violet-400/80",
  },
  emerald: {
    topBar: "from-emerald-500 via-emerald-400/50 to-transparent",
    iconBorder: "border-emerald-400/30",
    iconBg: "from-emerald-500/20 to-emerald-600/5",
    iconText: "text-emerald-300",
    capBar: "bg-emerald-400/50",
    capIconText: "text-emerald-400",
    glowBlob: "bg-emerald-500/10",
    counterText: "text-emerald-400/40",
    tagBg: "bg-emerald-500/10 border-emerald-500/20",
    tagText: "text-emerald-400/80",
  },
  amber: {
    topBar: "from-amber-500 via-amber-400/50 to-transparent",
    iconBorder: "border-amber-400/30",
    iconBg: "from-amber-500/20 to-amber-600/5",
    iconText: "text-amber-300",
    capBar: "bg-amber-400/50",
    capIconText: "text-amber-400",
    glowBlob: "bg-amber-500/10",
    counterText: "text-amber-400/40",
    tagBg: "bg-amber-500/10 border-amber-500/20",
    tagText: "text-amber-400/80",
  },
  cyan: {
    topBar: "from-cyan-500 via-cyan-400/50 to-transparent",
    iconBorder: "border-cyan-400/30",
    iconBg: "from-cyan-500/20 to-cyan-600/5",
    iconText: "text-cyan-300",
    capBar: "bg-cyan-400/50",
    capIconText: "text-cyan-400",
    glowBlob: "bg-cyan-500/10",
    counterText: "text-cyan-400/40",
    tagBg: "bg-cyan-500/10 border-cyan-500/20",
    tagText: "text-cyan-400/80",
  },
  rose: {
    topBar: "from-rose-500 via-rose-400/50 to-transparent",
    iconBorder: "border-rose-400/30",
    iconBg: "from-rose-500/20 to-rose-600/5",
    iconText: "text-rose-300",
    capBar: "bg-rose-400/50",
    capIconText: "text-rose-400",
    glowBlob: "bg-rose-500/10",
    counterText: "text-rose-400/40",
    tagBg: "bg-rose-500/10 border-rose-500/20",
    tagText: "text-rose-400/80",
  },
};

// ─── Header meta chips ────────────────────────────────────────────────────────
const headerMeta = [
  { dot: "bg-blue-400", label: "6 connected product systems" },
  { dot: "bg-emerald-400", label: "Production controls" },
  { dot: "bg-violet-400", label: "Operator-grade" },
];

export default function FeaturesGrid() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 18,
    scaleRange: [0.993, 1.01],
  });

  return (
    <motion.section ref={ref} style={style} id="features" className={landingSectionShellClass}>
      <div className={landingContentClass}>
        {/* ── Section header ─────────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ type: "spring", stiffness: 100, damping: 20 }}
          className={landingHeaderWrapClass}
        >
          {/* Eyebrow with flanking decorative line */}
          <div className="mb-5 flex items-center justify-center gap-3">
            <div className="h-px w-8 bg-white/25" />
            <p className={landingEyebrowClass}>Platform Features</p>
          </div>

          <h2 className={`${landingSectionTitleClass} ${landingTitleGradientBySection.features}`}>
            The complete workspace, without hiding how it works
          </h2>

          <p className={`${landingSectionLeadClass} mt-4`}>
            Documents, grounded retrieval, DeepSpace, notes, MCP connections, providers, and
            security boundaries work together while remaining visible and user-controlled.
          </p>

          {/* Meta chips strip */}
          <div className="mt-8 flex flex-wrap items-center justify-center gap-2">
            {headerMeta.map(({ dot, label }) => (
              <span
                key={label}
                className="flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.04] px-3.5 py-1.5"
              >
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot} opacity-70`} />
                <span className="text-muted-foreground font-mono text-[11px] tracking-wide">
                  {label}
                </span>
              </span>
            ))}
          </div>
        </motion.div>

        {/* ── Bento grid ─────────────────────────────────────────────────────── */}
        <div className="grid gap-4 md:grid-cols-2 lg:gap-5">
          {features.map((feature, index) => {
            const Icon = feature.icon;
            const accent = accentMap[feature.accent];
            const isLarge = feature.size === "large";
            const counter = `${String(index + 1).padStart(2, "0")} ∕ ${String(features.length).padStart(2, "0")}`;

            return (
              <motion.article
                key={feature.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{
                  type: "spring",
                  stiffness: 75,
                  damping: 18,
                  delay: index * 0.055,
                }}
                className={`theme-panel group relative overflow-hidden rounded-2xl border transition-all duration-500 hover:-translate-y-1 hover:border-white/[0.16] hover:shadow-[0_24px_70px_rgba(0,0,0,0.28)] ${
                  isLarge ? "md:col-span-2 lg:col-span-1" : ""
                }`}
              >
                {/* 2px top accent gradient bar, primary visual differentiator */}
                <div
                  className={`absolute top-0 right-0 left-0 h-[2px] bg-gradient-to-r ${accent.topBar}`}
                />

                {/* Hover glow blob, revealed on group-hover */}
                <div
                  className={`pointer-events-none absolute -top-24 -left-20 h-56 w-56 rounded-full blur-[90px] ${accent.glowBlob} opacity-0 transition-opacity duration-700 group-hover:opacity-100`}
                />
                <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.06),transparent_36%),linear-gradient(180deg,rgba(255,255,255,0.015),transparent_28%)] opacity-0 transition-opacity duration-500 group-hover:opacity-100" />

                {/* Card content */}
                <div className="relative p-5 sm:p-6 lg:p-7">
                  {/* Top row: icon left, counter right */}
                  <div className="mb-5 flex items-start justify-between">
                    <div
                      className={`flex h-11 w-11 items-center justify-center rounded-xl border ${accent.iconBorder} bg-gradient-to-b ${accent.iconBg} shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] transition-all duration-300 group-hover:-translate-y-0.5 group-hover:scale-[1.08]`}
                    >
                      <Icon size={19} className={accent.iconText} />
                    </div>

                    {/* Monospace counter, editorial feel */}
                    <span
                      className={`font-mono text-[11px] tracking-widest tabular-nums select-none ${accent.counterText} transition-opacity duration-300 group-hover:opacity-100`}
                    >
                      {counter}
                    </span>
                  </div>

                  {/* Title */}
                  <h3 className="text-foreground mb-2 text-[1.05rem] leading-snug font-bold tracking-tight transition-colors duration-300 group-hover:text-white">
                    {feature.title}
                  </h3>

                  {/* Description */}
                  <p className="text-muted-foreground text-sm leading-[1.75] transition-colors duration-300 group-hover:text-slate-300">
                    {feature.description}
                  </p>

                  {/* ── Capabilities separator with label ───────────────────── */}
                  <div className="my-5 flex items-center gap-3">
                    <div className="h-px flex-1 bg-white/[0.06] transition-colors duration-300 group-hover:bg-white/10" />
                    <span className="font-mono text-[9px] tracking-[0.18em] text-white/[0.22] uppercase transition-colors duration-300 group-hover:text-white/32">
                      Capabilities
                    </span>
                    <div className="h-px flex-1 bg-white/[0.06] transition-colors duration-300 group-hover:bg-white/10" />
                  </div>

                  {/* Capability rows, precision readout style */}
                  {/* Large cards: 2-col grid. Medium: single column */}
                  <div
                    className={`grid gap-x-4 gap-y-0 ${isLarge ? "sm:grid-cols-2" : "grid-cols-1"}`}
                  >
                    {feature.capabilities.map((cap, ci) => {
                      const CapIcon = cap.icon;
                      return (
                        <div
                          key={ci}
                          className="group/row flex items-start gap-3 border-b border-white/[0.04] py-2.5 transition-colors duration-300 group-hover/row:border-white/[0.06] last:border-0"
                        >
                          {/* Left accent bar */}
                          <div
                            className={`mt-[5px] h-3 w-[2px] shrink-0 rounded-full ${accent.capBar} transition-all duration-300 group-hover/row:h-4 group-hover/row:opacity-100`}
                          />

                          <CapIcon
                            size={12}
                            className={`mt-[3px] shrink-0 ${accent.capIconText} opacity-55 transition-all duration-200 group-hover/row:-translate-y-0.5 group-hover/row:opacity-90`}
                          />

                          <span className="text-muted-foreground group-hover/row:text-foreground/80 text-xs leading-[1.6] transition-colors duration-200">
                            {cap.text}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </motion.article>
            );
          })}
        </div>
      </div>
    </motion.section>
  );
}
