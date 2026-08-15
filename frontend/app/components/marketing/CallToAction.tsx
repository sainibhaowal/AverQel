"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  Bot,
  Check,
  CircleGauge,
  FilePlus2,
  SearchCheck,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useLandingSectionMotion } from "./landingMotion";

const signals = [
  { icon: FilePlus2, text: "Bring in your sources", color: "text-cyan-200" },
  { icon: SearchCheck, text: "Ground every answer", color: "text-violet-200" },
  { icon: ShieldCheck, text: "Keep control of connections", color: "text-emerald-200" },
];

export default function CallToAction() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 14,
    scaleRange: [0.994, 1.008],
  });
  const reduceMotion = useReducedMotion();

  return (
    <motion.section
      ref={ref}
      style={style}
      className="landing-trace-frame relative overflow-hidden px-4 py-18 sm:px-8 sm:py-24 lg:px-12 lg:py-32"
    >
      <div className="relative mx-auto w-full max-w-[1800px] overflow-hidden rounded-[2.5rem] border border-emerald-300/15 bg-[radial-gradient(circle_at_18%_25%,rgba(0,255,163,0.14),transparent_26%),radial-gradient(circle_at_80%_70%,rgba(0,184,255,0.16),transparent_28%),linear-gradient(135deg,rgba(6,15,14,0.97),rgba(5,10,19,0.96))] shadow-[0_45px_150px_rgba(0,0,0,0.44)] sm:rounded-[3rem]">
        <div
          aria-hidden="true"
          className="absolute inset-0 [background-image:linear-gradient(rgba(81,255,200,0.07)_1px,transparent_1px),linear-gradient(90deg,rgba(81,255,200,0.07)_1px,transparent_1px)] [background-size:38px_38px] opacity-55"
        />
        <motion.div
          aria-hidden="true"
          className="absolute top-1/2 -left-24 h-72 w-72 -translate-y-1/2 rounded-full border border-cyan-300/15"
          animate={reduceMotion ? undefined : { rotate: 360 }}
          transition={{ duration: 34, repeat: Infinity, ease: "linear" }}
        />
        <motion.div
          aria-hidden="true"
          className="absolute top-1/2 -right-28 h-96 w-96 -translate-y-1/2 rounded-full border border-dashed border-emerald-300/15"
          animate={reduceMotion ? undefined : { rotate: -360 }}
          transition={{ duration: 42, repeat: Infinity, ease: "linear" }}
        />

        <div className="relative grid items-center gap-12 px-6 py-12 sm:px-10 sm:py-16 lg:grid-cols-[1fr_auto_1fr] lg:px-16 xl:px-20">
          <motion.div
            initial={{ opacity: 0, x: -22 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ type: "spring", stiffness: 90, damping: 20 }}
            className="max-w-xl lg:text-left"
          >
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-300/25 bg-emerald-300/[0.08] px-3 py-1.5 font-mono text-[10px] font-bold tracking-[0.2em] text-emerald-200 uppercase">
              <Sparkles size={13} /> Your next workspace
            </div>
            <h2 className="mt-5 max-w-[12ch] [font-family:var(--font-landing-display),var(--font-display),var(--font-inter),sans-serif] text-4xl leading-[0.95] font-black tracking-[-0.035em] text-white sm:text-5xl lg:text-6xl">
              Build on what you know.{" "}
              <span className="bg-gradient-to-r from-emerald-200 via-cyan-200 to-amber-200 bg-clip-text text-transparent">
                Keep what matters.
              </span>
            </h2>
            <p className="mt-6 max-w-lg text-sm leading-7 text-slate-300 sm:text-base sm:leading-8">
              Start with a provider and your documents. Move from source-backed answers into
              DeepSpace work, saved notes, and exportable deliverables—while connections remain
              under your control.
            </p>

            <div className="mt-8 grid gap-2.5 sm:grid-cols-3 lg:grid-cols-1">
              {signals.map((signal, index) => {
                const Icon = signal.icon;
                return (
                  <motion.div
                    key={signal.text}
                    initial={{ opacity: 0, x: -10 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: 0.16 + index * 0.08 }}
                    className="flex items-center gap-2.5 text-xs font-semibold text-slate-300"
                  >
                    <span
                      className={`flex h-7 w-7 items-center justify-center rounded-lg border border-white/[0.09] bg-white/[0.035] ${signal.color}`}
                    >
                      <Icon size={14} />
                    </span>
                    {signal.text}
                  </motion.div>
                );
              })}
            </div>
          </motion.div>

          <motion.div
            aria-hidden="true"
            initial={{ opacity: 0, scale: 0.8 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ type: "spring", stiffness: 90, damping: 18, delay: 0.12 }}
            className="relative mx-auto hidden h-56 w-56 items-center justify-center lg:flex"
          >
            <motion.div
              className="absolute inset-0 rounded-full border border-cyan-200/20"
              animate={reduceMotion ? undefined : { rotate: 360 }}
              transition={{ duration: 18, repeat: Infinity, ease: "linear" }}
            >
              <span className="absolute -top-2 left-1/2 h-3 w-3 -translate-x-1/2 rounded-full bg-cyan-200 shadow-[0_0_22px_#67e8f9]" />
            </motion.div>
            <motion.div
              className="absolute inset-6 rounded-full border border-dashed border-emerald-200/25"
              animate={reduceMotion ? undefined : { rotate: -360 }}
              transition={{ duration: 14, repeat: Infinity, ease: "linear" }}
            >
              <span className="absolute bottom-3 left-0 h-2.5 w-2.5 rounded-full bg-emerald-200 shadow-[0_0_18px_#6ee7b7]" />
            </motion.div>
            <div className="relative flex h-24 w-24 items-center justify-center rounded-[1.8rem] border border-white/15 bg-slate-950/75 shadow-[0_0_70px_rgba(0,255,163,0.16)] backdrop-blur-xl">
              <Bot size={34} className="text-emerald-200" />
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 22 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true, margin: "-100px" }}
            transition={{ type: "spring", stiffness: 90, damping: 20, delay: 0.08 }}
            className="rounded-[1.8rem] border border-white/[0.12] bg-slate-950/55 p-5 shadow-[0_24px_70px_rgba(0,0,0,0.26)] backdrop-blur-xl sm:p-6"
          >
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 font-mono text-[10px] font-bold tracking-[0.2em] text-slate-400 uppercase">
                <CircleGauge size={14} className="text-cyan-200" /> Workspace ready
              </span>
              <span className="flex items-center gap-1.5 text-[10px] font-bold text-emerald-200 uppercase">
                <span className="h-2 w-2 rounded-full bg-emerald-200 shadow-[0_0_12px_#6ee7b7]" />{" "}
                Your control
              </span>
            </div>
            <div className="mt-6 space-y-3">
              {["Add a provider", "Upload source material", "Start a grounded workspace"].map(
                (step, index) => (
                  <div
                    key={step}
                    className="flex items-center gap-3 rounded-xl border border-white/[0.07] bg-white/[0.025] px-3 py-3"
                  >
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-emerald-300/10 text-emerald-200">
                      <Check size={13} />
                    </span>
                    <span className="text-sm font-semibold text-slate-200">{step}</span>
                    <span className="ml-auto font-mono text-[10px] text-slate-600">
                      0{index + 1}
                    </span>
                  </div>
                ),
              )}
            </div>
            <div className="mt-7 grid gap-3 sm:grid-cols-2">
              <Link
                href="/auth/signup"
                className="group inline-flex items-center justify-center gap-2 rounded-xl bg-[linear-gradient(135deg,#00ffa3,#2dd4bf,#22d3ee)] px-5 py-3.5 text-sm font-black text-slate-950 shadow-[0_15px_40px_rgba(0,255,163,0.2)] transition-all hover:-translate-y-0.5 hover:shadow-[0_18px_50px_rgba(0,255,163,0.32)]"
              >
                Start using AverQel{" "}
                <ArrowRight
                  size={16}
                  className="transition-transform group-hover:translate-x-0.5"
                />
              </Link>
              <Link
                href="/documentation"
                className="inline-flex items-center justify-center rounded-xl border border-white/[0.12] bg-white/[0.025] px-5 py-3.5 text-sm font-bold text-white transition-colors hover:border-cyan-200/35 hover:bg-cyan-200/[0.06]"
              >
                Explore the docs
              </Link>
            </div>
            <Link
              href="/auth/login"
              className="mt-4 block text-center text-xs font-semibold text-slate-500 transition-colors hover:text-white"
            >
              Already have an account? Log in
            </Link>
          </motion.div>
        </div>
      </div>
    </motion.section>
  );
}
