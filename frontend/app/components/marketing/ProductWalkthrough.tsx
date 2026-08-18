"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  Cable,
  CheckCircle2,
  FileText,
  FolderKanban,
  Gauge,
  Network,
  Search,
  ShieldCheck,
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

const steps = [
  {
    title: "Choose your runtime",
    eyebrow: "01 · Providers",
    icon: Network,
    color: "text-rose-300",
    border: "border-rose-400/25",
    bg: "bg-rose-500/[0.08]",
    body: "Add a cloud or local model provider for chat, research, embeddings, reranking, or web search. Your configured provider remains private to your account.",
    outcome: "A ready AI runtime, chosen by you.",
    signals: [
      ["Runtime route", "Cloud or local", "Selected per workspace capability"],
      ["Model inventory", "Discovered", "Context and capability metadata stay visible"],
      ["Credentials", "Protected", "Masked in the user interface"],
    ],
  },
  {
    title: "Bring in documents",
    eyebrow: "02 · Documents Hub",
    icon: FileText,
    color: "text-cyan-300",
    border: "border-cyan-400/25",
    bg: "bg-cyan-500/[0.08]",
    body: "Upload supported files and watch their processing state. Inspect text, chunks, versions, extraction signals, and the original file from one document workspace.",
    outcome: "Private source material that is ready to search.",
    signals: [
      ["Pipeline", "Queued to indexed", "Worker progress remains visible"],
      ["Source detail", "Inspectable", "Text, chunks, versions, and extraction state"],
      ["Recovery", "Available", "Retry and reingest paths are explicit"],
    ],
  },
  {
    title: "Keep context focused",
    eyebrow: "03 · Collections",
    icon: FolderKanban,
    color: "text-emerald-300",
    border: "border-emerald-400/25",
    bg: "bg-emerald-500/[0.08]",
    body: "Group the documents that belong together, then share only the collection you intend to share through explicit ownership and permission controls.",
    outcome: "A deliberate scope for each project or team.",
    signals: [
      ["Membership", "Invite-based", "Owner and member roles remain explicit"],
      ["Conversation", "Real time", "Encrypted messages and attachments"],
      ["Documents", "Shared by reference", "Members use only approved collection sources"],
    ],
  },
  {
    title: "Ask grounded questions",
    eyebrow: "04 · Grounded Query",
    icon: Search,
    color: "text-blue-300",
    border: "border-blue-400/25",
    bg: "bg-blue-500/[0.08]",
    body: "Ask questions over the documents you can access. Review evidence, citations, rich results, and source details instead of relying on an ungrounded answer.",
    outcome: "Answers you can trace back to source material.",
    signals: [
      ["Retrieval", "Scoped", "Only accessible document context is eligible"],
      ["Evidence", "Linked", "Sources stay attached to the answer"],
      ["Output", "Structured", "Rich text, tables, diagrams, and export paths"],
    ],
  },
  {
    title: "Do the deeper work",
    eyebrow: "05 · DeepSpace",
    icon: Activity,
    color: "text-violet-300",
    border: "border-violet-400/25",
    bg: "bg-violet-500/[0.08]",
    body: "Use a durable chat for research, drafting, notes, memory, and tool-assisted work. Save results into the workspace and export the finished deliverable when ready.",
    outcome: "A continuous place to turn information into work.",
    signals: [
      ["Activity", "Visible", "Thinking, tools, approvals, and progress"],
      ["State", "Durable", "Saved history and reconnectable runs"],
      ["Workspace", "Connected", "Notes, Library, memory, and deliverables"],
    ],
  },
  {
    title: "Connect apps deliberately",
    eyebrow: "06 · MCP Connections",
    icon: Cable,
    color: "text-amber-300",
    border: "border-amber-400/25",
    bg: "bg-amber-500/[0.08]",
    body: "Authorize supported remote apps through OAuth. AverQel checks connection health, scope, policy, and any required approval before an external tool is used.",
    outcome: "Useful integrations without giving up control.",
    signals: [
      ["Connection", "OAuth", "Health and catalog state are checked"],
      ["Permission", "Policy-bound", "Read, write, delete, and message risk levels"],
      ["Execution", "Human-aware", "Approval can be required before remote effects"],
    ],
  },
];

export default function ProductWalkthrough() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 18,
    scaleRange: [0.994, 1.008],
  });
  const [activeStep, setActiveStep] = useState(0);
  const active = steps[activeStep];
  const ActiveIcon = active.icon;

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
          <p className={landingEyebrowClass}>The Real Product Walkthrough</p>
          <h2
            className={`${landingSectionTitleClass} ${landingTitleGradientBySection.platformSurfaces}`}
          >
            From a private document to a finished piece of work
          </h2>
          <p className={landingSectionLeadClass}>
            AverQel is a connected workspace, not a generic chat box. Follow the steps below to see
            exactly where documents, grounded answers, DeepSpace, providers, and connected apps fit
            together.
          </p>
        </motion.div>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,0.86fr)_minmax(0,1.14fr)]">
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
            {steps.map((step, index) => {
              const Icon = step.icon;
              const selected = index === activeStep;
              return (
                <button
                  key={step.title}
                  type="button"
                  onClick={() => setActiveStep(index)}
                  className={`group flex w-full items-start gap-3 rounded-2xl border p-4 text-left transition-all duration-300 focus-visible:ring-2 focus-visible:ring-cyan-300/70 focus-visible:outline-none ${
                    selected
                      ? `${step.border} ${step.bg} shadow-[0_16px_50px_rgba(0,0,0,0.2)]`
                      : "border-white/[0.07] bg-white/[0.02] hover:border-white/[0.15] hover:bg-white/[0.045]"
                  }`}
                  aria-pressed={selected}
                >
                  <span
                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border ${step.border} ${step.bg} ${step.color}`}
                  >
                    <Icon size={17} />
                  </span>
                  <span className="min-w-0">
                    <span
                      className={`block text-[10px] font-bold tracking-[0.2em] uppercase ${step.color}`}
                    >
                      {step.eyebrow}
                    </span>
                    <span className="mt-1 block text-sm font-bold text-white">{step.title}</span>
                  </span>
                </button>
              );
            })}
          </div>

          <motion.article
            key={active.title}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.24, ease: "easeOut" }}
            className="theme-panel relative overflow-hidden rounded-[1.8rem] border border-white/[0.1] p-6 sm:p-8"
          >
            <div
              className={`absolute -top-20 -right-20 h-64 w-64 rounded-full blur-[100px] ${active.bg}`}
            />
            <div className="relative">
              <div className="flex items-start justify-between gap-5">
                <div>
                  <p
                    className={`text-[11px] font-bold tracking-[0.25em] uppercase ${active.color}`}
                  >
                    {active.eyebrow}
                  </p>
                  <h3 className="mt-3 text-2xl font-black tracking-tight text-white sm:text-3xl">
                    {active.title}
                  </h3>
                </div>
                <div
                  className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border ${active.border} ${active.bg} ${active.color}`}
                >
                  <ActiveIcon size={23} />
                </div>
              </div>
              <p className="mt-7 max-w-2xl text-base leading-8 text-slate-300">{active.body}</p>
              <div className={`mt-8 rounded-2xl border ${active.border} ${active.bg} p-4`}>
                <p className="text-[10px] font-bold tracking-[0.22em] text-slate-400 uppercase">
                  What you get
                </p>
                <p className={`mt-2 text-sm font-bold ${active.color}`}>{active.outcome}</p>
              </div>
              <div className="mt-6 grid gap-3 sm:grid-cols-3">
                {active.signals.map(([label, value, detail], index) => (
                  <motion.div
                    key={label}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.08 + index * 0.06, duration: 0.22 }}
                    className="rounded-2xl border border-white/[0.08] bg-black/20 p-3"
                  >
                    <p className="text-[9px] font-bold tracking-[0.16em] text-slate-500 uppercase">
                      {label}
                    </p>
                    <p className={`mt-2 text-sm font-black ${active.color}`}>{value}</p>
                    <p className="mt-1 text-[10px] leading-4 text-slate-500">{detail}</p>
                  </motion.div>
                ))}
              </div>
              <div className="mt-6 flex flex-wrap items-center gap-3 text-[10px] font-bold tracking-[0.15em] text-slate-500 uppercase">
                <span className="inline-flex items-center gap-1.5">
                  <CheckCircle2 size={13} className="text-emerald-300" /> Verified path
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <ShieldCheck size={13} className="text-cyan-300" /> Policy boundary
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <Gauge size={13} className="text-violet-300" /> Observable state
                </span>
              </div>
              <div
                className="mt-8 flex items-center gap-2"
                aria-label={`Step ${activeStep + 1} of ${steps.length}`}
              >
                {steps.map((step, index) => (
                  <span
                    key={step.title}
                    className={`h-1.5 rounded-full transition-all duration-300 ${
                      index === activeStep ? "w-9 bg-cyan-300" : "w-3 bg-white/15"
                    }`}
                  />
                ))}
              </div>
            </div>
          </motion.article>
        </div>
      </div>
    </motion.section>
  );
}
