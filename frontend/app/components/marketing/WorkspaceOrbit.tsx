"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  Bot,
  BrainCircuit,
  Check,
  FileText,
  FolderOpen,
  LockKeyhole,
  Network,
  SearchCheck,
  Sparkles,
} from "lucide-react";
import { useLandingSectionMotion } from "./landingMotion";
import {
  landingContentClass,
  landingEyebrowClass,
  landingSectionLeadClass,
  landingSectionShellClass,
  landingSectionTitleClass,
  landingTitleGradientBySection,
} from "./landingType";

const orbitNodes = [
  {
    label: "Library",
    icon: FolderOpen,
    tone: "text-cyan-300 border-cyan-300/30 bg-cyan-400/10",
    x: "left-[5%] top-[14%]",
  },
  {
    label: "Memory",
    icon: BrainCircuit,
    tone: "text-violet-300 border-violet-300/30 bg-violet-400/10",
    x: "right-[3%] top-[12%]",
  },
  {
    label: "Evidence",
    icon: SearchCheck,
    tone: "text-amber-200 border-amber-300/30 bg-amber-300/10",
    x: "left-[6%] bottom-[13%]",
  },
  {
    label: "MCP",
    icon: Network,
    tone: "text-emerald-300 border-emerald-300/30 bg-emerald-300/10",
    x: "right-[4%] bottom-[13%]",
  },
] as const;

function Connector({ className }: { className: string }) {
  return (
    <motion.span
      aria-hidden="true"
      className={`absolute h-px origin-left bg-gradient-to-r from-transparent via-cyan-200/50 to-transparent ${className}`}
      animate={{ opacity: [0.24, 0.85, 0.24], scaleX: [0.86, 1, 0.86] }}
      transition={{ duration: 3.2, repeat: Infinity, ease: "easeInOut" }}
    />
  );
}

export default function WorkspaceOrbit() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 20,
    scaleRange: [0.99, 1.006],
  });
  const reduceMotion = useReducedMotion();

  return (
    <motion.section ref={ref} style={style} className={landingSectionShellClass}>
      <div className={landingContentClass}>
        <div className="grid items-center gap-12 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] xl:gap-18">
          <motion.div
            initial={{ opacity: 0, x: -24 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-90px" }}
            transition={{ type: "spring", stiffness: 90, damping: 20 }}
          >
            <p className={`${landingEyebrowClass} mx-0 text-left`}>One Connected Workspace</p>
            <h2
              className={`${landingSectionTitleClass} ${landingTitleGradientBySection.orchestration} mx-0 max-w-[12ch] text-left`}
            >
              The intelligence is not a separate tab
            </h2>
            <p className={`${landingSectionLeadClass} mx-0 max-w-xl text-left`}>
              A clear visual model of how documents, grounded evidence, DeepSpace, memory, and
              authorized connections work together—without pretending that external access is
              automatic.
            </p>

            <div className="mt-8 border-l border-cyan-300/35 pl-5">
              <p className="text-sm font-bold text-white">Start with what you control.</p>
              <p className="mt-2 max-w-lg text-sm leading-7 text-slate-400">
                Add documents, build collections, choose a provider, and authorize a connection only
                when it is useful. DeepSpace keeps the working context visible along the way.
              </p>
            </div>

            <Link
              href="#how-it-works"
              className="mt-9 inline-flex items-center gap-2 rounded-full border border-cyan-300/25 bg-cyan-300/[0.08] px-5 py-3 text-sm font-bold text-cyan-100 transition-all hover:border-cyan-200/60 hover:bg-cyan-300/[0.14]"
            >
              Explore the workflow <ArrowRight size={16} />
            </Link>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 28 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ type: "spring", stiffness: 80, damping: 18, delay: 0.06 }}
            className="relative min-h-[430px] overflow-hidden rounded-[2.3rem] border border-white/10 bg-[radial-gradient(circle_at_50%_45%,rgba(0,184,255,0.14),transparent_24%),linear-gradient(145deg,rgba(9,17,25,0.96),rgba(4,8,14,0.9))] p-4 shadow-[0_38px_120px_rgba(0,0,0,0.45)] sm:min-h-[520px] sm:p-7"
          >
            <div className="absolute inset-0 [background-image:linear-gradient(rgba(108,255,219,0.07)_1px,transparent_1px),linear-gradient(90deg,rgba(108,255,219,0.07)_1px,transparent_1px)] [background-size:30px_30px] opacity-50" />
            <div className="pointer-events-none absolute top-1/2 left-1/2 h-[46%] w-[46%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-300/15" />
            <div className="pointer-events-none absolute top-1/2 left-1/2 h-[72%] w-[72%] -translate-x-1/2 -translate-y-1/2 rounded-full border border-dashed border-cyan-200/10" />
            <Connector className="top-[30%] left-[21%] w-[32%] rotate-[21deg]" />
            <Connector className="top-[32%] left-[49%] w-[31%] rotate-[157deg]" />
            <Connector className="top-[68%] left-[21%] w-[31%] -rotate-[20deg]" />
            <Connector className="top-[68%] left-[49%] w-[31%] rotate-[202deg]" />

            <div className="relative z-10 flex items-center justify-between font-mono text-[10px] font-bold tracking-[0.18em] text-slate-500 uppercase">
              <span>Workspace map</span>
              <span className="flex items-center gap-2 text-emerald-300">
                <span className="h-2 w-2 rounded-full bg-emerald-300 shadow-[0_0_14px_#6ee7b7]" />{" "}
                Active context
              </span>
            </div>

            {orbitNodes.map((node, index) => {
              const Icon = node.icon;
              return (
                <motion.div
                  key={node.label}
                  className={`absolute z-20 ${node.x}`}
                  animate={reduceMotion ? undefined : { y: [0, index % 2 ? -8 : 8, 0] }}
                  transition={{
                    duration: 4.2 + index * 0.3,
                    repeat: Infinity,
                    ease: "easeInOut",
                    delay: index * 0.28,
                  }}
                >
                  <div
                    className={`flex items-center gap-2 rounded-2xl border px-3 py-2.5 shadow-[0_12px_40px_rgba(0,0,0,0.32)] backdrop-blur-xl ${node.tone}`}
                  >
                    <Icon size={15} />
                    <span className="text-xs font-black tracking-wide text-slate-100">
                      {node.label}
                    </span>
                  </div>
                </motion.div>
              );
            })}

            <motion.div
              className="absolute top-1/2 left-1/2 z-30 w-[min(72%,330px)] -translate-x-1/2 -translate-y-1/2 rounded-[1.7rem] border border-cyan-200/25 bg-[#071018]/90 p-4 shadow-[0_0_0_1px_rgba(86,255,211,0.06),0_25px_90px_rgba(0,0,0,0.5)] backdrop-blur-xl sm:p-5"
              animate={
                reduceMotion
                  ? undefined
                  : {
                      boxShadow: [
                        "0 0 0 1px rgba(86,255,211,0.06),0 25px 90px rgba(0,0,0,0.5)",
                        "0 0 0 1px rgba(86,255,211,0.19),0 25px 100px rgba(0,184,255,0.17)",
                        "0 0 0 1px rgba(86,255,211,0.06),0 25px 90px rgba(0,0,0,0.5)",
                      ],
                    }
              }
              transition={{ duration: 3.6, repeat: Infinity, ease: "easeInOut" }}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-cyan-100">
                  <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-cyan-300/10">
                    <Bot size={16} />
                  </span>
                  <span className="text-xs font-black tracking-[0.16em] uppercase">DeepSpace</span>
                </div>
                <Sparkles size={15} className="text-amber-200" />
              </div>
              <div className="mt-5 rounded-xl border border-white/[0.08] bg-white/[0.03] px-3 py-3 text-xs leading-6 text-slate-300">
                Compare the sources, retain my approved preference, and save the research summary.
              </div>
              <div className="mt-4 flex items-center justify-between gap-3 text-[10px] font-bold tracking-[0.14em] uppercase">
                <span className="flex items-center gap-1.5 text-emerald-200">
                  <Check size={12} /> Evidence linked
                </span>
                <span className="flex items-center gap-1.5 text-violet-200">
                  <LockKeyhole size={12} /> Policy checked
                </span>
              </div>
              <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/[0.07]">
                <motion.div
                  className="h-full rounded-full bg-gradient-to-r from-cyan-300 via-emerald-300 to-violet-300"
                  animate={reduceMotion ? { width: "68%" } : { width: ["18%", "82%", "46%"] }}
                  transition={{ duration: 4.5, repeat: Infinity, ease: "easeInOut" }}
                />
              </div>
            </motion.div>

            <div className="absolute right-5 bottom-5 left-5 z-20 flex items-center justify-between rounded-xl border border-white/[0.07] bg-slate-950/65 px-3 py-2.5 text-[10px] font-bold tracking-[0.16em] text-slate-400 uppercase backdrop-blur-lg sm:right-7 sm:bottom-7 sm:left-7">
              <span className="flex items-center gap-2">
                <FileText size={13} className="text-cyan-300" /> Context stays inspectable
              </span>
              <span className="hidden text-slate-500 sm:block">Illustrated product flow</span>
            </div>
          </motion.div>
        </div>
      </div>
    </motion.section>
  );
}
