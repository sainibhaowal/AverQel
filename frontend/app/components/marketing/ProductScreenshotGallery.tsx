"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, BookOpenCheck, FileSearch, Network, PanelsTopLeft } from "lucide-react";
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

const proofPaths = [
  {
    title: "Evidence-first answers",
    icon: FileSearch,
    accent: "text-cyan-300 border-cyan-400/25 bg-cyan-500/[0.08]",
    steps: [
      "Add a supported document",
      "Check processing and source details",
      "Ask a Grounded Query with evidence",
    ],
    href: "/documentation/grounded-query",
    link: "Read about Grounded Query",
  },
  {
    title: "From research to deliverable",
    icon: PanelsTopLeft,
    accent: "text-violet-300 border-violet-400/25 bg-violet-500/[0.08]",
    steps: [
      "Open DeepSpace for the broader task",
      "Draft and refine in connected notes",
      "Export the finished work as needed",
    ],
    href: "/documentation/editor-files",
    link: "Explore notes and exports",
  },
  {
    title: "Connected work under your control",
    icon: Network,
    accent: "text-amber-300 border-amber-400/25 bg-amber-500/[0.08]",
    steps: [
      "Authorize a supported MCP connection",
      "Review tools, risk, and permissions",
      "Approve external actions only when needed",
    ],
    href: "/documentation/connectors-mcp",
    link: "Explore MCP controls",
  },
];

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
          <p className={`${landingEyebrowClass} text-amber-300`}>Built Around Real Work</p>
          <h2 className={`${landingSectionTitleClass} ${landingTitleGradientBySection.techStack}`}>
            Three paths users can take from day one
          </h2>
          <p className={landingSectionLeadClass}>
            No fake dashboard mockups or promises of automatic access. These are the actual product
            paths available in AverQel today.
          </p>
        </motion.div>

        <div className="grid gap-5 lg:grid-cols-3">
          {proofPaths.map((path, index) => {
            const Icon = path.icon;
            return (
              <motion.article
                key={path.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{ type: "spring", stiffness: 90, damping: 18, delay: index * 0.06 }}
                className="theme-panel group relative overflow-hidden rounded-[1.7rem] border p-5 transition-all duration-500 hover:-translate-y-1 hover:border-white/[0.16] hover:shadow-[0_24px_70px_rgba(0,0,0,0.26)] sm:p-6"
              >
                <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/25 to-transparent opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
                <div
                  className={`flex h-12 w-12 items-center justify-center rounded-2xl border ${path.accent}`}
                >
                  <Icon size={20} />
                </div>
                <h3 className="mt-5 text-xl font-black tracking-tight text-white">{path.title}</h3>
                <ol className="mt-5 space-y-3">
                  {path.steps.map((step, stepIndex) => (
                    <li key={step} className="flex gap-3 text-sm leading-6 text-slate-300">
                      <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] font-mono text-[10px] text-slate-400">
                        {stepIndex + 1}
                      </span>
                      {step}
                    </li>
                  ))}
                </ol>
                <Link
                  href={path.href}
                  className="mt-7 inline-flex items-center gap-2 text-sm font-bold text-white transition-colors hover:text-cyan-200"
                >
                  <BookOpenCheck size={15} className="text-cyan-300" />
                  {path.link}
                  <ArrowRight size={14} />
                </Link>
              </motion.article>
            );
          })}
        </div>
      </div>
    </motion.section>
  );
}
