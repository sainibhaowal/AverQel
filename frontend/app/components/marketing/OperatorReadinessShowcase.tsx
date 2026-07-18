"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Binary, BrainCircuit, FilePenLine, Radar, ShieldCheck } from "lucide-react";
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

const proofCards = [
  {
    title: "Visible mission runtime",
    description:
      "DeepSpace now shows an inline mission canvas with planner source, lane progress, approvals, subagent posture, and mission-level summaries instead of hiding execution behind a single answer bubble.",
    icon: Radar,
    accent:
      "border-cyan-400/20 bg-cyan-500/[0.08] text-cyan-200 shadow-[0_18px_50px_rgba(34,211,238,0.1)]",
  },
  {
    title: "Operator-grade orchestration",
    description:
      "The orchestration control room and mission diagnostics expose why work was delegated, what policy affected it, what hooks ran, and where the mission is paused, active, or completed.",
    icon: Binary,
    accent:
      "border-violet-400/20 bg-violet-500/[0.08] text-violet-200 shadow-[0_18px_50px_rgba(168,85,247,0.1)]",
  },
  {
    title: "Real working surface",
    description:
      "AverQel is not only chat. Users can move into split chat-plus-notes workflows, file-aware drafting, exports, memory-oriented layouts, and persistent proactive follow-up without leaving the product.",
    icon: FilePenLine,
    accent:
      "border-emerald-400/20 bg-emerald-500/[0.08] text-emerald-200 shadow-[0_18px_50px_rgba(16,185,129,0.1)]",
  },
  {
    title: "Safe model flexibility",
    description:
      "Cloud and local runtimes can be used through the same product surface, including OpenRouter, OpenAI-compatible providers, Anthropic, Google, Ollama, and LM Studio, while approvals and tenant boundaries stay intact.",
    icon: BrainCircuit,
    accent:
      "border-amber-400/20 bg-amber-500/[0.08] text-amber-100 shadow-[0_18px_50px_rgba(245,158,11,0.1)]",
  },
];

const operatorPillars = [
  "Mission canvas inside the conversation",
  "DeepSpace runtime controls and preferences",
  "Compaction-aware long-session stability",
  "Hook, policy, and approval visibility",
];

export default function OperatorReadinessShowcase() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 16,
    scaleRange: [0.994, 1.008],
  });

  return (
    <motion.section ref={ref} style={style} className={landingSectionShellClass}>
      <div className={landingContentClass}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ type: "spring", stiffness: 100, damping: 20 }}
          className={landingHeaderWrapClass}
        >
          <p className={`${landingEyebrowClass} text-cyan-300`}>Operator-Grade Runtime</p>
          <h2
            className={`${landingSectionTitleClass} ${landingTitleGradientBySection.orchestration}`}
          >
            Built for teams that need agentic power with production visibility
          </h2>
          <p className={landingSectionLeadClass}>
            The value of AverQel is not only that it can plan, delegate, call tools, and continue
            work. It is that the system exposes those behaviors clearly enough for operators and
            users to understand, trust, and control them in an operational environment.
          </p>
        </motion.div>

        <div className="grid gap-5 lg:grid-cols-2 2xl:grid-cols-4">
          {proofCards.map((card, index) => {
            const Icon = card.icon;
            return (
              <motion.article
                key={card.title}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{
                  type: "spring",
                  stiffness: 88,
                  damping: 18,
                  delay: index * 0.05,
                }}
                className="group theme-panel relative overflow-hidden rounded-[1.7rem] border border-white/8 p-5 transition-all duration-500 hover:-translate-y-1 hover:border-white/[0.16] hover:shadow-[0_28px_80px_rgba(0,0,0,0.22)] sm:p-6"
              >
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/20 to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
                <div
                  className={`mb-5 flex h-12 w-12 items-center justify-center rounded-2xl border ${card.accent}`}
                >
                  <Icon size={20} />
                </div>
                <h3 className="text-foreground text-lg font-black tracking-tight transition-colors duration-300 group-hover:text-white">
                  {card.title}
                </h3>
                <p className="text-muted-foreground mt-3 text-sm leading-7 transition-colors duration-300 group-hover:text-slate-300">
                  {card.description}
                </p>
              </motion.article>
            );
          })}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.45 }}
          className="mt-6 grid gap-5 xl:grid-cols-[1.2fr_0.8fr]"
        >
          <div className="theme-panel rounded-[1.8rem] border border-white/8 p-5 sm:p-6">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-500/[0.08] px-3.5 py-1.5 text-[11px] font-bold tracking-[0.24em] text-emerald-200 uppercase">
              <ShieldCheck size={13} />
              Staging-Verified Controls
            </div>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {operatorPillars.map((pillar) => (
                <div
                  key={pillar}
                  className="rounded-2xl border border-white/8 bg-white/[0.02] px-4 py-3 text-sm font-semibold text-slate-200"
                >
                  {pillar}
                </div>
              ))}
            </div>
          </div>

          <div className="theme-panel rounded-[1.8rem] border border-white/8 p-5 sm:p-6">
            <p className="text-[11px] font-bold tracking-[0.28em] text-slate-400 uppercase">
              Read The Live Product Truth
            </p>
            <p className="text-muted-foreground mt-3 text-sm leading-7">
              The documentation inside AverQel now covers DeepSpace, orchestration, workspace
              editing, memory, proactive automation, providers, connectors, and privacy boundaries
              as they exist in the actual build. The runtime has focused integration and real-provider
              staging validation; deployment teams should still size and load-test their target
              provider and infrastructure before broad rollout.
            </p>
            <Link
              href="/documentation"
              className="mt-5 inline-flex items-center gap-2 text-sm font-bold text-cyan-200 transition hover:text-white"
            >
              Open documentation
              <ArrowRight size={14} />
            </Link>
          </div>
        </motion.div>
      </div>
    </motion.section>
  );
}
