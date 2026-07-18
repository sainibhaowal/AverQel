"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, Home } from "lucide-react";
import { motion } from "framer-motion";

export default function Breadcrumbs() {
  const pathname = usePathname();
  const paths = pathname.split("/").filter((path) => path !== "");
  const nonNavigableCrumbs = new Set(["/dashboard/admin", "/dashboard/settings"]);

  // Generate crumbs
  const crumbs = paths.map((path, index) => {
    const href = `/${paths.slice(0, index + 1).join("/")}`;
    const label = path === "dashboard" ? "Home" : path.replace(/-/g, " ");
    const isLast = index === paths.length - 1;
    const isClickable = !isLast && !nonNavigableCrumbs.has(href);

    return { label, href, isLast, isClickable };
  });

  if (crumbs.length === 1 && crumbs[0]?.href === "/dashboard") {
    return (
      <nav className="text-muted-foreground flex items-center space-x-2 text-xs font-medium">
        <Link
          href="/dashboard"
          className="hover:text-foreground group flex items-center gap-1.5 transition-colors"
        >
          <div className="bg-muted rounded-md p-1 transition-colors group-hover:bg-blue-500/10">
            <Home size={14} />
          </div>
        </Link>
        <div className="flex items-center space-x-2">
          <ChevronRight size={14} className="text-muted-foreground/40" />
          <motion.span
            initial={{ opacity: 0, x: -4 }}
            animate={{ opacity: 1, x: 0 }}
            className="text-foreground bg-muted border-glass-border rounded-md border px-2 py-1 capitalize"
          >
            Dashboard
          </motion.span>
        </div>
      </nav>
    );
  }

  if (crumbs.length <= 1) return null;

  return (
    <nav className="text-muted-foreground flex items-center space-x-2 text-xs font-medium">
      <Link
        href="/dashboard"
        className="hover:text-foreground group flex items-center gap-1.5 transition-colors"
      >
        <div className="bg-muted rounded-md p-1 transition-colors group-hover:bg-blue-500/10">
          <Home size={14} />
        </div>
      </Link>

      {crumbs.slice(1).map((crumb) => (
        <div key={crumb.href} className="flex items-center space-x-2">
          <ChevronRight size={14} className="text-muted-foreground/40" />
          {!crumb.isClickable ? (
            <motion.span
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              className="text-foreground bg-muted border-glass-border rounded-md border px-2 py-1 capitalize"
            >
              {crumb.label}
            </motion.span>
          ) : (
            <Link
              href={crumb.href}
              className="hover:text-foreground hover:bg-muted rounded-md px-2 py-1 capitalize transition-colors"
            >
              {crumb.label}
            </Link>
          )}
        </div>
      ))}
    </nav>
  );
}
