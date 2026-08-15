"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { Archive, BrainCircuit, FileOutput, Image, Search, ShieldCheck } from "lucide-react";
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

const capabilities = [
  {
    title: "Memory you can inspect and control",
    short: "DeepSpace Memory",
    icon: BrainCircuit,
    color: "text-violet-300",
    border: "border-violet-400/25",
    background: "bg-violet-500/[0.08]",
    body: "DeepSpace can retain approved preferences and useful workspace facts across conversations. Memory is visible, editable, searchable, exportable, and removable by the user.",
    items: [
      "User and session memory scopes",
      "Memory candidates can require your approval",
      "Search, edit, forget, clean up, or export saved context",
      "Conversation history stays separate from memory facts",
    ],
    href: "/documentation/memory-workspace",
    link: "Read the memory guide",
  },
  {
    title: "A Library for usable output",
    short: "Library + Files",
    icon: Archive,
    color: "text-cyan-300",
    border: "border-cyan-400/25",
    background: "bg-cyan-500/[0.08]",
    body: "Turn DeepSpace work into files you can revisit. The Library supports files, folders, imports, previews, editing for supported text formats, downloads, and workspace-aware file handling.",
    items: [
      "Create and organize files and folders",
      "Import supported local files with visible progress",
      "Preview and edit supported text, Markdown, code, and documents",
      "Download saved workspace files when you need them elsewhere",
    ],
    href: "/documentation/editor-files",
    link: "Explore notes and deliverables",
  },
  {
    title: "Rich answers and media, when a provider returns them",
    short: "Artifacts + Outputs",
    icon: Image,
    color: "text-emerald-300",
    border: "border-emerald-400/25",
    background: "bg-emerald-500/[0.08]",
    body: "AverQel presents structured answers, diagrams, charts, and provider-returned media as usable output. Availability depends on the selected provider and the result it returns.",
    items: [
      "Markdown, diagrams, equations, tables, and charts",
      "Private image, audio, and video artifact delivery when supported",
      "Notes and exports keep useful output close to the conversation",
      "No claim that every provider supports every media type",
    ],
    href: "/documentation/editor-files",
    link: "See output and export support",
  },
  {
    title: "Conversations that stay useful after interruption",
    short: "Durable DeepSpace",
    icon: ShieldCheck,
    color: "text-amber-300",
    border: "border-amber-400/25",
    background: "bg-amber-500/[0.08]",
    body: "DeepSpace persists authorized conversation state, activity, and saved answers so users can return to their work after a browser reload or interruption.",
    items: [
      "Saved conversation history and visible activity",
      "Tenant-scoped run and workspace state",
      "Explicit cancellation and safe recovery boundaries",
      "Provider or remote-service failures remain visible rather than hidden",
    ],
    href: "/documentation/simple-system-walkthrough",
    link: "See the plain-language walkthrough",
  },
];

export default function WorkspaceIntelligence() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 16,
    scaleRange: [0.994, 1.008],
  });
  const [activeIndex, setActiveIndex] = useState(0);
  const active = capabilities[activeIndex];
  const ActiveIcon = active.icon;

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
          <p className={landingEyebrowClass}>Beyond the Answer</p>
          <h2 className={`${landingSectionTitleClass} ${landingTitleGradientBySection.features}`}>
            Keep context, files, and output useful after the chat ends
          </h2>
          <p className={landingSectionLeadClass}>
            AverQel is designed to help users continue work, not only generate a one-time reply.
            Explore the workspace capabilities below.
          </p>
        </motion.div>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
            {capabilities.map((capability, index) => {
              const Icon = capability.icon;
              const selected = index === activeIndex;
              return (
                <button
                  key={capability.short}
                  type="button"
                  onClick={() => setActiveIndex(index)}
                  aria-pressed={selected}
                  className={`flex items-center gap-3 rounded-2xl border p-4 text-left transition-all duration-300 focus-visible:ring-2 focus-visible:ring-cyan-300/70 focus-visible:outline-none ${
                    selected
                      ? `${capability.border} ${capability.background}`
                      : "border-white/[0.07] bg-white/[0.02] hover:border-white/[0.15] hover:bg-white/[0.045]"
                  }`}
                >
                  <span
                    className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border ${capability.border} ${capability.background} ${capability.color}`}
                  >
                    <Icon size={17} />
                  </span>
                  <span className="text-sm font-bold text-white">{capability.short}</span>
                </button>
              );
            })}
          </div>

          <motion.article
            key={active.short}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.24, ease: "easeOut" }}
            className="theme-panel relative overflow-hidden rounded-[1.8rem] border border-white/[0.1] p-6 sm:p-8"
          >
            <div
              className={`pointer-events-none absolute -top-24 -right-24 h-64 w-64 rounded-full blur-[100px] ${active.background}`}
            />
            <div className="relative">
              <div className="flex items-start justify-between gap-5">
                <div>
                  <p
                    className={`text-[10px] font-bold tracking-[0.24em] uppercase ${active.color}`}
                  >
                    Workspace capability
                  </p>
                  <h3 className="mt-3 text-2xl font-black tracking-tight text-white sm:text-3xl">
                    {active.title}
                  </h3>
                </div>
                <span
                  className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border ${active.border} ${active.background} ${active.color}`}
                >
                  <ActiveIcon size={23} />
                </span>
              </div>
              <p className="mt-7 text-base leading-8 text-slate-300">{active.body}</p>
              <ul className="mt-7 grid gap-3 sm:grid-cols-2">
                {active.items.map((item) => (
                  <li
                    key={item}
                    className="flex gap-2.5 rounded-xl border border-white/[0.07] bg-white/[0.025] px-3.5 py-3 text-sm leading-6 text-slate-300"
                  >
                    <Search size={14} className={`mt-1 shrink-0 ${active.color}`} />
                    {item}
                  </li>
                ))}
              </ul>
              <Link
                href={active.href}
                className={`mt-7 inline-flex items-center gap-2 text-sm font-bold ${active.color} transition-opacity hover:opacity-80`}
              >
                <FileOutput size={15} />
                {active.link}
              </Link>
            </div>
          </motion.article>
        </div>
      </div>
    </motion.section>
  );
}
