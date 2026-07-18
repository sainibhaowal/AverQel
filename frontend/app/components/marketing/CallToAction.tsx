"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Database, FileText, Search, Shield, Users } from "lucide-react";
import { useLandingSectionMotion } from "./landingMotion";
import {
  landingContentClass,
  landingSectionLeadClass,
  landingSectionShellClass,
  landingSectionTitleClass,
  landingTitleGradientBySection,
} from "./landingType";

const highlights = [
  { icon: FileText, text: "Connect GitHub, Drive, Gmail, Calendar, Notion, Slack" },
  { icon: Search, text: "DeepSpace missions with live SSE and mission canvas visibility" },
  { icon: Database, text: "Durable memory, proactive workspace, and long-session stability" },
  { icon: Users, text: "Grounded answers, workspace deliverables, and approval-based sharing" },
  {
    icon: Shield,
    text: "Private-by-default accounts, approvals, audit logs, and tenant isolation",
  },
];

export default function CallToAction() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 14,
    scaleRange: [0.994, 1.008],
  });

  return (
    <motion.section ref={ref} style={style} className={landingSectionShellClass}>
      <div className={`${landingContentClass} text-center`}>
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ duration: 0.5 }}
          className="mx-auto max-w-4xl space-y-6 sm:space-y-8"
        >
          <h2 className={`${landingSectionTitleClass} ${landingTitleGradientBySection.cta}`}>
            Ready to turn your entire ecosystem into{" "}
            <span className="text-inherit">an operator-grade agentic work system</span>?
          </h2>
          <p className={`${landingSectionLeadClass} text-muted-foreground/90 mx-auto max-w-2xl`}>
            Stop stitching together disconnected tools manually. Connect your workspace, ask
            questions, launch visible missions, inspect the runtime, approve risky actions when
            needed, and turn results into durable notes, tasks, and follow-up work backed by real
            evidence and production safety boundaries.
          </p>

          {/* Highlights */}
          <div className="flex flex-wrap justify-center gap-2.5 pt-2 sm:gap-3">
            {highlights.map((h, i) => {
              const Icon = h.icon;
              return (
                <div
                  key={i}
                  className="border-glass-border bg-surface-0 text-muted-foreground flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] shadow-sm sm:px-4 sm:py-2 sm:text-sm"
                >
                  <Icon size={14} className="text-primary" />
                  {h.text}
                </div>
              );
            })}
          </div>

          {/* CTA buttons */}
          <div className="grid gap-3 pt-4 sm:flex sm:flex-row sm:justify-center sm:gap-4">
            <Link
              href="/documentation"
              className="group bg-primary text-primary-foreground shadow-primary/35 inline-flex items-center justify-center gap-2.5 rounded-full px-6 py-3.5 text-sm font-bold shadow-[0_20px_60px_rgba(var(--primary),0.35)] transition-all hover:translate-y-[-2px] hover:shadow-[0_28px_70px_rgba(var(--primary),0.45)] hover:brightness-110 sm:px-10 sm:py-4.5 sm:text-base"
            >
              Read the Docs
              <ArrowRight size={16} className="transition-transform group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/auth/signup"
              className="bg-surface-0 border-glass-border text-foreground hover:bg-muted inline-flex items-center justify-center rounded-full border px-6 py-3.5 text-sm font-bold shadow-sm transition sm:px-10 sm:py-4.5 sm:text-base"
            >
              Start Using AverQel
            </Link>
            <Link
              href="/auth/login"
              className="text-muted-foreground hover:text-primary inline-flex items-center justify-center rounded-full px-3 py-2 text-sm font-semibold transition"
            >
              Log In
            </Link>
          </div>
        </motion.div>
      </div>
    </motion.section>
  );
}
