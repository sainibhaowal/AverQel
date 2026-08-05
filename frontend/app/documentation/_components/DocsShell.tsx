"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "framer-motion";
import { BookOpen, ChevronRight, Zap } from "lucide-react";
import { Menu, X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import ParticleBackground from "../../components/marketing/ParticleBackground";
import { docsNavGroups } from "./docsNav";

export function DocsShell({
  title,
  intro,
  children,
}: {
  title: string;
  intro: string;
  children: ReactNode;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!menuOpen) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, [menuOpen]);

  return (
    <main className="bg-background text-foreground relative min-h-[100svh] overflow-hidden lg:h-[100dvh]">
      {/* Background Intelligence Mesh - Lower Opacity for Docs */}
      <div className="pointer-events-none absolute inset-0 opacity-[0.08] lg:opacity-[0.15]">
        <ParticleBackground />
      </div>

      <div className="relative z-10 flex w-full flex-col gap-4 px-4 py-4 sm:px-5 sm:py-5 lg:h-full lg:flex-row lg:gap-5 lg:px-5 lg:py-5">
        <header className="flex items-center justify-between lg:hidden">
          <Link
            href="/"
            className="text-primary group flex items-center gap-3 text-lg font-black tracking-tighter"
          >
            <div className="bg-primary/10 flex h-10 w-10 items-center justify-center rounded-xl transition-transform group-hover:scale-110">
              <BookOpen size={20} />
            </div>
            AverQel OS
          </Link>
          <button
            type="button"
            onClick={() => setMenuOpen(true)}
            className="bg-surface-0 border-glass-border text-foreground flex h-11 w-11 items-center justify-center rounded-xl border shadow-sm"
            aria-label="Open documentation menu"
            aria-expanded={menuOpen}
          >
            <Menu size={20} />
          </button>
        </header>

        <aside className="hidden w-full lg:sticky lg:top-5 lg:block lg:h-[calc(100dvh-2.5rem)] lg:w-[280px] lg:flex-shrink-0">
          <Link
            href="/"
            className="text-primary group mb-8 flex items-center gap-3 text-lg font-black tracking-tighter"
          >
            <div className="bg-primary/10 flex h-10 w-10 items-center justify-center rounded-xl transition-transform group-hover:scale-110">
              <BookOpen size={20} />
            </div>
            AverQel OS
          </Link>
          <nav className="theme-panel docs-scrollbar bg-background/50 flex h-[calc(100%-4rem)] flex-col gap-4 overflow-x-hidden overflow-y-auto rounded-2xl border p-4 backdrop-blur-xl">
            {docsNavGroups.map((group) => (
              <div key={group.group} className="space-y-1">
                <h4 className="text-muted-foreground/50 mb-1 px-4 text-[9px] font-black tracking-wider uppercase">
                  {group.group}
                </h4>
                {group.items.map((item) => {
                  const hasSubItems = item.items && item.items.length > 0;
                  return (
                    <div key={item.href} className="space-y-0.5">
                      <Link
                        href={item.href}
                        className="text-muted-foreground hover:bg-primary/10 hover:text-primary group flex w-full items-center justify-between rounded-xl px-4 py-2.5 text-xs font-bold transition-all"
                      >
                        <div className="flex items-center gap-3">
                          {item.icon && (
                            <span className="opacity-40 group-hover:opacity-100">{item.icon}</span>
                          )}
                          {item.title}
                        </div>
                        {!hasSubItems && (
                          <ChevronRight
                            size={12}
                            className="opacity-0 transition-all group-hover:translate-x-1 group-hover:opacity-40"
                          />
                        )}
                      </Link>
                      {hasSubItems && (
                        <div className="ml-5 space-y-1 border-l border-white/[0.05] py-1 pr-2 pl-9">
                          {item.items!.map((subItem) => (
                            <Link
                              key={subItem.href}
                              href={subItem.href}
                              className="hover:text-primary block py-1.5 text-[11px] font-semibold text-slate-500 transition-colors"
                            >
                              {subItem.title}
                            </Link>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ))}
          </nav>
        </aside>

        <article className="min-w-0 flex-1 lg:pl-0">
          <div className="space-y-12 pb-14 lg:hidden">
            <div className="mb-8 max-w-4xl">
              <div className="bg-primary/10 text-primary mb-6 inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-[10px] font-black tracking-[0.3em] uppercase">
                <Zap size={10} className="animate-pulse" />
                Technical Guidebook
              </div>
              <h1 className="text-foreground text-4xl font-black tracking-tight sm:text-5xl">
                {title}
              </h1>
              <p className="text-muted-foreground/80 mt-6 text-lg leading-relaxed font-medium sm:text-xl">
                {intro}
              </p>
            </div>
            {children}
          </div>

          <div className="hidden h-full lg:block">
            <div className="workspace-fit-shell h-full">
              <div className="workspace-fit-page h-full">
                <div className="workspace-fit-pane">
                  <div className="workspace-fit-scroll docs-scrollbar pr-1 lg:pr-3">
                    <div className="mb-16 w-full max-w-none">
                      <div className="bg-primary/10 text-primary mb-6 inline-flex items-center gap-2 rounded-full px-4 py-1.5 text-[10px] font-black tracking-[0.3em] uppercase">
                        <Zap size={10} className="animate-pulse" />
                        Technical Guidebook
                      </div>
                      <h1 className="text-foreground text-4xl font-black tracking-tight sm:text-5xl lg:text-7xl">
                        {title}
                      </h1>
                      <p className="text-muted-foreground/80 mt-8 text-xl leading-relaxed font-medium">
                        {intro}
                      </p>
                    </div>
                    <div className="space-y-12 pb-12">{children}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </article>
      </div>

      <AnimatePresence>
        {menuOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setMenuOpen(false)}
            className="fixed inset-0 z-50 bg-black/70 px-4 py-4 backdrop-blur-xl lg:hidden"
          >
            <motion.div
              initial={{ y: 20, opacity: 0, scale: 0.98 }}
              animate={{ y: 0, opacity: 1, scale: 1 }}
              exit={{ y: 16, opacity: 0, scale: 0.98 }}
              transition={{ type: "spring", stiffness: 240, damping: 24 }}
              onClick={(event) => event.stopPropagation()}
              className="theme-panel bg-background/95 mx-auto flex h-full w-full max-w-md flex-col overflow-hidden rounded-[1.8rem] border p-4 shadow-2xl"
            >
              <div className="mb-4 flex items-center justify-between gap-4">
                <Link
                  href="/"
                  onClick={() => setMenuOpen(false)}
                  className="text-primary flex items-center gap-3 text-lg font-black tracking-tighter"
                >
                  <div className="bg-primary/10 flex h-10 w-10 items-center justify-center rounded-xl">
                    <BookOpen size={20} />
                  </div>
                  AverQel OS
                </Link>
                <button
                  type="button"
                  onClick={() => setMenuOpen(false)}
                  className="bg-surface-0 border-glass-border text-foreground flex h-11 w-11 items-center justify-center rounded-xl border shadow-sm"
                  aria-label="Close documentation menu"
                >
                  <X size={20} />
                </button>
              </div>

              <nav className="docs-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
                {docsNavGroups.map((group) => (
                  <div key={group.group} className="space-y-1">
                    <h4 className="text-muted-foreground/50 mb-1 px-4 text-[9px] font-black tracking-wider uppercase">
                      {group.group}
                    </h4>
                    {group.items.map((item) => {
                      const hasSubItems = item.items && item.items.length > 0;
                      return (
                        <div key={item.href} className="space-y-0.5">
                          <Link
                            href={item.href}
                            onClick={() => setMenuOpen(false)}
                            className="text-muted-foreground hover:bg-primary/10 hover:text-primary group flex items-center justify-between rounded-xl border border-white/5 px-4 py-3 text-xs font-bold transition-all"
                          >
                            <div className="flex items-center gap-3">
                              {item.icon && <span className="opacity-50">{item.icon}</span>}
                              {item.title}
                            </div>
                            {!hasSubItems && <ChevronRight size={12} className="opacity-40" />}
                          </Link>
                          {hasSubItems && (
                            <div className="ml-6 space-y-1 border-l border-white/[0.05] py-1 pr-2 pl-10">
                              {item.items!.map((subItem) => (
                                <Link
                                  key={subItem.href}
                                  href={subItem.href}
                                  onClick={() => setMenuOpen(false)}
                                  className="hover:text-primary block py-1.5 text-[11px] font-semibold text-slate-500 transition-colors"
                                >
                                  {subItem.title}
                                </Link>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                ))}
              </nav>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </main>
  );
}

export function DocsSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="theme-panel border-glass-border bg-background/40 hover:border-primary/20 rounded-3xl border p-8 backdrop-blur-md transition-all">
      <h2 className="text-foreground mb-6 flex items-center gap-3 text-2xl font-black">
        <div className="bg-primary h-6 w-1.5 rounded-full" />
        {title}
      </h2>
      <div className="text-muted-foreground space-y-4 text-base leading-8 font-medium">
        {children}
      </div>
    </section>
  );
}

export function DocsCards({
  items,
}: {
  items: Array<{ title: string; body: string; href?: string }>;
}) {
  return (
    <div className="grid gap-6 md:grid-cols-2">
      {items.map((item) => {
        const content = (
          <>
            <h3 className="text-foreground mb-3 text-xl font-black">{item.title}</h3>
            <p className="text-muted-foreground text-sm leading-relaxed font-medium">{item.body}</p>
            {item.href && (
              <div className="text-primary mt-6 flex items-center gap-2 text-xs font-black tracking-widest uppercase opacity-0 transition-all group-hover:opacity-100">
                Explore Module <ChevronRight size={14} />
              </div>
            )}
          </>
        );
        return item.href ? (
          <Link
            key={item.href}
            href={item.href}
            className="theme-panel border-glass-border bg-background/40 group hover:border-primary/40 hover:shadow-primary/5 relative overflow-hidden rounded-3xl border p-8 backdrop-blur-md transition-all hover:-translate-y-1 hover:shadow-2xl"
          >
            {content}
          </Link>
        ) : (
          <div
            key={item.title}
            className="theme-panel border-glass-border bg-background/40 rounded-3xl border p-8 backdrop-blur-md"
          >
            {content}
          </div>
        );
      })}
    </div>
  );
}
