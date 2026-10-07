"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  ArrowRight,
  CalendarClock,
  Cable,
  FileStack,
  FolderKanban,
  Globe2,
  HardDrive,
  Layers3,
  LifeBuoy,
  Mic,
  Network,
  SearchCheck,
  ShieldCheck,
  UserRound,
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
  group: "Knowledge" | "AI and work" | "Account and support";
  icon: typeof FileStack;
  title: string;
  description: string;
  href: string;
  status: string;
  accent: string;
};

const capabilities: Capability[] = [
  {
    group: "Knowledge",
    icon: FileStack,
    title: "Documents Hub",
    description:
      "Upload supported files, inspect extraction and indexing, manage versions, and follow processing or retry status.",
    href: "/documentation/library",
    status: "Available",
    accent: "cyan",
  },
  {
    group: "Knowledge",
    icon: SearchCheck,
    title: "Grounded Query",
    description:
      "Ask questions over sources you can access, then inspect the supporting evidence and citations.",
    href: "/documentation/grounded-query",
    status: "Available",
    accent: "blue",
  },
  {
    group: "Knowledge",
    icon: FolderKanban,
    title: "Collections",
    description:
      "Keep project sources together and collaborate through explicit collection membership. Collections are in experimental beta.",
    href: "/documentation/collections-sharing",
    status: "Experimental beta",
    accent: "emerald",
  },
  {
    group: "AI and work",
    icon: Network,
    title: "AI providers",
    description:
      "Configure compatible cloud or local providers for the runtime roles enabled in your workspace.",
    href: "/documentation/providers",
    status: "User configured",
    accent: "blue",
  },
  {
    group: "AI and work",
    icon: Layers3,
    title: "DeepSpace",
    description:
      "Continue research, drafting, notes, memory, and tool-assisted work in durable conversations with saved history.",
    href: "/documentation/memory-workspace",
    status: "Provider required",
    accent: "violet",
  },
  {
    group: "AI and work",
    icon: Cable,
    title: "MCP connections",
    description:
      "Authorize supported external tools separately. Connection health, tool policy, and approval rules apply.",
    href: "/documentation/connectors-mcp",
    status: "Optional · policy gated",
    accent: "amber",
  },
  {
    group: "AI and work",
    icon: Globe2,
    title: "Research and analysis",
    description:
      "Use web research and bounded analysis where their required renderer or sandbox profile is enabled.",
    href: "/documentation/features",
    status: "Deployment dependent",
    accent: "blue",
  },
  {
    group: "AI and work",
    icon: CalendarClock,
    title: "Scheduled work",
    description:
      "Run tenant-owned prompts on an interval with durable status and history when worker scheduling is enabled.",
    href: "/documentation/automation",
    status: "Worker + Beat required",
    accent: "amber",
  },
  {
    group: "AI and work",
    icon: Mic,
    title: "Voice and realtime",
    description:
      "Use speech input and realtime voice features in supported deployments with compatible providers.",
    href: "/documentation/voice",
    status: "Deployment gated",
    accent: "violet",
  },
  {
    group: "Account and support",
    icon: UserRound,
    title: "Profile and account",
    description:
      "Manage account identity, sign-in security, and active sessions from your workspace settings.",
    href: "/documentation/profile",
    status: "Account settings",
    accent: "cyan",
  },
  {
    group: "Account and support",
    icon: HardDrive,
    title: "Plan and storage",
    description:
      "Review your assigned plan, workspace storage usage, and the data retention controls available to your account.",
    href: "/dashboard/settings/plan",
    status: "Account scoped",
    accent: "amber",
  },
  {
    group: "Account and support",
    icon: ShieldCheck,
    title: "Trust and policies",
    description:
      "Understand privacy, retention, tenant boundaries, and how access to sources and external actions is controlled.",
    href: "/documentation/privacy-security",
    status: "Security controls",
    accent: "emerald",
  },
  {
    group: "Account and support",
    icon: LifeBuoy,
    title: "Support and feedback",
    description:
      "Get help with a support request and share product feedback through the signed-in workspace.",
    href: "/documentation/support",
    status: "Account area",
    accent: "rose",
  },
];

const capabilityGroups = [
  {
    id: "knowledge",
    title: "Organize and find knowledge",
    description: "Bring sources together, retrieve evidence, and work with scoped collections.",
    name: "Knowledge",
  },
  {
    id: "ai-work",
    title: "Choose how AI work happens",
    description:
      "Configure providers and use DeepSpace, research, and connected tools where enabled.",
    name: "AI and work",
  },
  {
    id: "account-support",
    title: "Manage your account and get help",
    description:
      "Review account, plan, storage, privacy, support, and feedback options in one place.",
    name: "Account and support",
  },
] as const;

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
            The whole AverQel workspace, clearly connected
          </h2>
          <p className={landingSectionLeadClass}>
            Start with knowledge, move into AI-assisted work, then manage the account and support
            around it. Some capabilities require a compatible provider or deployment configuration;
            each card links to its setup and limits.
          </p>
        </div>

        <div className="space-y-9">
          {capabilityGroups.map((group) => {
            const groupCapabilities = capabilities.filter((item) => item.group === group.name);
            return (
              <section key={group.name} aria-labelledby={`capability-group-${group.id}`}>
                <div className="mb-4">
                  <h3
                    id={`capability-group-${group.id}`}
                    className="text-lg font-bold tracking-tight text-white sm:text-xl"
                  >
                    {group.title}
                  </h3>
                  <p className="mt-1 text-sm leading-6 text-slate-400">{group.description}</p>
                </div>
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {groupCapabilities.map((capability, index) => {
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
                          <h4 className="mt-4 text-base font-bold text-white">
                            {capability.title}
                          </h4>
                          <p className="mt-2 text-sm leading-6 text-slate-400">
                            {capability.description}
                          </p>
                          <span className="mt-auto flex items-center gap-1.5 pt-4 text-xs font-bold text-[#8effd2] transition-transform group-hover:translate-x-1">
                            Open overview <ArrowRight size={13} />
                          </span>
                        </Link>
                      </motion.div>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      </div>
    </motion.section>
  );
}
