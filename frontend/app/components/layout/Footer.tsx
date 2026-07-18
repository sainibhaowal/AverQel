"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import AverQelLogo from "../ui/AverQelLogo";
import { BRAND_NAME } from "@/lib/brand";
import { useLandingSectionMotion } from "../marketing/landingMotion";

const links = [
  {
    title: "Product",
    items: [
      { label: "How It Works", href: "#how-it-works" },
      { label: "Surfaces", href: "#platform-surfaces" },
      { label: "Features", href: "#features" },
      { label: "Security", href: "#security" },
      { label: "Docs", href: "/documentation" },
    ],
  },
  {
    title: "Legal",
    items: [
      { label: "Privacy Policy", href: "/legal/privacy" },
      { label: "Terms of Service", href: "/legal/terms" },
      { label: "Data Retention", href: "/legal/data-retention" },
      { label: "Acceptable Use", href: "/legal/acceptable-use" },
    ],
  },
  {
    title: "Account",
    items: [
      { label: "Sign Up", href: "/auth/signup" },
      { label: "Log In", href: "/auth/login" },
      { label: "Security Overview", href: "/legal/security" },
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
        <div className="grid grid-cols-1 gap-10 sm:grid-cols-2 md:grid-cols-4">
          {/* Brand */}
          <div className="md:col-span-1">
            <AverQelLogo size="footer" showWordmark={true} />
            <p className="text-muted-foreground mt-4 max-w-xs text-sm leading-6">
              The agentic intelligence layer for your entire ecosystem. Grounded chat, DeepSpace,
              and the proactive workspace keep work moving with citations, approvals, and durable
              state across GitHub, Drive, Gmail, Calendar, Notion, and Slack.
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
          <p className="text-muted-foreground/40 text-xs">
            {new Date().getFullYear()} {BRAND_NAME}
          </p>
          <p className="text-muted-foreground/40 text-xs">
            Privacy, security, and trust documentation stay aligned with the live build.
          </p>
        </div>
      </div>
    </motion.footer>
  );
}
