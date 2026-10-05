"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { ArrowLeft } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface DashboardSectionHeaderProps {
  title: string;
  subtitle: string;
  icon: LucideIcon;
  accentClassName?: string;
  accentGlowClassName?: string;
  backHref?: string;
  backLabel?: string;
  actions?: React.ReactNode;
}

const LIGHT_ACCENT_COLORS: Record<string, string> = {
  primary: "#0f766e",
  success: "#15803d",
  "cyan-400": "#0e7490",
  "cyan-500": "#0e7490",
  "indigo-500": "#4338ca",
  "slate-500": "#475569",
  "amber-400": "#b45309",
  "amber-500": "#b45309",
  "violet-500": "#6d28d9",
  "emerald-500": "#047857",
  "red-500": "#b91c1c",
  "purple-500": "#7e22ce",
  "blue-500": "#1d4ed8",
  "rose-500": "#be123c",
};

export default function DashboardSectionHeader({
  title,
  subtitle,
  icon: Icon,
  accentClassName = "bg-primary text-primary",
  accentGlowClassName = "shadow-[0_0_18px_rgba(var(--primary),0.28)]",
  backHref,
  backLabel,
  actions,
}: DashboardSectionHeaderProps) {
  const accentColor = accentClassName.split(" ")[0].replace("bg-", "");

  return (
    <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        {backHref && backLabel ? (
          <Link
            href={backHref}
            aria-label={backLabel}
            className="text-muted-foreground hover:text-primary border-border/70 bg-background/40 hover:border-primary/30 hover:bg-primary/5 mb-3 inline-flex w-fit shrink-0 items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-semibold tracking-wide whitespace-nowrap uppercase transition-colors"
          >
            <ArrowLeft size={13} aria-hidden="true" />
            {backLabel}
          </Link>
        ) : null}
        <div className="flex items-center gap-4">
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 36, opacity: 1 }}
            transition={{ type: "spring", stiffness: 300, damping: 24, delay: 0.1 }}
            style={
              {
                "--dashboard-header-accent-light": LIGHT_ACCENT_COLORS[accentColor] ?? "#0f766e",
              } as React.CSSProperties
            }
            className={`dashboard-section-header-accent w-2 shrink-0 rounded-full ${accentClassName.split(" ")[0]} ${accentGlowClassName}`}
          />
          <div className="flex min-w-0 items-center gap-3">
            <Icon
              size={24}
              className={`${accentClassName.split(" ").find((c) => c.startsWith("text-")) || "text-primary"} shrink-0 drop-shadow-[0_0_10px_rgba(var(--primary),0.3)]`}
            />

            <div className="min-w-0">
              <h1 className="text-foreground text-2xl font-black tracking-tight sm:text-3xl md:text-4xl">
                {title}
              </h1>
              <p className="text-foreground/60 mt-1 text-[11px] font-black tracking-[0.22em] uppercase">
                {subtitle}
              </p>

              <motion.div
                initial={{ scaleX: 0, opacity: 0 }}
                animate={{ scaleX: 1, opacity: 1 }}
                transition={{ duration: 0.6, delay: 0.3, ease: "easeOut" }}
                className="settings-divider mt-2 origin-left"
                style={{ maxWidth: "60%" }}
              />
            </div>
          </div>
        </div>
      </div>
      {actions ? (
        <div className="flex max-w-full flex-wrap items-center gap-2 sm:gap-3">{actions}</div>
      ) : null}
    </div>
  );
}
