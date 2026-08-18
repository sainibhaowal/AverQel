"use client";

import { useRef } from "react";
import { motion, useInView } from "framer-motion";
import {
  Upload,
  Cpu,
  MessageSquareText,
  Users,
  FileText,
  Layers,
  Brain,
  CheckCheck,
  Quote,
  BarChart3,
  FolderLock,
  UserCheck,
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

// ─── Data (unchanged) ─────────────────────────────────────────────────────────
const stages = [
  {
    step: "01",
    title: "Choose a provider and add your source material",
    description:
      "Start with a cloud or local AI provider, then upload supported documents into the Documents Hub. Connected apps are optional and are authorized separately through the MCP marketplace.",
    icon: Upload,
    accent: "blue",
    details: [
      { icon: FileText, text: "Documents Hub for supported files and source inspection" },
      { icon: Layers, text: "Optional supported app connections through OAuth" },
      { icon: BarChart3, text: "Provider, connection, and processing status stay visible" },
    ],
  },
  {
    step: "02",
    title: "Make documents ready for grounded work",
    description:
      "AverQel processes supported documents into searchable context. You can follow accepted, processing, indexed, retry, and extraction-quality states instead of assuming every file succeeded.",
    icon: Cpu,
    accent: "cyan",
    details: [
      { icon: Layers, text: "Parse | chunk | embed | index | source inspection" },
      { icon: Brain, text: "Grounded retrieval context for accessible documents" },
      { icon: CheckCheck, text: "Retry and quarantine paths for problematic data" },
    ],
  },
  {
    step: "03",
    title: "Ask, verify, then move into DeepSpace",
    description:
      "Use Grounded Query when evidence from documents is the priority. Use DeepSpace when you need research, drafting, notes, memory, or a controlled tool-assisted workflow in the same conversation.",
    icon: MessageSquareText,
    accent: "violet",
    details: [
      { icon: Quote, text: "Grounded answers, citations, and source inspection" },
      { icon: BarChart3, text: "DeepSpace activity, notes, memory, and saved history" },
      { icon: Brain, text: "External effects stay behind policy and approval controls" },
    ],
  },
  {
    step: "04",
    title: "Organize and share with deliberate scope",
    description:
      "Organize documents into collections and share them through invitation and approval workflows. You choose exactly which documents to include, and owners keep control of what is visible.",
    icon: Users,
    accent: "emerald",
    details: [
      { icon: FolderLock, text: "Invite by collection code, approve or deny requests" },
      { icon: FileText, text: "Selective document inclusion, never forced global sharing" },
      { icon: UserCheck, text: "Owner and shared roles with distinct permissions" },
    ],
  },
];

// ─── Accent system ─────────────────────────────────────────────────────────────
const accentStyles: Record<
  string,
  {
    dot: string;
    dotInner: string;
    dotPulse: string;
    leftBar: string;
    icon: string;
    stepLabel: string;
    detailBar: string;
    detailIcon: string;
    watermark: string;
    glowBg: string;
  }
> = {
  blue: {
    dot: "border-blue-400/40 bg-blue-500/[0.1]",
    dotInner: "bg-blue-400",
    dotPulse: "bg-blue-400",
    leftBar: "from-blue-500 via-blue-400/50 to-transparent",
    icon: "bg-blue-500/[0.1] text-blue-300 border-blue-400/20",
    stepLabel: "text-blue-400/55",
    detailBar: "bg-blue-400/55",
    detailIcon: "text-blue-400",
    watermark: "text-blue-500/[0.055]",
    glowBg: "bg-blue-500/[0.1]",
  },
  cyan: {
    dot: "border-cyan-400/40 bg-cyan-500/[0.1]",
    dotInner: "bg-cyan-400",
    dotPulse: "bg-cyan-400",
    leftBar: "from-cyan-500 via-cyan-400/50 to-transparent",
    icon: "bg-cyan-500/[0.1] text-cyan-300 border-cyan-400/20",
    stepLabel: "text-cyan-400/55",
    detailBar: "bg-cyan-400/55",
    detailIcon: "text-cyan-400",
    watermark: "text-cyan-500/[0.055]",
    glowBg: "bg-cyan-500/[0.1]",
  },
  violet: {
    dot: "border-violet-400/40 bg-violet-500/[0.1]",
    dotInner: "bg-violet-400",
    dotPulse: "bg-violet-400",
    leftBar: "from-violet-500 via-violet-400/50 to-transparent",
    icon: "bg-violet-500/[0.1] text-violet-300 border-violet-400/20",
    stepLabel: "text-violet-400/55",
    detailBar: "bg-violet-400/55",
    detailIcon: "text-violet-400",
    watermark: "text-violet-500/[0.055]",
    glowBg: "bg-violet-500/[0.1]",
  },
  emerald: {
    dot: "border-emerald-400/40 bg-emerald-500/[0.1]",
    dotInner: "bg-emerald-400",
    dotPulse: "bg-emerald-400",
    leftBar: "from-emerald-500 via-emerald-400/50 to-transparent",
    icon: "bg-emerald-500/[0.1] text-emerald-300 border-emerald-400/20",
    stepLabel: "text-emerald-400/55",
    detailBar: "bg-emerald-400/55",
    detailIcon: "text-emerald-400",
    watermark: "text-emerald-500/[0.055]",
    glowBg: "bg-emerald-500/[0.1]",
  },
};

// ─── Motion variants ───────────────────────────────────────────────────────────

/** Stage card: spring slide-up, staggered by index */
const cardVariants = {
  hidden: { opacity: 0, y: 30 },
  visible: (delay: number) => ({
    opacity: 1,
    y: 0,
    transition: { type: "spring" as const, stiffness: 65, damping: 16, delay },
  }),
};

/** Detail rows: stagger container */
const detailContainerVariants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.09, delayChildren: 0.18 },
  },
};

/** Individual detail row: slides in from left */
const detailRowVariants = {
  hidden: { opacity: 0, x: -10 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { type: "spring" as const, stiffness: 100, damping: 20 },
  },
};

// ─── Pulsing timeline dot ──────────────────────────────────────────────────────
function PulseDot({ accentKey, pulseDelay }: { accentKey: string; pulseDelay: number }) {
  const styles = accentStyles[accentKey];
  return (
    <div className="absolute top-[26px] left-[13px] z-10 hidden lg:block">
      {/* Expanding pulse ring */}
      <motion.div
        className={`absolute inset-[-5px] rounded-full ${styles.dotPulse}`}
        animate={{ scale: [0.85, 1.7], opacity: [0.45, 0] }}
        transition={{
          duration: 2.2,
          repeat: Infinity,
          ease: "easeOut",
          delay: pulseDelay,
        }}
      />
      {/* Outer ring + center dot */}
      <div
        className={`flex h-7 w-7 items-center justify-center rounded-full border-2 ${styles.dot}`}
      >
        <div className={`h-2 w-2 rounded-full ${styles.dotInner}`} />
      </div>
    </div>
  );
}

// ─── Header meta chips ─────────────────────────────────────────────────────────
const headerChips = [
  { dot: "bg-blue-400", label: "4 pipeline stages" },
  { dot: "bg-emerald-400", label: "Approval-gated writes" },
  { dot: "bg-violet-400", label: "Live SSE streaming" },
];

// ─── Component ─────────────────────────────────────────────────────────────────
export default function HowItWorks() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 20,
    scaleRange: [0.992, 1.01],
  });

  // Animate vertical line drawing in on scroll
  const lineRef = useRef<HTMLDivElement>(null);
  const lineInView = useInView(lineRef, { once: true, margin: "-80px" });

  return (
    <motion.section ref={ref} style={style} id="how-it-works" className={landingSectionShellClass}>
      {/* Ambient background glows */}
      <div className="pointer-events-none absolute top-1/4 left-[-8rem] h-80 w-80 rounded-full bg-blue-500/[0.05] blur-[140px]" />
      <div className="pointer-events-none absolute right-[-6rem] bottom-1/4 h-72 w-72 rounded-full bg-violet-500/[0.05] blur-[120px]" />

      <div className={landingContentClass}>
        {/* ── Section header ───────────────────────────────────────────────── */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ type: "spring", stiffness: 90, damping: 20 }}
          className={landingHeaderWrapClass}
        >
          {/* Eyebrow with decorative flanking line */}
          <div className="mb-5 flex items-center gap-3">
            <div className="h-px w-8 bg-white/25" />
            <p className={landingEyebrowClass}>How It Works</p>
          </div>

          <h2 className={`${landingSectionTitleClass} ${landingTitleGradientBySection.howItWorks}`}>
            A clear path from documents to grounded answers and finished work
          </h2>

          <p className={`${landingSectionLeadClass} mt-4`}>
            AverQel is not only a file bucket or a generic chatbot. It gives users a practical path:
            create a private workspace, organize material, ask grounded questions, do deeper work,
            and connect external apps only under explicit controls.
          </p>

          {/* Meta chips, stagger in after header */}
          <motion.div
            className="mt-8 flex flex-wrap gap-2"
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: "-60px" }}
            variants={{
              hidden: {},
              visible: { transition: { staggerChildren: 0.08, delayChildren: 0.2 } },
            }}
          >
            {headerChips.map(({ dot, label }) => (
              <motion.span
                key={label}
                variants={{
                  hidden: { opacity: 0, y: 6 },
                  visible: {
                    opacity: 1,
                    y: 0,
                    transition: { type: "spring", stiffness: 120, damping: 20 },
                  },
                }}
                className="flex items-center gap-2 rounded-full border border-white/[0.08] bg-white/[0.04] px-3.5 py-1.5"
              >
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${dot} opacity-80`} />
                <span className="text-muted-foreground font-mono text-[11px] tracking-wide">
                  {label}
                </span>
              </motion.span>
            ))}
          </motion.div>
        </motion.div>

        {/* ── Steps ────────────────────────────────────────────────────────── */}
        <div className="relative" ref={lineRef}>
          {/* Vertical connector line, draws in with scaleY on scroll */}
          <motion.div
            initial={{ scaleY: 0, opacity: 0 }}
            animate={lineInView ? { scaleY: 1, opacity: 1 } : {}}
            transition={{ duration: 1.8, ease: [0.16, 1, 0.3, 1], delay: 0.3 }}
            style={{ originY: 0 }}
            className="absolute top-0 bottom-0 left-8 hidden w-px bg-gradient-to-b from-transparent via-white/[0.07] to-transparent lg:block"
          />

          <div className="space-y-4 lg:space-y-3">
            {stages.map((stage, index) => {
              const Icon = stage.icon;
              const styles = accentStyles[stage.accent];

              return (
                /* Scroll-entry animation wrapper */
                <motion.div
                  key={stage.step}
                  custom={index * 0.09}
                  initial="hidden"
                  whileInView="visible"
                  viewport={{ once: true, margin: "-80px" }}
                  variants={cardVariants}
                  className="relative lg:pl-24 last:lg:pb-0"
                >
                  {/* Pulsing timeline dot */}
                  <PulseDot accentKey={stage.accent} pulseDelay={index * 0.35} />

                  {/* Hover lift wrapper, separate from scroll animation */}
                  <motion.div
                    whileHover={{ y: -3 }}
                    transition={{ type: "spring", stiffness: 380, damping: 28 }}
                    className={`group theme-panel relative overflow-hidden rounded-2xl border transition-colors duration-500 hover:border-white/[0.13]`}
                  >
                    {/* ── Left gradient accent bar (3px vertical) ──────────── */}
                    <div
                      className={`absolute top-0 bottom-0 left-0 w-[3px] bg-gradient-to-b ${styles.leftBar}`}
                    />

                    {/* ── Watermark step number ─────────────────────────────── */}
                    <span
                      className={`pointer-events-none absolute -top-4 right-5 font-mono text-[108px] leading-none font-black select-none ${styles.watermark}`}
                    >
                      {stage.step}
                    </span>

                    {/* Hover glow blob, top-right corner */}
                    <div
                      className={`pointer-events-none absolute -top-16 -right-16 h-56 w-56 rounded-full blur-[80px] ${styles.glowBg} opacity-0 transition-opacity duration-700 group-hover:opacity-100`}
                    />

                    {/* ── Card content ──────────────────────────────────────── */}
                    <div className="relative grid gap-5 p-5 pl-7 sm:p-6 sm:pl-8 lg:p-8 lg:pl-10 xl:grid-cols-[1fr_1.15fr] xl:gap-10">
                      {/* Left: Stage label + title + description */}
                      <div>
                        <div className="mb-3 flex items-center gap-3">
                          <span
                            className={`font-mono text-[10px] tracking-[0.2em] uppercase ${styles.stepLabel}`}
                          >
                            Stage {stage.step}
                          </span>
                          {/* Mobile icon, hidden on xl */}
                          <div
                            className={`flex h-9 w-9 items-center justify-center rounded-xl border xl:hidden ${styles.icon}`}
                          >
                            <Icon size={16} />
                          </div>
                        </div>

                        <h3 className="text-foreground text-lg leading-snug font-bold sm:text-xl">
                          {stage.title}
                        </h3>

                        <p className="text-muted-foreground mt-3 text-sm leading-7">
                          {stage.description}
                        </p>
                      </div>

                      {/* Right: Detail rows, staggered slide-in */}
                      <motion.div
                        initial="hidden"
                        whileInView="visible"
                        viewport={{ once: true, margin: "-60px" }}
                        variants={detailContainerVariants}
                      >
                        {/* Separator label, mobile only */}
                        <div className="mb-3 flex items-center gap-3 xl:hidden">
                          <div className="h-px flex-1 bg-white/[0.06]" />
                          <span className="font-mono text-[9px] tracking-[0.18em] text-white/[0.22] uppercase">
                            Details
                          </span>
                          <div className="h-px flex-1 bg-white/[0.06]" />
                        </div>

                        {stage.details.map((detail, di) => {
                          const DetailIcon = detail.icon;
                          const isLastDetail = di === stage.details.length - 1;
                          return (
                            <motion.div
                              key={di}
                              variants={detailRowVariants}
                              className={`group/row flex items-start gap-3 py-3 ${
                                isLastDetail ? "" : "border-b border-white/[0.05]"
                              }`}
                            >
                              {/* Left accent bar, grows on row hover */}
                              <div
                                className={`mt-[5px] h-3 w-[2px] shrink-0 rounded-full ${styles.detailBar} transition-all duration-200 group-hover/row:h-4`}
                              />

                              <DetailIcon
                                size={13}
                                className={`mt-0.5 shrink-0 ${styles.detailIcon} opacity-50 transition-opacity duration-200 group-hover/row:opacity-90`}
                              />

                              <p className="text-muted-foreground group-hover/row:text-foreground/70 text-sm leading-6 transition-colors duration-200">
                                {detail.text}
                              </p>
                            </motion.div>
                          );
                        })}
                      </motion.div>
                    </div>
                  </motion.div>
                </motion.div>
              );
            })}
          </div>
        </div>
      </div>
    </motion.section>
  );
}
