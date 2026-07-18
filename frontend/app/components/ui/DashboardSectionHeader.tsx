"use client";

import Link from "next/link";
import { motion } from "framer-motion";
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
  return (
    <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
      <div className="min-w-0">
        {backHref && backLabel ? (
          <Link
            href={backHref}
            className="text-muted-foreground mb-3 inline-flex text-xs font-semibold tracking-[0.2em] uppercase transition-colors hover:text-white"
          >
            {backLabel}
          </Link>
        ) : null}
        <div className="flex items-center gap-4">
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 36, opacity: 1 }}
            transition={{ type: "spring", stiffness: 300, damping: 24, delay: 0.1 }}
            className={`w-2 shrink-0 rounded-full ${accentClassName.split(" ")[0]} ${accentGlowClassName}`}
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
