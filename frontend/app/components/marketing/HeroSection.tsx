"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowRight, Cpu, FileText, Globe, Hexagon, Shield, Terminal, Zap } from "lucide-react";
import { useState } from "react";
import HeroBackdrop from "./HeroBackdrop";
import HeroMorphingBackground from "./HeroMorphingBackground";
import MobileNav from "./MobileNav";
import { useLandingSectionMotion } from "./landingMotion";
import { useVisibilityAwareInterval } from "@/app/hooks/useVisibilityAwareInterval";
import { landingHeroTitleClass, landingTitleGradientBySection } from "./landingType";
import AverQelLogo from "../ui/AverQelLogo";

const navLinks = [
  { label: "How It Works", href: "#how-it-works" },
  { label: "Surfaces", href: "#platform-surfaces" },
  { label: "Features", href: "#features" },
  { label: "Security", href: "#security" },
  { label: "Docs", href: "/documentation" },
];

const pipelineSteps = [
  {
    icon: Globe,
    accent: "text-[#00b8ff]",
    label: "CONNECTING",
    title: "GitHub repo | Drive folder | Gmail inbox | local files",
    detail: "authenticate | scope access | sync sources | build live context",
  },
  {
    icon: Zap,
    accent: "text-[#00ffa3]",
    label: "STREAMING",
    title: "DeepSpace runtime",
    detail: "plan | lane activity | tool delta | approval | answer stream",
  },
  {
    icon: Hexagon,
    accent: "text-amber-300",
    label: "DELEGATING",
    title: '"Research, edit, validate, then prepare the final answer"',
    detail: "subagents | workspace mode | memory | policy | hooks",
  },
  {
    icon: Shield,
    accent: "text-white",
    label: "VISIBLE",
    title: "Operator can inspect the mission end to end",
    detail: "canvas | approvals | diagnostics | durable state | tenant isolation",
  },
];

const signalCards = [
  { value: "Mission", label: "canvas + lane visibility" },
  { value: "Local + Cloud", label: "provider routing" },
  { value: "Approval", label: "gated execution control" },
];

export default function HeroSection() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 34,
    scaleRange: [0.994, 1.008],
  });
  const [activeStep, setActiveStep] = useState(0);

  useVisibilityAwareInterval(() => {
    setActiveStep((current) => (current + 1) % pipelineSteps.length);
  }, 2400);

  return (
    <motion.section
      ref={ref}
      style={style}
      className="landing-trace-frame relative overflow-hidden"
    >
      <HeroBackdrop />

      <div className="relative z-10 mx-auto flex min-h-[100svh] w-full max-w-[1800px] flex-col px-4 sm:px-8 lg:px-12">
        <nav className="flex items-center justify-between gap-3 py-6 sm:py-8">
          <Link href="/" className="group inline-flex items-center gap-3 md:hidden">
            <AverQelLogo size="nav" showWordmark={false} />
          </Link>

          <Link href="/" className="group hidden items-center gap-3 md:inline-flex">
            <AverQelLogo size="nav" />
          </Link>

          <div className="hidden items-center gap-4 md:flex lg:gap-6 xl:gap-7">
            {navLinks.map((link) => (
              <Link
                key={link.label}
                href={link.href}
                className="text-xs font-medium text-slate-300 transition-colors hover:text-white lg:text-sm"
              >
                {link.label}
              </Link>
            ))}
            <Link
              href="/auth/login"
              className="ml-1 text-xs font-medium text-slate-200 transition-colors hover:text-white lg:ml-2 lg:text-sm"
            >
              Log In
            </Link>
            <Link
              href="/auth/signup"
              className="rounded-full border border-[#00ffa3]/30 bg-[#00ffa3]/12 px-4 py-2 text-xs font-semibold text-[#8effd2] transition-all hover:border-[#00ffa3] hover:bg-[#00ffa3]/20 hover:text-white lg:px-5 lg:text-sm"
            >
              Get Started
            </Link>
          </div>

          <MobileNav />
        </nav>

        <main className="flex flex-1 flex-col justify-center gap-10 py-10 lg:py-14">
          <div className="flex flex-col items-start gap-14 text-left xl:flex-row xl:items-start xl:gap-14 xl:text-left">
            <div className="flex w-full max-w-4xl min-w-0 flex-1 flex-col items-start text-left">
              <div className="mb-8 inline-flex max-w-full items-center gap-3 rounded-full border border-[#00ffa3]/25 bg-[#07110d]/70 px-4 py-2 text-[11px] font-bold tracking-[0.28em] text-slate-300 uppercase shadow-[0_0_24px_rgba(0,255,163,0.08)] backdrop-blur-md">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#00ffa3]/14 text-[#00ffa3]">
                  <Cpu size={13} />
                </span>
                Operator-Grade Agentic Operating Layer
              </div>

              <h1
                className={`${landingHeroTitleClass} ${landingTitleGradientBySection.hero} mb-7 max-w-[12ch] text-left sm:max-w-none`}
              >
                The operator-grade agentic system for your{" "}
                <span className="text-inherit">workspace, missions, and live execution</span>
              </h1>

              <p className="max-w-2xl text-base leading-8 text-slate-300/88 sm:text-lg sm:leading-9">
                AverQel connects GitHub, Google Drive, Gmail, Calendar, Notion, Slack, web search,
                web fetch, crawling, local files, and sandboxed bash into one live DeepSpace
                runtime. It turns user requests into visible missions with orchestration, subagents,
                inline mission canvas diagnostics, approval-gated actions, durable workspace state,
                and cloud-or-local model routing while keeping every action tenant-isolated,
                audited, and under your authority.
              </p>

              <div className="mt-10 flex flex-wrap items-center gap-4">
                <Link
                  href="/auth/signup"
                  className="inline-flex items-center gap-2 rounded-full bg-[linear-gradient(135deg,#00ffa3_0%,#2dd4bf_48%,#00b8ff_100%)] px-8 py-4 text-sm font-black text-slate-950 shadow-[0_24px_60px_rgba(0,255,163,0.24)] transition-all hover:shadow-[0_28px_72px_rgba(0,255,163,0.34)]"
                >
                  Start Using AverQel
                  <ArrowRight size={18} />
                </Link>
                <Link
                  href="#security"
                  className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-slate-950/45 px-7 py-4 text-sm font-semibold text-white backdrop-blur-md transition-all hover:border-[#00ffa3]/28 hover:bg-slate-900/65"
                >
                  <Shield size={17} className="text-slate-400" />
                  Security Overview
                </Link>
                <Link
                  href="/documentation"
                  className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-slate-950/45 px-7 py-4 text-sm font-semibold text-white backdrop-blur-md transition-all hover:border-[#00b8ff]/28 hover:bg-slate-900/65"
                >
                  <FileText size={17} className="text-slate-400" />
                  Production Docs
                </Link>
              </div>

              <div className="mt-12 grid w-full max-w-3xl gap-3 sm:grid-cols-3">
                {signalCards.map((card) => (
                  <div
                    key={card.label}
                    className="rounded-3xl border border-white/8 bg-[linear-gradient(180deg,rgba(10,15,20,0.86),rgba(6,10,15,0.68))] px-5 py-4 backdrop-blur-md"
                  >
                    <div className="text-lg font-black tracking-tight text-white">{card.value}</div>
                    <div className="mt-1 text-xs font-semibold tracking-[0.18em] text-slate-400 uppercase">
                      {card.label}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="relative w-full min-w-0 flex-1">
              <div className="absolute inset-x-[8%] top-[18%] h-40 rounded-full bg-[#00ffa3]/12 blur-[110px]" />
              <div className="absolute inset-x-[16%] bottom-[10%] h-36 rounded-full bg-[#00b8ff]/10 blur-[110px]" />

              <div className="relative overflow-hidden rounded-[28px] border border-white/10 bg-[linear-gradient(180deg,rgba(11,16,22,0.94),rgba(7,11,16,0.84))] shadow-[0_34px_120px_rgba(0,0,0,0.48)] backdrop-blur-xl">
                <div className="flex items-center justify-between border-b border-white/8 bg-slate-950/45 px-4 py-3">
                  <div className="flex gap-2">
                    <span className="h-3 w-3 rounded-full bg-slate-600" />
                    <span className="h-3 w-3 rounded-full bg-slate-600" />
                    <span className="h-3 w-3 rounded-full bg-slate-600" />
                  </div>
                  <div className="flex items-center gap-2 font-mono text-[11px] text-slate-500">
                    <Terminal size={12} />
                    averqel | mission runtime
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-[#00ffa3] shadow-[0_0_12px_#00ffa3]" />
                    <span className="text-[10px] font-black tracking-[0.26em] text-[#00ffa3] uppercase">
                      Live
                    </span>
                  </div>
                </div>

                <div className="space-y-5 p-6 font-mono text-sm sm:p-7">
                  <div className="text-slate-200">
                    <span className="mr-2 text-[#00ffa3]">$</span>
                    averqel pipeline | watch
                  </div>

                  {pipelineSteps.map((step, index) => {
                    const Icon = step.icon;
                    const isActive = index === activeStep;

                    return (
                      <div
                        key={step.label}
                        className={`rounded-2xl border px-4 py-3 transition-all duration-500 ${
                          isActive
                            ? "border-[#00ffa3]/22 bg-white/[0.045] shadow-[0_0_0_1px_rgba(0,255,163,0.05),0_18px_48px_rgba(0,255,163,0.08)]"
                            : "border-white/[0.05] bg-white/[0.02]"
                        }`}
                      >
                        <div className="flex items-center gap-3 text-slate-200">
                          <Icon size={14} className={step.accent} />
                          <span className={`text-xs font-black tracking-[0.22em] ${step.accent}`}>
                            {step.label}
                          </span>
                          <span className="truncate text-sm text-slate-200/95">{step.title}</span>
                        </div>
                        <div className="pt-1 pl-6 text-xs text-slate-500">{step.detail}</div>
                      </div>
                    );
                  })}

                  <div className="flex items-center pt-2">
                    <span className="mr-2 text-[#00ffa3]">$</span>
                    <div className="h-4 w-2.5 animate-pulse bg-[#00ffa3]" />
                  </div>
                </div>

                <div className="flex items-center justify-between border-t border-white/8 bg-[#06090e] px-6 py-3 font-mono text-[10px] text-slate-500">
                  <div className="flex gap-4">
                    <span className="text-[#00ffa3]">
                      Live <span className="text-slate-500">mission diagnostics</span>
                    </span>
                    <span className="text-[#00b8ff]">
                      SSE <span className="text-slate-500">state streaming</span>
                    </span>
                  </div>
                  <span>account: tenant isolated</span>
                </div>
              </div>
            </div>
          </div>

          <div className="relative mt-2 overflow-hidden rounded-[34px] border border-white/8 bg-[linear-gradient(180deg,rgba(6,10,15,0.78),rgba(4,8,12,0.58))] shadow-[0_28px_90px_rgba(0,0,0,0.34)]">
            <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[#00ffa3]/35 to-transparent" />
            <div className="relative h-[260px] sm:h-[320px] lg:h-[380px]">
              <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex items-center justify-between px-5 py-4 font-mono text-[10px] font-bold tracking-[0.22em] text-slate-400 uppercase sm:px-7">
                <span className="text-[#00ffa3]">Runtime Visualization</span>
                <span className="text-slate-500">Particle intelligence field</span>
              </div>
              <div className="pointer-events-none absolute inset-x-[14%] top-[10%] h-28 rounded-full bg-[#00ffa3]/10 blur-[90px]" />
              <div className="pointer-events-none absolute inset-x-[22%] bottom-[6%] h-24 rounded-full bg-[#00b8ff]/10 blur-[90px]" />
              <HeroMorphingBackground className="!z-0" />
            </div>
          </div>
        </main>
      </div>
    </motion.section>
  );
}
