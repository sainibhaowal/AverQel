"use client";

import { motion } from "framer-motion";
import { ImageIcon, MonitorSmartphone } from "lucide-react";
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

const screenshots = [
  {
    title: "DeepSpace Chat",
    description:
      "Use this slot for a real DeepSpace conversation screenshot showing grounded answers, notes, memory, and safe approval prompts.",
    fileHint: "/public/landing-proof/deepspace-runtime.png",
    accent: "from-cyan-400/35 via-cyan-300/10 to-transparent",
    glow: "bg-cyan-400/15",
  },
  {
    title: "Workspace Editor And Deliverables",
    description:
      "Use this slot for the real editor or split-workspace view showing notes, drafts, exports, and the output side of agentic execution.",
    fileHint: "/public/landing-proof/workspace-editor.png",
    accent: "from-emerald-400/35 via-emerald-300/10 to-transparent",
    glow: "bg-emerald-400/15",
  },
];

export default function ProductScreenshotGallery() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 14,
    scaleRange: [0.995, 1.006],
  });

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
          <p className={`${landingEyebrowClass} text-amber-300`}>Real Product Proof</p>
          <h2 className={`${landingSectionTitleClass} ${landingTitleGradientBySection.techStack}`}>
            Reserved space for real product screenshots, not fake demos
          </h2>
          <p className={landingSectionLeadClass}>
            This section is intentionally structured for actual shipped-product screenshots. The
            frames are ready now, and each panel is labeled with the exact kind of proof image that
            should replace the placeholder when you add your PNGs.
          </p>
        </motion.div>

        <div className="grid gap-6 xl:grid-cols-3">
          {screenshots.map((item, index) => (
            <motion.article
              key={item.title}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{
                type: "spring",
                stiffness: 88,
                damping: 18,
                delay: index * 0.05,
              }}
              className="group relative overflow-hidden rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(9,13,19,0.92),rgba(5,9,14,0.82))] p-4 shadow-[0_30px_90px_rgba(0,0,0,0.3)]"
            >
              <div
                className={`pointer-events-none absolute -top-10 -right-10 h-36 w-36 rounded-full blur-[90px] ${item.glow}`}
              />
              <div
                className={`pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r ${item.accent}`}
              />

              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <p className="text-[11px] font-bold tracking-[0.24em] text-slate-400 uppercase">
                    Screenshot Slot
                  </p>
                  <h3 className="mt-2 text-lg font-black tracking-tight text-white">
                    {item.title}
                  </h3>
                </div>
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.04] text-slate-200">
                  <MonitorSmartphone size={18} />
                </div>
              </div>

              <div className="relative overflow-hidden rounded-[1.5rem] border border-white/10 bg-[#080c12] p-3">
                <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.08),transparent_38%),linear-gradient(180deg,rgba(255,255,255,0.04),transparent_40%)]" />
                <div className="relative aspect-[16/10] overflow-hidden rounded-[1.15rem] border border-white/8 bg-[linear-gradient(135deg,rgba(18,24,32,0.96),rgba(8,12,18,0.94))]">
                  <div className="absolute inset-x-0 top-0 flex items-center justify-between border-b border-white/8 bg-black/20 px-4 py-2.5">
                    <div className="flex gap-2">
                      <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
                      <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
                      <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
                    </div>
                    <span className="text-[10px] font-bold tracking-[0.22em] text-slate-400 uppercase">
                      Replace With Real PNG
                    </span>
                  </div>
                  <div className="absolute inset-0 flex flex-col items-center justify-center px-6 text-center">
                    <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full border border-white/10 bg-white/[0.04] text-slate-200 shadow-[0_0_0_1px_rgba(255,255,255,0.02),0_0_40px_rgba(255,255,255,0.06)]">
                      <ImageIcon size={22} />
                    </div>
                    <p className="max-w-xs text-sm leading-7 font-semibold text-slate-200">
                      Drop your real product screenshot here later to replace this proof panel.
                    </p>
                    <code className="mt-4 rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-[10px] text-slate-400">
                      {item.fileHint}
                    </code>
                  </div>
                </div>
              </div>

              <p className="mt-4 text-sm leading-7 text-slate-400">{item.description}</p>
            </motion.article>
          ))}
        </div>
      </div>
    </motion.section>
  );
}
