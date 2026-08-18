"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight,
  CheckCircle2,
  FileSearch,
  FolderTree,
  Network,
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

const stages = [
  {
    label: "01",
    title: "Bring in the material",
    detail:
      "A workspace tree keeps files, folders, and shared sources visible at the start of the route.",
    icon: FolderTree,
    tone: "cyan",
  },
  {
    label: "02",
    title: "Ask with evidence",
    detail: "A query trace shows the evidence path before a result becomes part of the work.",
    icon: FileSearch,
    tone: "violet",
  },
  {
    label: "03",
    title: "Do the deeper work",
    detail:
      "The active workspace turns that result into a draft, note, or next action with visible progress.",
    icon: CheckCircle2,
    tone: "emerald",
  },
  {
    label: "04",
    title: "Connect deliberately",
    detail:
      "A final boundary makes external actions explicit: connection health, policy, and approval are visible.",
    icon: ShieldCheck,
    tone: "amber",
  },
] as const;

const toneClass = {
  cyan: "border-cyan-300/25 bg-cyan-300/10 text-cyan-200",
  violet: "border-violet-300/25 bg-violet-300/10 text-violet-200",
  emerald: "border-emerald-300/25 bg-emerald-300/10 text-emerald-200",
  amber: "border-amber-300/25 bg-amber-300/10 text-amber-100",
};

export default function ProductScreenshotGallery() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 14,
    scaleRange: [0.995, 1.006],
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
          <p className={`${landingEyebrowClass} text-amber-300`}>
            A Product Story, Not a Card Wall
          </p>
          <h2 className={`${landingSectionTitleClass} ${landingTitleGradientBySection.techStack}`}>
            Follow one piece of work through AverQel
          </h2>
          <p className={landingSectionLeadClass}>
            This is an interactive product illustration, not a fabricated screenshot. It shows how
            the actual surfaces connect in a deliberate, user-controlled sequence.
          </p>
        </motion.div>

        <div className="relative overflow-hidden rounded-[2.25rem] border border-white/10 bg-[linear-gradient(145deg,rgba(8,14,21,0.96),rgba(4,8,13,0.88))] p-5 shadow-[0_34px_120px_rgba(0,0,0,0.38)] sm:p-8 lg:p-10">
          <div className="absolute inset-0 [background-image:linear-gradient(90deg,rgba(255,255,255,0.045)_1px,transparent_1px),linear-gradient(rgba(255,255,255,0.045)_1px,transparent_1px)] [background-size:42px_42px] opacity-40" />
          <div className="relative grid gap-8 xl:grid-cols-[0.8fr_1.2fr] xl:gap-12">
            <div className="flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-2 font-mono text-[10px] font-bold tracking-[0.22em] text-cyan-300 uppercase">
                  <Network size={13} /> Workspace route
                </div>
                <h3 className="mt-4 max-w-md text-3xl font-black tracking-tight text-white sm:text-4xl">
                  From source material to a useful next action.
                </h3>
                <p className="mt-5 max-w-md text-sm leading-7 text-slate-400">
                  Every stage has a visible boundary: sources, answer evidence, workspace work, then
                  any authorized external service.
                </p>
              </div>
              <Link
                href="/documentation/simple-system-walkthrough"
                className="mt-8 inline-flex w-fit items-center gap-2 text-sm font-bold text-cyan-200 transition-colors hover:text-white"
              >
                Read the end-to-end walkthrough <ArrowRight size={15} />
              </Link>
            </div>

            <div className="relative grid gap-3 md:grid-cols-2">
              <div className="pointer-events-none absolute top-5 left-1/2 hidden h-[calc(100%-40px)] w-px -translate-x-1/2 bg-gradient-to-b from-transparent via-cyan-300/30 to-transparent md:block" />
              {stages.map((stage, index) => {
                const Icon = stage.icon;
                return (
                  <motion.article
                    key={stage.label}
                    initial={{ opacity: 0, scale: 0.96 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true, margin: "-70px" }}
                    transition={{
                      type: "spring",
                      stiffness: 90,
                      damping: 18,
                      delay: index * 0.07,
                    }}
                    whileHover={{ y: -5, scale: 1.01 }}
                    className="group relative z-10 overflow-hidden rounded-2xl border border-white/[0.08] bg-slate-950/45 p-5 backdrop-blur-md transition-shadow hover:shadow-[0_20px_55px_rgba(0,0,0,0.3)]"
                  >
                    <motion.div
                      className={`absolute -top-9 -right-9 h-28 w-28 rounded-full blur-3xl ${toneClass[stage.tone]}`}
                      initial={{ opacity: 0.35 }}
                      whileHover={{ opacity: 0.7, scale: 1.15 }}
                    />
                    <div className="relative flex items-start justify-between gap-3">
                      <span className="font-mono text-xs font-black tracking-[0.22em] text-slate-500">
                        {stage.label}
                      </span>
                      <span
                        className={`flex h-10 w-10 items-center justify-center rounded-xl border ${toneClass[stage.tone]}`}
                      >
                        <Icon size={18} />
                      </span>
                    </div>
                    <h4 className="relative mt-9 text-lg font-black tracking-tight text-white">
                      {stage.title}
                    </h4>
                    <p className="relative mt-3 text-sm leading-6 text-slate-400">{stage.detail}</p>
                    <div className="relative mt-6 flex items-center gap-2 text-[10px] font-bold tracking-[0.15em] text-slate-500 uppercase">
                      <span
                        className={`h-1.5 w-1.5 rounded-full ${stage.tone === "amber" ? "bg-amber-300" : "bg-emerald-300"}`}
                      />
                      {stage.tone === "amber" ? "policy-aware" : "workspace scoped"}
                    </div>
                  </motion.article>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </motion.section>
  );
}
