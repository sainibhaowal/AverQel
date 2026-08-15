"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  CheckCircle2,
  KeyRound,
  ShieldCheck,
  SlidersHorizontal,
  UserRoundCheck,
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

const controlAreas = [
  {
    title: "Account security",
    icon: KeyRound,
    color: "text-emerald-300 border-emerald-400/25 bg-emerald-500/[0.08]",
    items: [
      "TOTP two-factor authentication",
      "Backup codes and session invalidation",
      "Sign out from all active devices",
    ],
    href: "/legal/security",
  },
  {
    title: "Data control",
    icon: UserRoundCheck,
    color: "text-cyan-300 border-cyan-400/25 bg-cyan-500/[0.08]",
    items: [
      "Export account data",
      "Review privacy and retention information",
      "Use account deletion controls when needed",
    ],
    href: "/legal/privacy",
  },
  {
    title: "Connected-app control",
    icon: SlidersHorizontal,
    color: "text-amber-300 border-amber-400/25 bg-amber-500/[0.08]",
    items: [
      "OAuth consent happens with the provider",
      "Per-tool permission and risk settings",
      "Approval before sensitive external actions",
    ],
    href: "/documentation/connectors-mcp",
  },
];

const connectionSteps = [
  "Choose an approved remote MCP provider",
  "Review the provider, tools, scopes, and risk labels",
  "Authorize on the provider's official OAuth page",
  "Set permissions and approval requirements",
  "Use only the tools your connection allows",
];

export default function ControlCenter() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 14,
    scaleRange: [0.995, 1.006],
  });

  return (
    <motion.section ref={ref} style={style} id="control" className={landingSectionShellClass}>
      <div className={landingContentClass}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ type: "spring", stiffness: 100, damping: 20 }}
          className={landingHeaderWrapClass}
        >
          <p className={landingEyebrowClass}>Control Is Part of the Product</p>
          <h2 className={`${landingSectionTitleClass} ${landingTitleGradientBySection.trust}`}>
            Useful connections without surrendering authority
          </h2>
          <p className={landingSectionLeadClass}>
            AverQel is built so users can see what is connected, choose what is allowed, and retain
            practical control over their account, data, and external actions.
          </p>
        </motion.div>

        <div className="grid gap-5 lg:grid-cols-3">
          {controlAreas.map((area, index) => {
            const Icon = area.icon;
            return (
              <motion.article
                key={area.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{ type: "spring", stiffness: 88, damping: 18, delay: index * 0.06 }}
                className="theme-panel rounded-2xl border p-5 sm:p-6"
              >
                <span
                  className={`flex h-11 w-11 items-center justify-center rounded-xl border ${area.color}`}
                >
                  <Icon size={18} />
                </span>
                <h3 className="mt-5 text-lg font-black text-white">{area.title}</h3>
                <ul className="mt-4 space-y-3">
                  {area.items.map((item) => (
                    <li key={item} className="flex gap-2.5 text-sm leading-6 text-slate-300">
                      <CheckCircle2 size={14} className="mt-1 shrink-0 text-emerald-300" />
                      {item}
                    </li>
                  ))}
                </ul>
                <Link
                  href={area.href}
                  className="mt-6 inline-flex text-sm font-bold text-cyan-200 hover:text-cyan-100"
                >
                  Learn more
                </Link>
              </motion.article>
            );
          })}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-80px" }}
          transition={{ type: "spring", stiffness: 88, damping: 18 }}
          className="theme-panel mt-5 overflow-hidden rounded-[1.8rem] border p-5 sm:p-7"
        >
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-xl border border-violet-400/25 bg-violet-500/[0.08] text-violet-300">
              <ShieldCheck size={18} />
            </span>
            <div>
              <p className="text-[10px] font-bold tracking-[0.22em] text-violet-300 uppercase">
                MCP connection lifecycle
              </p>
              <h3 className="mt-1 text-xl font-black text-white">
                How a supported app becomes available in DeepSpace
              </h3>
            </div>
          </div>
          <ol className="mt-7 grid gap-3 md:grid-cols-5">
            {connectionSteps.map((step, index) => (
              <li
                key={step}
                className="relative rounded-2xl border border-white/[0.07] bg-white/[0.025] p-4 text-sm leading-6 text-slate-300"
              >
                <span className="mb-4 flex h-7 w-7 items-center justify-center rounded-full border border-violet-400/25 bg-violet-500/[0.08] font-mono text-xs text-violet-200">
                  {index + 1}
                </span>
                {step}
              </li>
            ))}
          </ol>
          <p className="mt-5 text-xs leading-6 text-slate-400">
            Connection health and tool availability are checked at run time. A connected account is
            not a promise that every remote provider will always be available.
          </p>
        </motion.div>
      </div>
    </motion.section>
  );
}
