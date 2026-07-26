"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import {
  Database,
  Eye,
  Fingerprint,
  KeyRound,
  Lock,
  ScrollText,
  ShieldCheck,
  UserX,
} from "lucide-react";
import { useLandingSectionMotion } from "./landingMotion";
import {
  landingContentClass,
  landingHeaderWrapClass,
  landingSectionLeadClass,
  landingSectionShellClass,
  landingSectionTitleClass,
  landingTitleGradientBySection,
} from "./landingType";

const securityFeatures = [
  {
    title: "Authentication & Access",
    icon: KeyRound,
    items: [
      "Argon2id password hashing",
      "Time-based 2FA (TOTP) with backup codes",
      "Brute-force protection with account lockout",
      "Session invalidation and logout-all-devices",
      "Token versioning for forced re-authentication",
    ],
  },
  {
    title: "Data Isolation",
    icon: Lock,
    items: [
      "Tenant- and user-scoped conversation state",
      "PostgreSQL stores authoritative chat and memory records",
      "Redis is limited to cache and transient service coordination",
      "Workspace and connector policy remains enforced at execution time",
      "Cross-tenant run and event access is denied server-side",
    ],
  },
  {
    title: "Operational Visibility",
    icon: ScrollText,
    items: [
      "Redacted operational records with integrity checks",
      "Saved messages and safe reload behavior",
      "Trace IDs, approval decisions, and provider posture",
      "Admin surfaces restricted to operational metadata by policy",
      "Live execution state streamed without exposing raw secrets",
    ],
  },
  {
    title: "Runtime Protection",
    icon: ShieldCheck,
    items: [
      "Rate limiting on account endpoints",
      "Secure connector and workflow execution",
      "Secure session cookies with HTTPS",
      "Execution gates and approval controls",
      "External mutations execute only through authorized connectors",
    ],
  },
];

const trustPillars = [
  {
    icon: Eye,
    title: "Durable state has a clear source of truth",
    body: "DeepSpace stores conversation messages and memory in PostgreSQL. Transient service state cannot authorize or replace tenant-scoped records.",
  },
  {
    icon: Fingerprint,
    title: "Provider secrets stay protected",
    body: "Provider secrets and connector OAuth credentials remain encrypted, masked in responses, and protected by the existing provider and connector security boundaries.",
  },
  {
    icon: Database,
    title: "Every action stays scoped",
    body: "Tenant and user ownership is carried through runs, nodes, events, approvals, checkpoints, leases, and tool records. Workspace policy and approval gates remain part of execution.",
  },
  {
    icon: UserX,
    title: "Users can recover their conversation",
    body: "Persisted assistant messages let authorized users recover the visible thread after a browser or API interruption.",
  },
];

export default function TrustCommitments() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 16,
    scaleRange: [0.994, 1.008],
  });

  return (
    <motion.section ref={ref} style={style} id="security" className={landingSectionShellClass}>
      <div className={landingContentClass}>
        {/* Section header */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
          className={landingHeaderWrapClass}
        >
          <p className="text-[11px] font-bold tracking-[0.3em] text-emerald-400/80 uppercase">
            Security & Trust
          </p>
          <h2 className={`${landingSectionTitleClass} ${landingTitleGradientBySection.trust}`}>
            Security built into every layer, not bolted on after the fact
          </h2>
          <p className={landingSectionLeadClass}>
            AverQel treats privacy, durability, and control as one runtime contract. DeepSpace keeps
            authoritative execution state in PostgreSQL, uses Redis only for live projections, and
            carries tenant isolation, encrypted secrets, workspace policy, approvals, and audit
            redaction through the execution path.
          </p>
        </motion.div>

        {/* Security features grid */}
        <div className="mb-12 grid gap-5 sm:grid-cols-2 lg:mb-16 lg:grid-cols-4">
          {securityFeatures.map((feature, i) => {
            const Icon = feature.icon;
            return (
              <motion.div
                key={feature.title}
                initial={{ opacity: 0, y: 18 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{ duration: 0.4, delay: i * 0.06 }}
                className="group border-glass-border bg-surface-0 hover:bg-primary/5 relative flex flex-col overflow-hidden rounded-2xl border p-4 shadow-sm transition-all duration-500 hover:-translate-y-1 hover:border-white/[0.14] hover:shadow-[0_22px_60px_rgba(0,0,0,0.24)] sm:p-5"
              >
                <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(34,197,94,0.08),transparent_34%),linear-gradient(180deg,rgba(255,255,255,0.014),transparent_26%)] opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
                <div className="pointer-events-none absolute top-0 right-0 left-0 h-px bg-gradient-to-r from-emerald-400/0 via-emerald-300/45 to-emerald-400/0 opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
                <div className="pointer-events-none absolute top-4 right-4 h-10 w-10 rounded-full border border-emerald-400/10 opacity-0 transition-all duration-500 group-hover:scale-110 group-hover:opacity-100" />
                <div className="pointer-events-none absolute right-0 bottom-0 h-16 w-16 translate-x-4 translate-y-4 rounded-tl-[2rem] border-t border-l border-emerald-400/10 opacity-0 transition-all duration-500 group-hover:translate-x-0 group-hover:translate-y-0 group-hover:opacity-100" />
                <div className="relative mb-4 flex h-12 w-12 items-center justify-center rounded-[1rem] border border-emerald-400/20 bg-[linear-gradient(180deg,rgba(16,185,129,0.14),rgba(16,185,129,0.05))] shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_10px_24px_rgba(16,185,129,0.08)] transition-all duration-300 group-hover:-translate-y-0.5 group-hover:scale-[1.06] group-hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.1),0_16px_34px_rgba(16,185,129,0.14)]">
                  <Icon size={18} className="text-emerald-300" />
                </div>
                <h3 className="text-foreground relative mb-3 text-sm font-bold transition-colors duration-300 group-hover:text-white">
                  {feature.title}
                </h3>
                <ul className="space-y-2">
                  {feature.items.map((item, j) => (
                    <li
                      key={j}
                      className="text-muted-foreground relative flex items-start gap-2 rounded-lg pr-2 text-xs leading-5 transition-all duration-300 group-hover:text-slate-300"
                    >
                      <span className="pointer-events-none absolute inset-y-1 left-[-0.35rem] w-px scale-y-0 bg-gradient-to-b from-emerald-300/0 via-emerald-300/60 to-emerald-300/0 transition-transform duration-300 group-hover:scale-y-100" />
                      <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-emerald-400/50 transition-all duration-300 group-hover:scale-125 group-hover:bg-emerald-300" />
                      <span className="transition-transform duration-300 group-hover:translate-x-0.5">
                        {item}
                      </span>
                    </li>
                  ))}
                </ul>
              </motion.div>
            );
          })}
        </div>

        {/* Trust pillars */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
          className="mb-8 sm:mb-10"
        >
          <h3 className="text-foreground mb-6 text-lg font-bold sm:mb-8 sm:text-xl">
            Trust commitments
          </h3>
          <div className="grid gap-5 sm:grid-cols-2">
            {trustPillars.map((pillar) => {
              const Icon = pillar.icon;
              return (
                <div
                  key={pillar.title}
                  className="group border-glass-border bg-surface-0 relative flex items-start gap-4 overflow-hidden rounded-2xl border p-4 shadow-sm transition-all duration-500 hover:-translate-y-1 hover:border-white/[0.14] hover:shadow-[0_22px_60px_rgba(0,0,0,0.22)] sm:p-5"
                >
                  <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(59,130,246,0.08),transparent_36%),linear-gradient(180deg,rgba(255,255,255,0.014),transparent_26%)] opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
                  <div className="pointer-events-none absolute top-0 right-0 left-0 h-px bg-gradient-to-r from-blue-400/0 via-blue-300/45 to-blue-400/0 opacity-0 transition-opacity duration-500 group-hover:opacity-100" />
                  <div className="pointer-events-none absolute right-0 bottom-0 h-18 w-18 translate-x-5 translate-y-5 rounded-tl-[2rem] border-t border-l border-blue-400/10 opacity-0 transition-all duration-500 group-hover:translate-x-0 group-hover:translate-y-0 group-hover:opacity-100" />
                  <div className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-[1rem] border border-blue-400/20 bg-[linear-gradient(180deg,rgba(59,130,246,0.14),rgba(59,130,246,0.05))] shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_10px_24px_rgba(59,130,246,0.08)] transition-all duration-300 group-hover:-translate-y-0.5 group-hover:scale-[1.06] group-hover:shadow-[inset_0_1px_0_rgba(255,255,255,0.1),0_16px_34px_rgba(59,130,246,0.14)]">
                    <Icon size={16} className="text-blue-300" />
                  </div>
                  <div className="relative">
                    <h4 className="text-foreground text-sm font-bold transition-all duration-300 group-hover:translate-x-0.5 group-hover:text-white">
                      {pillar.title}
                    </h4>
                    <p className="text-muted-foreground mt-1.5 text-xs leading-6 transition-all duration-300 group-hover:translate-x-0.5 group-hover:text-slate-300 sm:text-xs">
                      {pillar.body}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </motion.div>

        {/* Legal links */}
        <div className="flex flex-wrap justify-center gap-3">
          <Link
            href="/legal/privacy"
            className="group bg-surface-0 border-glass-border text-muted-foreground hover:bg-muted hover:text-foreground relative isolate inline-flex items-center overflow-hidden rounded-full border px-5 py-2.5 text-sm font-bold shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:border-white/[0.14] hover:shadow-[0_16px_36px_rgba(0,0,0,0.18)]"
          >
            <span className="pointer-events-none absolute inset-y-0 left-[-30%] w-[30%] -skew-x-12 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.18),transparent)] opacity-0 blur-[1px] transition-all duration-700 group-hover:translate-x-[420%] group-hover:opacity-100" />
            Privacy Policy
          </Link>
          <Link
            href="/legal/terms"
            className="group bg-surface-0 border-glass-border text-muted-foreground hover:bg-muted hover:text-foreground relative isolate inline-flex items-center overflow-hidden rounded-full border px-5 py-2.5 text-sm font-bold shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:border-white/[0.14] hover:shadow-[0_16px_36px_rgba(0,0,0,0.18)]"
          >
            <span className="pointer-events-none absolute inset-y-0 left-[-30%] w-[30%] -skew-x-12 bg-[linear-gradient(90deg,transparent,rgba(255,255,255,0.18),transparent)] opacity-0 blur-[1px] transition-all duration-700 group-hover:translate-x-[420%] group-hover:opacity-100" />
            Terms of Service
          </Link>
          <Link
            href="/legal/security"
            className="group relative isolate inline-flex items-center gap-2 overflow-hidden rounded-full border border-emerald-400/20 bg-emerald-500/[0.08] px-5 py-2.5 text-sm font-semibold text-emerald-200 shadow-[0_0_0_1px_rgba(16,185,129,0.02)] transition-all duration-300 hover:-translate-y-0.5 hover:border-emerald-300/30 hover:bg-emerald-500/[0.14] hover:text-emerald-100 hover:shadow-[0_16px_36px_rgba(16,185,129,0.12)]"
          >
            <span className="pointer-events-none absolute inset-y-0 left-[-30%] w-[30%] -skew-x-12 bg-[linear-gradient(90deg,transparent,rgba(153,255,216,0.22),transparent)] opacity-0 blur-[1px] transition-all duration-700 group-hover:translate-x-[420%] group-hover:opacity-100" />
            <ShieldCheck
              size={14}
              className="transition-transform duration-300 group-hover:scale-110"
            />
            Full Security Overview
          </Link>
        </div>
      </div>
    </motion.section>
  );
}
