"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight,
  BarChart3,
  CalendarClock,
  FileStack,
  Globe2,
  Network,
  ShieldCheck,
  Sparkles,
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

type Capability = {
  icon: typeof FileStack;
  title: string;
  description: string;
  href: string;
  status: string;
  accent: string;
};

const capabilities: Capability[] = [
  {
    icon: FileStack,
    title: "Library + document intelligence",
    description: "Extract and ground answers in PDF, DOCX, PPTX, XLSX, CSV, images, OCR, and text.",
    href: "/documentation/library",
    status: "Available",
    accent: "cyan",
  },
  {
    icon: Globe2,
    title: "Web research",
    description:
      "Plan queries, compare sources, fetch pages, rank evidence, and cite claims in DeepSpace.",
    href: "/documentation/web-research",
    status: "Available · renderer optional",
    accent: "blue",
  },
  {
    icon: BarChart3,
    title: "Sandboxed analysis",
    description:
      "Run bounded Python or read-only SQL against selected Library files without host access.",
    href: "/documentation/sandbox",
    status: "Enable sandbox profile",
    accent: "violet",
  },
  {
    icon: Sparkles,
    title: "Artifacts + exports",
    description:
      "Turn answers into private reports, tables, charts, diagrams, UML, and editable files.",
    href: "/documentation/artifacts",
    status: "Available",
    accent: "emerald",
  },
  {
    icon: CalendarClock,
    title: "Schedules + long-running work",
    description:
      "Run tenant-owned prompts on an interval with durable status, cancellation, and history.",
    href: "/documentation/automation",
    status: "Worker + Beat required",
    accent: "amber",
  },
  {
    icon: Network,
    title: "Providers + MCP",
    description:
      "Choose configured runtimes and connect approved services with encrypted credentials and approvals.",
    href: "/documentation/connectors-mcp",
    status: "Available · approved connectors",
    accent: "rose",
  },
];

const accentClasses: Record<string, string> = {
  cyan: "border-cyan-400/20 bg-cyan-400/[0.06] text-cyan-200",
  blue: "border-blue-400/20 bg-blue-400/[0.06] text-blue-200",
  violet: "border-violet-400/20 bg-violet-400/[0.06] text-violet-200",
  emerald: "border-emerald-400/20 bg-emerald-400/[0.06] text-emerald-200",
  amber: "border-amber-400/20 bg-amber-400/[0.06] text-amber-200",
  rose: "border-rose-400/20 bg-rose-400/[0.06] text-rose-200",
};

export default function CapabilityDirectory() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 10,
    scaleRange: [0.997, 1.004],
  });

  return (
    <motion.section
      ref={ref}
      style={style}
      id="capabilities"
      className={`${landingSectionShellClass} py-14 sm:py-16 lg:py-20`}
      aria-labelledby="capabilities-title"
    >
      <div className={landingContentClass}>
        <div className={landingHeaderWrapClass}>
          <p className={landingEyebrowClass}>Capability directory</p>
          <h2
            id="capabilities-title"
            className={`${landingSectionTitleClass} ${landingTitleGradientBySection.platformSurfaces}`}
          >
            One workspace, six focused ways to work
          </h2>
          <p className={landingSectionLeadClass}>
            See what is available now and what needs an optional deployment profile. Open a card for
            the exact workflow, limits, and setup instead of searching through a long marketing
            page.
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {capabilities.map((capability, index) => {
            const Icon = capability.icon;
            return (
              <motion.div
                key={capability.title}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-40px" }}
                transition={{ delay: index * 0.04 }}
              >
                <Link
                  href={capability.href}
                  className="group flex h-full min-h-[168px] flex-col rounded-2xl border border-white/[0.09] bg-slate-950/45 p-5 backdrop-blur-md transition-all hover:-translate-y-0.5 hover:border-white/25 hover:bg-slate-900/70"
                >
                  <div className="flex items-start justify-between gap-4">
                    <span
                      className={`inline-flex h-10 w-10 items-center justify-center rounded-xl border ${accentClasses[capability.accent]}`}
                    >
                      <Icon size={18} />
                    </span>
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.09] px-2.5 py-1 text-[9px] font-bold tracking-[0.12em] text-slate-400 uppercase">
                      <ShieldCheck size={11} className="text-[#00ffa3]" />
                      {capability.status}
                    </span>
                  </div>
                  <h3 className="mt-4 text-base font-bold text-white">{capability.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{capability.description}</p>
                  <span className="mt-auto flex items-center gap-1.5 pt-4 text-xs font-bold text-[#8effd2] transition-transform group-hover:translate-x-1">
                    Open overview <ArrowRight size={13} />
                  </span>
                </Link>
              </motion.div>
            );
          })}
        </div>
      </div>
    </motion.section>
  );
}
