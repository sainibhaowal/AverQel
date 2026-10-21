"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Cpu,
  FolderOpen,
  Menu,
  Plug,
  Search,
  Settings,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import AverQelLogo from "../ui/AverQelLogo";
import { QEL_CONNECT_NAME } from "@/lib/brand";

const navLinks = [
  { name: "Documents Hub", href: "#documents-hub", icon: FolderOpen },
  { name: "Query", href: "#query", icon: Search },
  { name: QEL_CONNECT_NAME, href: "#qel-connect", icon: Users },
  { name: "DeepSpace", href: "#deepspace", icon: Cpu },
  { name: "AI Providers", href: "#providers", icon: Settings },
  { name: "MCP Servers", href: "#mcp", icon: Plug },
  { name: "Workspace controls", href: "#workspace-controls", icon: Settings },
  { name: "Docs", href: "/documentation", icon: BookOpen },
];

export default function MobileNav() {
  const [isOpen, setIsOpen] = useState(false);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [isOpen]);

  const linkVariants = {
    hidden: { opacity: 0, y: reduceMotion ? 0 : 6 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: reduceMotion ? 0 : 0.16, ease: "easeOut" as const },
    },
  };

  const listVariants = {
    hidden: {},
    visible: {
      transition: {
        staggerChildren: reduceMotion ? 0 : 0.035,
        delayChildren: reduceMotion ? 0 : 0.04,
      },
    },
  };

  const motionTransition = reduceMotion ? { duration: 0 } : { duration: 0.18 };

  return (
    <div className="flex xl:hidden">
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/[0.1] bg-white/[0.035] text-slate-100 transition-colors hover:border-teal-200/35 hover:bg-teal-200/[0.08] focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan-200"
        aria-label="Open menu"
        aria-expanded={isOpen}
        aria-controls="averqel-mobile-navigation"
      >
        <Menu size={19} />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={reduceMotion ? undefined : { opacity: 0 }}
            transition={motionTransition}
            onClick={() => setIsOpen(false)}
            className="fixed inset-0 z-[100] flex items-center justify-center bg-[#02060c]/80 p-3 backdrop-blur-md sm:p-5"
          >
            <motion.div
              id="averqel-mobile-navigation"
              role="dialog"
              aria-modal="true"
              aria-labelledby="averqel-mobile-navigation-title"
              initial={reduceMotion ? false : { opacity: 0, y: -10, scale: 0.99 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={reduceMotion ? undefined : { opacity: 0, y: -6, scale: 0.99 }}
              transition={
                reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 260, damping: 28 }
              }
              onClick={(event) => event.stopPropagation()}
              className="max-h-[calc(100dvh-1.5rem)] w-full max-w-[1080px] overflow-y-auto rounded-[1.6rem] border border-cyan-100/[0.12] bg-[radial-gradient(ellipse_at_top_right,rgba(0,184,255,0.08),transparent_38%),linear-gradient(145deg,#0a1119,#05090f_62%)] shadow-[0_35px_120px_rgba(0,0,0,0.65)] sm:max-h-[calc(100dvh-2.5rem)] sm:rounded-[2rem]"
            >
              <div className="flex items-center justify-between border-b border-white/[0.07] px-4 py-3.5 sm:px-6 sm:py-4">
                <div className="flex min-w-0 items-center gap-3">
                  <AverQelLogo size="nav" animateMark />
                  <span className="hidden h-7 w-px bg-white/10 sm:block" aria-hidden="true" />
                  <span className="hidden font-mono text-[0.6rem] font-bold tracking-[0.18em] text-slate-500 uppercase sm:inline">
                    Workspace navigation
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => setIsOpen(false)}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/[0.09] bg-white/[0.035] text-slate-300 transition-colors hover:border-rose-200/30 hover:bg-rose-200/[0.07] hover:text-white focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-cyan-200"
                  aria-label="Close menu"
                >
                  <X size={19} />
                </button>
              </div>

              <div className="px-4 py-5 sm:px-6 sm:py-6 lg:px-8">
                <div className="mb-4 flex flex-col justify-between gap-2 sm:mb-5 sm:flex-row sm:items-end">
                  <div>
                    <p className="font-mono text-[0.62rem] font-bold tracking-[0.2em] text-teal-200/80 uppercase">
                      Explore AverQel
                    </p>
                    <h2
                      id="averqel-mobile-navigation-title"
                      className="mt-1 text-xl font-bold tracking-tight text-white sm:text-2xl"
                    >
                      Choose where to go
                    </h2>
                  </div>
                  <p className="max-w-sm text-xs leading-5 text-slate-400 sm:text-right sm:text-sm">
                    Your documents, AI work, and workspace controls in one place.
                  </p>
                </div>

                <motion.nav
                  aria-label="Main navigation"
                  initial={reduceMotion ? false : "hidden"}
                  animate="visible"
                  variants={listVariants}
                  className="grid grid-cols-2 gap-2.5 sm:gap-3 md:grid-cols-4"
                >
                  {navLinks.map((link) => {
                    const Icon = link.icon;

                    return (
                      <motion.div key={link.name} variants={linkVariants}>
                        <Link
                          href={link.href}
                          onClick={() => setIsOpen(false)}
                          className="group flex min-h-[3.65rem] items-center gap-2 rounded-xl border border-white/[0.075] bg-white/[0.025] px-2.5 py-2 text-slate-200 transition duration-200 hover:-translate-y-0.5 hover:border-teal-200/25 hover:bg-teal-200/[0.055] hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-200 sm:min-h-[4.1rem] sm:gap-3 sm:px-3"
                        >
                          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-teal-100/[0.1] bg-teal-100/[0.045] text-teal-100/80 transition-colors group-hover:border-teal-200/25 group-hover:bg-teal-200/[0.1] group-hover:text-teal-100 sm:h-9 sm:w-9">
                            <Icon size={16} aria-hidden="true" />
                          </span>
                          <span className="min-w-0 flex-1 text-[0.7rem] leading-tight font-semibold sm:text-sm">
                            {link.name}
                          </span>
                          <ArrowUpRight
                            size={14}
                            className="hidden shrink-0 text-slate-600 transition-colors group-hover:text-teal-100 sm:block"
                            aria-hidden="true"
                          />
                        </Link>
                      </motion.div>
                    );
                  })}
                </motion.nav>

                <div className="mt-4 grid grid-cols-2 gap-2.5 border-t border-white/[0.07] pt-4 sm:mt-5 sm:gap-3 sm:pt-5">
                  <Link
                    href="/auth/login"
                    onClick={() => setIsOpen(false)}
                    className="flex min-h-11 items-center justify-center rounded-xl border border-white/[0.11] bg-white/[0.035] px-3 text-sm font-semibold text-slate-200 transition-colors hover:border-white/20 hover:bg-white/[0.07] hover:text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-200"
                  >
                    Log in
                  </Link>
                  <Link
                    href="/auth/signup"
                    onClick={() => setIsOpen(false)}
                    className="flex min-h-11 items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-emerald-300 to-cyan-300 px-3 text-sm font-bold text-slate-950 shadow-[0_12px_32px_rgba(45,212,191,0.15)] transition hover:brightness-110 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-100"
                  >
                    Get started <ArrowRight size={16} aria-hidden="true" />
                  </Link>
                </div>

                <p className="mt-3 text-center font-mono text-[0.55rem] tracking-[0.12em] text-slate-600 uppercase sm:mt-4">
                  Knowledge · AI · action
                </p>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
