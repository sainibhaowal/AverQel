"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  Check,
  FileCheck2,
  FileText,
  FolderOpen,
  LockKeyhole,
  MessageSquareText,
  MoreHorizontal,
  SearchCheck,
  Send,
  ShieldCheck,
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

const members = [
  { initials: "RS", tone: "bg-cyan-400/20 text-cyan-200" },
  { initials: "AK", tone: "bg-violet-400/20 text-violet-200" },
  { initials: "JM", tone: "bg-amber-400/20 text-amber-200" },
];

export default function WorkspaceOrbit() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 20,
    scaleRange: [0.99, 1.006],
  });
  const reduceMotion = useReducedMotion();

  return (
    <motion.section ref={ref} style={style} className={landingSectionShellClass}>
      <div className={landingContentClass}>
        <div className="grid items-center gap-12 xl:grid-cols-[minmax(0,0.78fr)_minmax(0,1.22fr)] xl:gap-18">
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
              Work together with the context in view
            </h2>
            <p className={`${landingSectionLeadClass} mx-0 max-w-xl text-left`}>
              Collections, Documents Hub, and DeepSpace meet in one permission-aware workspace. The
              interface below is an illustrated product flow based on the real surfaces, not a claim
              that every account is connected automatically.
            </p>
            <div className="mt-8 border-l border-cyan-300/35 pl-5">
              <p className="text-sm font-bold text-white">A shared source, not a copied source.</p>
              <p className="mt-2 max-w-lg text-sm leading-7 text-slate-400">
                Invite members, exchange encrypted messages and files, then add the exact documents
                the collection is allowed to use.
              </p>
            </div>
            <Link
              href="#secure-collaboration"
              className="mt-9 inline-flex items-center gap-2 rounded-full border border-cyan-300/25 bg-cyan-300/[0.08] px-5 py-3 text-sm font-bold text-cyan-100 transition-all hover:border-cyan-200/60 hover:bg-cyan-300/[0.14]"
            >
              See secure collaboration <ArrowRight size={16} />
            </Link>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 28 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ type: "spring", stiffness: 80, damping: 18, delay: 0.06 }}
            className="relative overflow-hidden rounded-[2.3rem] border border-white/10 bg-[radial-gradient(circle_at_70%_25%,rgba(0,184,255,0.16),transparent_28%),linear-gradient(145deg,rgba(9,17,25,0.98),rgba(4,8,14,0.96))] p-3 shadow-[0_38px_120px_rgba(0,0,0,0.45)] sm:p-5"
          >
            <div className="absolute inset-0 [background-image:linear-gradient(rgba(108,255,219,0.06)_1px,transparent_1px),linear-gradient(90deg,rgba(108,255,219,0.06)_1px,transparent_1px)] [background-size:30px_30px] opacity-60" />
            <div className="relative overflow-hidden rounded-[1.6rem] border border-white/[0.11] bg-[#071018]/95 shadow-[0_20px_80px_rgba(0,0,0,0.42)]">
              <div className="flex h-11 items-center justify-between border-b border-white/[0.08] px-4">
                <div className="flex items-center gap-2 text-[10px] font-black tracking-[0.18em] text-slate-400 uppercase">
                  <span className="h-2 w-2 rounded-full bg-emerald-300 shadow-[0_0_14px_#6ee7b7]" />
                  Research room / Antimatter
                </div>
                <div className="flex items-center gap-1">
                  {members.map((member) => (
                    <span
                      key={member.initials}
                      className={`flex h-6 w-6 items-center justify-center rounded-full text-[9px] font-black ${member.tone}`}
                    >
                      {member.initials}
                    </span>
                  ))}
                  <span className="ml-1 flex h-6 w-6 items-center justify-center rounded-full border border-white/10 text-slate-500">
                    <MoreHorizontal size={13} />
                  </span>
                </div>
              </div>

              <div className="grid min-h-[390px] lg:grid-cols-[0.78fr_1.38fr_0.9fr]">
                <aside className="hidden border-r border-white/[0.08] p-4 lg:block">
                  <p className="font-mono text-[9px] font-bold tracking-[0.18em] text-slate-500 uppercase">
                    Collections
                  </p>
                  <div className="mt-4 space-y-2 text-xs">
                    <div className="rounded-xl border border-cyan-300/20 bg-cyan-300/[0.08] px-3 py-2.5 text-cyan-100">
                      <FolderOpen size={13} className="mr-2 inline" /> Research room
                    </div>
                    <div className="px-3 py-2 text-slate-500">Course materials</div>
                    <div className="px-3 py-2 text-slate-500">Product brief</div>
                  </div>
                  <div className="mt-8 border-t border-white/[0.07] pt-4">
                    <p className="font-mono text-[9px] font-bold tracking-[0.18em] text-slate-500 uppercase">
                      Shared sources
                    </p>
                    <div className="mt-3 space-y-3 text-[11px] text-slate-400">
                      <p>
                        <FileCheck2 size={13} className="mr-2 inline text-emerald-300" />{" "}
                        PET-study.pdf
                      </p>
                      <p>
                        <FileText size={13} className="mr-2 inline text-cyan-300" /> lab-notes.md
                      </p>
                    </div>
                  </div>
                </aside>

                <main className="flex min-h-[390px] flex-col border-white/[0.08] p-4 lg:border-r">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-black text-white">Room conversation</p>
                      <p className="mt-1 text-[10px] text-slate-500">
                        Encrypted messages · 3 members
                      </p>
                    </div>
                    <MessageSquareText size={16} className="text-cyan-300" />
                  </div>
                  <div className="mt-6 flex-1 space-y-4">
                    <div className="flex gap-2">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-violet-400/20 text-[9px] font-black text-violet-200">
                        AK
                      </span>
                      <div className="rounded-2xl rounded-tl-sm border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-xs leading-5 text-slate-300">
                        Can we compare the PET sources in the shared room?
                      </div>
                    </div>
                    <div className="flex justify-end gap-2">
                      <div className="rounded-2xl rounded-tr-sm border border-cyan-300/20 bg-cyan-300/[0.08] px-3 py-2 text-xs leading-5 text-cyan-50">
                        Yes, only approved sources are in scope.
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-400/20 text-[9px] font-black text-amber-200">
                        JM
                      </span>
                      <div className="rounded-2xl rounded-tl-sm border border-white/[0.08] bg-white/[0.04] px-3 py-2 text-xs leading-5 text-slate-300">
                        <span className="mb-2 flex items-center gap-2 text-[10px] text-emerald-200">
                          <LockKeyhole size={11} /> encrypted attachment
                        </span>
                        PET-study.pdf · shared source
                      </div>
                    </div>
                  </div>
                  <div className="mt-6 flex shrink-0 items-center gap-2 rounded-xl border border-white/[0.08] bg-black/20 px-3 py-2 text-xs text-slate-500">
                    Write to the room… <Send size={13} className="ml-auto text-cyan-300" />
                  </div>
                </main>

                <aside className="p-4">
                  <p className="font-mono text-[9px] font-bold tracking-[0.18em] text-slate-500 uppercase">
                    Access &amp; context
                  </p>
                  <div className="mt-4 rounded-xl border border-emerald-300/20 bg-emerald-300/[0.06] p-3">
                    <div className="flex items-center gap-2 text-xs font-bold text-emerald-100">
                      <ShieldCheck size={14} /> Policy checked
                    </div>
                    <p className="mt-2 text-[10px] leading-4 text-slate-400">
                      Members can use permitted collection documents.
                    </p>
                  </div>
                  <div className="mt-3 space-y-2">
                    {["PET-study.pdf", "lab-notes.md"].map((file, index) => (
                      <motion.div
                        key={file}
                        animate={reduceMotion ? undefined : { opacity: [0.72, 1, 0.72] }}
                        transition={{ duration: 3.2, delay: index * 0.4, repeat: Infinity }}
                        className="flex items-center gap-2 rounded-xl border border-white/[0.07] bg-white/[0.025] px-3 py-2 text-[10px] text-slate-300"
                      >
                        <FileText size={13} className="text-cyan-300" /> {file}
                        <Check size={12} className="ml-auto text-emerald-300" />
                      </motion.div>
                    ))}
                  </div>
                  <div className="mt-5 border-t border-white/[0.07] pt-4 text-[10px] text-slate-500">
                    <p className="flex items-center gap-2">
                      <SearchCheck size={13} className="text-amber-200" /> Query-ready when approved
                    </p>
                    <p className="mt-3 flex items-center gap-2">
                      <LockKeyhole size={13} className="text-violet-200" /> Scoped to this room
                    </p>
                  </div>
                </aside>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </motion.section>
  );
}
