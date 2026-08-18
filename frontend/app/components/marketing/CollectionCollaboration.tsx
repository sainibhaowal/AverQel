"use client";

import { motion } from "framer-motion";
import {
  FileLock2,
  FolderHeart,
  ImagePlus,
  MessageCircleMore,
  ShieldCheck,
  UsersRound,
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

const collaborationSteps = [
  {
    icon: UsersRound,
    label: "Invite deliberately",
    detail: "Owners invite members and keep collection access explicit.",
    color: "text-emerald-300 border-emerald-400/25 bg-emerald-500/[0.08]",
  },
  {
    icon: MessageCircleMore,
    label: "Talk in real time",
    detail: "Encrypted collection messages keep the project conversation together.",
    color: "text-cyan-300 border-cyan-400/25 bg-cyan-500/[0.08]",
  },
  {
    icon: ImagePlus,
    label: "Send files securely",
    detail: "Share photos and file attachments as encrypted collection media.",
    color: "text-violet-300 border-violet-400/25 bg-violet-500/[0.08]",
  },
  {
    icon: FolderHeart,
    label: "Share the source once",
    detail:
      "Add an existing document to the collection instead of duplicating it for every member.",
    color: "text-amber-300 border-amber-400/25 bg-amber-500/[0.08]",
  },
];

export default function CollectionCollaboration() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 14,
    scaleRange: [0.995, 1.006],
  });

  return (
    <motion.section
      ref={ref}
      style={style}
      id="secure-collaboration"
      className={landingSectionShellClass}
    >
      <div className={landingContentClass}>
        <motion.div
          initial={{ opacity: 0, y: 22 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ type: "spring", stiffness: 100, damping: 20 }}
          className={landingHeaderWrapClass}
        >
          <p className={landingEyebrowClass}>Collections · Secure Collaboration</p>
          <h2
            className={`${landingSectionTitleClass} ${landingTitleGradientBySection.platformSurfaces}`}
          >
            A shared room for messages, media, and source material
          </h2>
          <p className={landingSectionLeadClass}>
            Collections let approved people work together without opening an entire workspace. Chat
            in real time, exchange encrypted attachments, and share the documents that belong to the
            project. Members see and use only the sources their collection permissions allow.
          </p>
        </motion.div>

        <div className="grid gap-5 lg:grid-cols-[0.82fr_1.18fr] lg:items-stretch">
          <motion.div
            initial={{ opacity: 0, x: -22 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ type: "spring", stiffness: 82, damping: 18 }}
            className="theme-panel relative overflow-hidden rounded-3xl border border-emerald-400/20 p-6 shadow-[0_30px_90px_rgba(0,255,163,0.08)] sm:p-8"
          >
            <div className="pointer-events-none absolute -top-20 -right-20 h-56 w-56 rounded-full bg-emerald-400/[0.10] blur-[80px]" />
            <div className="relative flex h-full flex-col justify-between gap-10">
              <div>
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-2 rounded-full border border-emerald-400/25 bg-emerald-400/[0.08] px-3 py-1.5 text-[10px] font-bold tracking-[0.18em] text-emerald-200 uppercase">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-300" />
                    Collection room
                  </span>
                  <ShieldCheck size={18} className="text-emerald-300" />
                </div>
                <h3 className="mt-7 text-2xl font-black tracking-tight text-white sm:text-3xl">
                  Keep the people, permissions, and project context together.
                </h3>
                <p className="mt-4 text-sm leading-7 text-slate-300">
                  Shared documents remain in controlled storage. The collection grants access to the
                  same source instead of creating a separate copy for every member.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs text-slate-300">
                <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                  <p className="text-lg font-black text-white">E2EE</p>
                  <p className="mt-1">messages and media</p>
                </div>
                <div className="rounded-2xl border border-white/[0.08] bg-white/[0.03] p-4">
                  <p className="text-lg font-black text-white">Scoped</p>
                  <p className="mt-1">document access</p>
                </div>
              </div>
            </div>
          </motion.div>

          <div className="grid gap-3 sm:grid-cols-2">
            {collaborationSteps.map((step, index) => {
              const Icon = step.icon;
              return (
                <motion.article
                  key={step.label}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, margin: "-80px" }}
                  transition={{ type: "spring", stiffness: 88, damping: 18, delay: index * 0.06 }}
                  whileHover={{ y: -4 }}
                  className="theme-panel rounded-2xl border border-white/[0.08] p-5 transition-shadow duration-300 hover:border-white/[0.16] hover:shadow-[0_22px_60px_rgba(0,0,0,0.24)]"
                >
                  <span
                    className={`flex h-11 w-11 items-center justify-center rounded-2xl border ${step.color}`}
                  >
                    <Icon size={18} />
                  </span>
                  <p className="mt-5 text-base font-black text-white">{step.label}</p>
                  <p className="mt-2 text-sm leading-6 text-slate-400">{step.detail}</p>
                </motion.article>
              );
            })}
          </div>
        </div>

        <div className="mt-5 flex items-start gap-3 rounded-2xl border border-cyan-400/15 bg-cyan-500/[0.05] px-5 py-4 text-xs leading-6 text-slate-300">
          <FileLock2 size={16} className="mt-1 shrink-0 text-cyan-300" />
          <p>
            Document querying remains permission-aware: a member can use a shared source only when
            that collection and its document access are approved and available to the workspace.
          </p>
        </div>
      </div>
    </motion.section>
  );
}
