"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import AverQelLogo from "../ui/AverQelLogo";
import { BRAND_NAME } from "@/lib/brand";
import { APP_VERSION } from "@/lib/release";
import { useLandingSectionMotion } from "../marketing/landingMotion";

const links = [
  {
    title: "Product areas",
    items: [
      { label: "Documents Hub", href: "#documents-hub" },
      { label: "Query", href: "#query" },
      { label: "Collections", href: "#collections" },
      { label: "DeepSpace", href: "#deepspace" },
      { label: "AI Providers", href: "#providers" },
      { label: "MCP Servers", href: "#mcp" },
      { label: "Docs", href: "/documentation" },
    ],
  },
  {
    title: "Account",
    items: [
      { label: "Profile settings", href: "/documentation/profile" },
      { label: "Plan and storage", href: "/dashboard/settings/plan" },
      { label: "Sign up", href: "/auth/signup" },
      { label: "Log in", href: "/auth/login" },
    ],
  },
  {
    title: "Trust & help",
    items: [
      { label: "Workspace controls", href: "#workspace-controls" },
      { label: "Trust and policies", href: "/documentation/privacy-security" },
      { label: "Support centre", href: "/documentation/support" },
      { label: "Share feedback", href: "/documentation/feedback" },
    ],
  },
  {
    title: "Legal",
    items: [
      { label: "Privacy policy", href: "/legal/privacy" },
      { label: "Terms of service", href: "/legal/terms" },
      { label: "Data retention", href: "/legal/data-retention" },
      { label: "Acceptable use", href: "/legal/acceptable-use" },
      { label: "Security overview", href: "/legal/security" },
    ],
  },
];

export default function Footer() {
  const { ref, style } = useLandingSectionMotion<HTMLElement>({
    depth: 8,
    scaleRange: [0.998, 1.003],
  });

  return (
    <motion.footer
      ref={ref}
      style={style}
      className="landing-trace-frame border-glass-border bg-surface-0 border-t"
    >
      <div className="mx-auto max-w-[1800px] px-4 py-12 sm:px-8 sm:py-16 lg:px-12">
        <div className="grid grid-cols-1 gap-10 sm:grid-cols-2 xl:grid-cols-5">
          {/* Brand */}
          <div className="md:col-span-1">
            <AverQelLogo size="footer" showWordmark={true} />
            <p className="text-muted-foreground mt-4 max-w-xs text-sm leading-6">
              AverQel brings source documents, evidence-based Query, shared Collections, and
              DeepSpace work together, with separate provider, MCP, and workspace controls.
            </p>
          </div>

          {/* Link columns */}
          {links.map((section) => (
            <div key={section.title}>
              <h4 className="text-muted-foreground mb-4 text-xs font-black tracking-[0.2em] uppercase">
                {section.title}
              </h4>
              <ul className="space-y-3">
                {section.items.map((item) => (
                  <li key={item.label}>
                    <Link
                      href={item.href}
                      className="text-muted-foreground hover:text-primary text-sm transition-colors"
                    >
                      {item.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div className="border-glass-border mt-12 flex flex-col items-center justify-between gap-4 border-t pt-6 sm:mt-14 sm:flex-row sm:pt-8">
          <div className="flex items-center gap-3">
            <p className="text-muted-foreground/40 text-xs">© {BRAND_NAME}</p>
            <span className="bg-primary/10 text-primary border-primary/20 inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-bold tracking-[0.14em] uppercase">
              {APP_VERSION}
              {process.env.NEXT_PUBLIC_GIT_SHA && process.env.NEXT_PUBLIC_GIT_SHA !== "unknown"
                ? ` • ${String(process.env.NEXT_PUBLIC_GIT_SHA).slice(0, 7)}`
                : ""}
            </span>
          </div>
          <p className="text-muted-foreground/40 text-xs">
            Review the privacy, security, and data-retention policies for current details.
          </p>
        </div>
      </div>
    </motion.footer>
  );
}
