"use client";

import { motion } from "framer-motion";
import {
  FileText,
  FileCode,
  BookOpen,
  ScanSearch,
  Layers,
  ArrowRight,
  MessageSquareText,
  Mail,
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

const formats = [
  {
    name: "GitHub",
    description: "Repo | Commits | Issues",
    icon: FileCode,
    color: "text-slate-200",
    bg: "bg-slate-500/[0.08] border-slate-400/20",
  },
  {
    name: "Google Drive",
    description: "Docs | Sheets | Folders",
    icon: FileText,
    color: "text-blue-400",
    bg: "bg-blue-500/[0.08] border-blue-400/20",
  },
  {
    name: "Notion",
    description: "Pages | Databases",
    icon: BookOpen,
    color: "text-slate-100",
    bg: "bg-slate-500/[0.08] border-slate-400/20",
  },
  {
    name: "Slack",
    description: "Channels | History",
    icon: MessageSquareText,
    color: "text-violet-400",
    bg: "bg-violet-500/[0.08] border-violet-400/20",
  },
  {
    name: "Web Crawler",
    description: "High-speed URL indexing",
    icon: ScanSearch,
    color: "text-emerald-400",
    bg: "bg-emerald-500/[0.08] border-emerald-400/20",
  },
  {
    name: "PDF",
    description: "Standard and scanned",
    icon: FileText,
    color: "text-red-400",
    bg: "bg-red-500/[0.08] border-red-400/20",
  },
  {
    name: "DOCX",
    description: "Microsoft Word",
    icon: FileText,
    color: "text-blue-400",
    bg: "bg-blue-500/[0.08] border-blue-400/20",
  },
  {
    name: "Gmail",
    description: "Threads | Attachments",
    icon: Mail,
    color: "text-red-400",
    bg: "bg-red-500/[0.08] border-red-400/20",
  },
];

const pipelineStages = [
  { label: "Queued", description: "Upload accepted | job created | worker dispatch" },
  { label: "Download", description: "Object storage fetch | connector payload hydrate" },
  { label: "Parse", description: "Extractor route | OCR | language detect | coverage score" },
  { label: "Chunk", description: "Structured blocks | overlap windows | sanitized chunks" },
  { label: "Embed", description: "Batch vectors | provider metadata | chunk embeddings" },
  { label: "Index", description: "Chunk records | embeddings stored | query-ready state" },
];

export default function SupportedFormats() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 18,
    scaleRange: [0.993, 1.008],
  });

  return (
    <motion.section ref={ref} style={style} className={landingSectionShellClass}>
      <div className={landingContentClass}>
        <div className="grid gap-10 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)] xl:items-stretch xl:gap-12">
          {/* Left: Format grid */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.5 }}
            className={`flex h-full flex-col items-center text-center ${landingHeaderWrapClass} xl:mb-0 xl:max-w-none`}
          >
            <div className="w-full">
              <p className={landingEyebrowClass}>Connected Sources</p>
              <h2
                className={`${landingSectionTitleClass} ${landingTitleGradientBySection.supportedFormats}`}
              >
                Unify your entire production knowledge ecosystem
              </h2>
              <p className={landingSectionLeadClass}>
                AverQel connects to the tools you use every day. Whether it is a GitHub repo, a
                Notion workspace, a Gmail inbox, or a local PDF, the platform automatically parses,
                syncs, and indexes everything inside your private account.
              </p>
            </div>

            <div className="mt-10 grid auto-rows-fr grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4 lg:gap-6">
              {formats.map((format, i) => {
                const Icon = format.icon;
                return (
                  <motion.div
                    key={format.name}
                    initial={{ opacity: 0, scale: 0.95 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    whileHover={{ y: -6, scale: 1.02 }}
                    transition={{ delay: i * 0.04, duration: 0.35 }}
                    className="group theme-panel hover:bg-primary/5 hover:border-primary/30 flex h-full min-h-[9rem] flex-col items-center justify-center gap-2.5 rounded-[1.2rem] border p-4 text-center shadow-sm transition-all duration-300 hover:shadow-[0_18px_50px_rgba(0,255,163,0.1)] sm:min-h-[10rem] sm:p-5 lg:min-h-[10.5rem] lg:gap-3 lg:rounded-[1.35rem] lg:p-6"
                  >
                    <div
                      className={`flex h-9 w-9 items-center justify-center rounded-xl border ${format.bg} sm:h-10 sm:w-10 lg:h-11 lg:w-11`}
                    >
                      <Icon size={15} className={format.color} />
                    </div>
                    <div>
                      <p className="text-foreground text-[13px] font-bold sm:text-sm">
                        {format.name}
                      </p>
                      <p className="text-[10px] leading-4 text-slate-500">{format.description}</p>
                    </div>
                  </motion.div>
                );
              })}
            </div>

            <div className="theme-panel border-glass-border hover:border-primary/25 mt-8 flex items-start gap-4 rounded-[1.35rem] border p-6 shadow-sm transition-all duration-300 hover:-translate-y-0.5 hover:shadow-[0_18px_50px_rgba(0,255,163,0.08)] sm:mt-10">
              <ScanSearch size={18} className="text-primary shrink-0" />
              <p className="text-muted-foreground text-sm leading-6">
                <span className="text-foreground font-bold">Intelligent OCR | Crawler</span> |
                Scanned documents, images, live websites, and connector sources are automatically
                indexed through high-fidelity extraction pipelines.
              </p>
            </div>
          </motion.div>

          {/* Right: Pipeline visualization */}
          <motion.div
            initial={{ opacity: 0, x: 24 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="flex h-full"
          >
            <div className="theme-panel border-glass-border relative flex h-full w-full flex-col overflow-hidden rounded-2xl border p-5 shadow-[0_40px_100px_rgba(var(--primary),0.1)] sm:p-8">
              <div className="mb-5 flex items-center gap-2">
                <Layers size={16} className="text-primary" />
                <span className="text-muted-foreground text-xs font-black tracking-[0.2em] uppercase">
                  Ingestion Pipeline
                </span>
              </div>

              {/* Pipeline stages */}
              <div className="space-y-0">
                {pipelineStages.map((stage, i) => (
                  <div key={stage.label}>
                    <div className="flex flex-col items-start gap-3 py-3 sm:flex-row sm:items-center sm:gap-4 sm:py-4">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-cyan-400/20 bg-cyan-500/[0.08] sm:h-10 sm:w-10">
                        <span className="text-sm font-bold text-cyan-300">{i + 1}</span>
                      </div>
                      <div>
                        <p className="text-foreground text-sm font-bold">{stage.label}</p>
                        <p className="text-xs text-slate-500">{stage.description}</p>
                      </div>
                      {i < pipelineStages.length - 1 && (
                        <ArrowRight size={14} className="ml-auto hidden text-slate-600 sm:block" />
                      )}
                    </div>
                    {i < pipelineStages.length - 1 && (
                      <div className="ml-4 h-4 w-px bg-gradient-to-b from-cyan-400/20 to-transparent sm:ml-5" />
                    )}
                  </div>
                ))}
              </div>

              {/* Status preview */}
              <div className="border-glass-border bg-muted/20 mt-5 rounded-xl border p-4">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500">Each document shows real-time status:</span>
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {[
                    "queued",
                    "downloading",
                    "parsing",
                    "chunking",
                    "embedding",
                    "indexed",
                    "failed",
                    "dead_lettered",
                  ].map((status) => (
                    <span
                      key={status}
                      className={`rounded-full px-3 py-1 text-[10px] font-semibold ${
                        status === "indexed"
                          ? "border border-emerald-400/20 bg-emerald-500/[0.1] text-emerald-300"
                          : status === "failed" || status === "dead_lettered"
                            ? "border border-rose-400/20 bg-rose-500/[0.08] text-rose-300"
                            : "border border-white/[0.08] bg-white/[0.03] text-slate-400"
                      }`}
                    >
                      {status}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </motion.section>
  );
}
