"use client";

import { motion } from "framer-motion";
import { BookOpen, BriefcaseBusiness, Code2, UsersRound } from "lucide-react";
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

const useCases = [
  {
    title: "Research and study",
    icon: BookOpen,
    accent: "text-cyan-300 border-cyan-400/25 bg-cyan-500/[0.08]",
    body: "Upload source material, ask grounded questions, compare evidence, then turn the result into structured notes or an exportable draft.",
  },
  {
    title: "Project and knowledge work",
    icon: BriefcaseBusiness,
    accent: "text-emerald-300 border-emerald-400/25 bg-emerald-500/[0.08]",
    body: "Create focused collections, keep project context organized, use DeepSpace to draft and analyze, and save useful outcomes for the next session.",
  },
  {
    title: "Technical work",
    icon: Code2,
    accent: "text-violet-300 border-violet-400/25 bg-violet-500/[0.08]",
    body: "Use local or cloud providers, organize reference files, inspect supported code and text files in the Library, and connect approved tools when they are needed.",
  },
  {
    title: "Controlled collaboration",
    icon: UsersRound,
    accent: "text-amber-300 border-amber-400/25 bg-amber-500/[0.08]",
    body: "Share selected document collections deliberately, keep ownership clear, and use permission-aware connections instead of exposing an entire workspace by default.",
  },
];

export default function UseCases() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 12,
    scaleRange: [0.996, 1.005],
  });

  return (
    <motion.section ref={ref} style={style} id="use-cases" className={landingSectionShellClass}>
      <div className={landingContentClass}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: "-100px" }}
          transition={{ type: "spring", stiffness: 100, damping: 20 }}
          className={landingHeaderWrapClass}
        >
          <p className={landingEyebrowClass}>Made for Real Work</p>
          <h2
            className={`${landingSectionTitleClass} ${landingTitleGradientBySection.supportedFormats}`}
          >
            One workspace, different ways to make progress
          </h2>
          <p className={landingSectionLeadClass}>
            AverQel adapts to the source material and the task. The workflow remains clear: organize
            context, ask better questions, make the result useful, and stay in control.
          </p>
        </motion.div>

        <div className="grid gap-5 sm:grid-cols-2">
          {useCases.map((useCase, index) => {
            const Icon = useCase.icon;
            return (
              <motion.article
                key={useCase.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: "-80px" }}
                transition={{ type: "spring", stiffness: 88, damping: 18, delay: index * 0.06 }}
                className="theme-panel group relative overflow-hidden rounded-2xl border p-5 transition-all duration-500 hover:-translate-y-1 hover:border-white/[0.15] hover:shadow-[0_24px_70px_rgba(0,0,0,0.24)] sm:p-6"
              >
                <span
                  className={`flex h-12 w-12 items-center justify-center rounded-2xl border ${useCase.accent}`}
                >
                  <Icon size={19} />
                </span>
                <h3 className="mt-5 text-xl font-black tracking-tight text-white">
                  {useCase.title}
                </h3>
                <p className="mt-3 max-w-xl text-sm leading-7 text-slate-300">{useCase.body}</p>
              </motion.article>
            );
          })}
        </div>
      </div>
    </motion.section>
  );
}
