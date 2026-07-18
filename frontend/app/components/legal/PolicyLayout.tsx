import type { ReactNode } from "react";
import Link from "next/link";

export default function PolicyLayout({
  eyebrow,
  title,
  intro,
  children,
  backHref = "/dashboard/settings/privacy",
  backLabel = "Trust & Privacy",
}: {
  eyebrow: string;
  title: string;
  intro: string;
  children: ReactNode;
  backHref?: string;
  backLabel?: string;
}) {
  return (
    <main className="min-h-[100svh] bg-[#05070f] px-4 py-10 text-white sm:px-6 sm:py-14">
      <div className="mx-auto max-w-4xl">
        <div className="mb-10 flex flex-wrap gap-3 text-xs font-semibold tracking-[0.18em] text-slate-400 uppercase">
          <Link href={backHref} className="hover:text-white">
            {backLabel}
          </Link>
          <span>/</span>
          <Link href="/" className="hover:text-white">
            Home
          </Link>
          <span>/</span>
          <span>{eyebrow}</span>
        </div>
        <p className="text-xs font-semibold tracking-[0.24em] text-cyan-300/80 uppercase">
          {eyebrow}
        </p>
        <h1 className="mt-4 text-3xl font-bold tracking-tight sm:text-4xl md:text-5xl">{title}</h1>
        <p className="mt-4 max-w-3xl text-sm leading-7 text-slate-300 sm:text-base">{intro}</p>

        <div className="mt-10 space-y-8 rounded-[1.75rem] border border-white/8 bg-white/[0.03] p-5 shadow-[0_20px_80px_rgba(2,8,23,0.45)] backdrop-blur sm:mt-12 sm:p-8">
          {children}
        </div>
      </div>
    </main>
  );
}
