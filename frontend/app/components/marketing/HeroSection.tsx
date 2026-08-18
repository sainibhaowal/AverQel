"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { Activity, ArrowRight, Cpu, FileText, Globe, Hexagon, Shield, Zap } from "lucide-react";
import { useState } from "react";
import HeroBackdrop from "./HeroBackdrop";
import HeroMorphingBackground from "./HeroMorphingBackground";
import MobileNav from "./MobileNav";
import { useLandingSectionMotion } from "./landingMotion";
import { useVisibilityAwareInterval } from "@/app/hooks/useVisibilityAwareInterval";
import {
  landingAnimatedGradientTextClass,
  landingHeroTitleClass,
  landingTitleGradientBySection,
} from "./landingType";
import AverQelLogo from "../ui/AverQelLogo";

const navLinks = [
  { label: "How It Works", href: "#how-it-works" },
  { label: "Surfaces", href: "#platform-surfaces" },
  { label: "Use Cases", href: "#use-cases" },
  { label: "Control", href: "#control" },
  { label: "Docs", href: "/documentation" },
];

const pipelineSteps = [
  {
    icon: Globe,
    accent: "text-[#00b8ff]",
    label: "ORGANIZING",
    title: "Documents Hub + Collections",
    detail: "upload | inspect | organize | keep the right context together",
  },
  {
    icon: Zap,
    accent: "text-[#00ffa3]",
    label: "GROUNDING",
    title: "Query answers with source evidence",
    detail: "retrieve | cite | inspect | save useful material to notes",
  },
  {
    icon: Hexagon,
    accent: "text-amber-300",
    label: "WORKING",
    title: "DeepSpace for research and deliverables",
    detail: "draft | analyze | use memory | export notes | review progress",
  },
  {
    icon: Shield,
    accent: "text-white",
    label: "CONNECTING",
    title: "Providers and supported MCP apps",
    detail: "choose a runtime | authorize an account | apply policy | approve actions",
  },
];

const signalCards = [
  { value: "Documents", label: "source-aware workspaces" },
  { value: "Grounded Query", label: "evidence-backed answers" },
  { value: "Your control", label: "approval-gated connections" },
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

        <main className="flex flex-1 flex-col justify-start gap-8 py-8 sm:gap-10 sm:py-10 lg:justify-center lg:py-14">
          <div className="grid items-start gap-10 text-left lg:grid-cols-[1.05fr_0.95fr] lg:gap-12 xl:gap-16 xl:text-left">
            <div className="flex w-full min-w-0 flex-col items-start text-left">
              <div className="mb-8 inline-flex max-w-full items-center gap-3 rounded-full border border-[#00ffa3]/25 bg-[#07110d]/70 px-4 py-2 text-[11px] font-bold tracking-[0.28em] text-slate-300 uppercase shadow-[0_0_24px_rgba(0,255,163,0.08)] backdrop-blur-md">
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#00ffa3]/14 text-[#00ffa3]">
                  <Cpu size={13} />
                </span>
                Your Private AI Workspace
              </div>

              <h1
                className={`${landingHeroTitleClass} ${landingTitleGradientBySection.hero} ${landingAnimatedGradientTextClass} mb-7 max-w-[12ch] text-left sm:max-w-none 2xl:text-[5.6rem]`}
              >
                Turn your documents into{" "}
                <span className="text-inherit">grounded answers and useful work</span>
              </h1>

              <p className="max-w-2xl text-base leading-8 text-slate-300/88 sm:text-lg sm:leading-9">
                Upload and organize documents, ask source-backed questions, then use DeepSpace to
                research, draft, save notes, and create exportable deliverables. Add your preferred
                cloud or local AI provider, and connect supported apps only when you choose to
                authorize them.
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

            <div className="relative w-full min-w-0">
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
                    <Activity size={12} />
                    averqel | productivity runtime
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full bg-[#00ffa3] shadow-[0_0_12px_#00ffa3]" />
                    <span className="text-[10px] font-black tracking-[0.26em] text-[#00ffa3] uppercase">
                      Live
                    </span>
                  </div>
                </div>

                <div className="space-y-3 p-4 font-mono text-xs sm:space-y-4 sm:p-6 sm:text-sm xl:p-8">
                  <div className="text-slate-200">
                    <span className="mr-2 text-[#00ffa3]">$</span>
                    averqel workspace | guide
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
                        <div className="flex min-w-0 items-center gap-2 text-slate-200 sm:gap-3">
                          <Icon size={14} className={step.accent} />
                          <span className={`text-xs font-black tracking-[0.22em] ${step.accent}`}>
                            {step.label}
                          </span>
                          <span className="truncate text-xs text-slate-200/95 sm:text-sm">
                            {step.title}
                          </span>
                        </div>
                        <div className="pt-1 pl-6 text-[10px] leading-5 text-slate-500 sm:text-xs">
                          {step.detail}
                        </div>
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
                      Live <span className="text-slate-500">answer streaming</span>
                    </span>
                    <span className="text-[#00b8ff]">
                      SSE <span className="text-slate-500">state streaming</span>
                    </span>
                  </div>
                  <span>your workspace, your controls</span>
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
