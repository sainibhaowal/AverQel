"use client";

import { motion, AnimatePresence } from "framer-motion";
import { X, Menu, ArrowRight } from "lucide-react";
import Link from "next/link";
import { useState, useEffect } from "react";
import AverQelLogo from "../ui/AverQelLogo";

export default function MobileNav() {
  const [isOpen, setIsOpen] = useState(false);

  // Prevent scroll when menu is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "unset";
    }
    return () => {
      document.body.style.overflow = "unset";
    };
  }, [isOpen]);

  const menuVariants = {
    closed: {
      opacity: 0,
      y: -20,
      transition: {
        staggerChildren: 0.05,
        staggerDirection: -1,
      },
    },
    open: {
      opacity: 1,
      y: 0,
      transition: {
        type: "spring" as const,
        stiffness: 100,
        damping: 20,
        staggerChildren: 0.1,
        delayChildren: 0.2,
      },
    },
  };

  const itemVariants = {
    closed: { opacity: 0, x: -10 },
    open: { opacity: 1, x: 0 },
  };

  const navLinks = [
    { name: "How It Works", href: "#how-it-works" },
    { name: "Surfaces", href: "#platform-surfaces" },
    { name: "Features", href: "#features" },
    { name: "Security", href: "#security" },
    { name: "Docs", href: "/documentation" },
  ];

  return (
    <div className="md:hidden">
      <button
        onClick={() => setIsOpen(true)}
        className="text-foreground flex h-10 w-10 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.03]"
        aria-label="Open menu"
      >
        <Menu size={20} />
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] flex flex-col bg-[#04070d]/98 backdrop-blur-xl"
          >
            {/* Header */}
            <div className="flex items-center justify-between border-b border-white/[0.05] px-4 py-4 sm:px-6 sm:py-6">
              <AverQelLogo size="nav" />
              <button
                onClick={() => setIsOpen(false)}
                className="text-foreground flex h-10 w-10 items-center justify-center rounded-xl border border-white/[0.08] bg-white/[0.03]"
                aria-label="Close menu"
              >
                <X size={20} />
              </button>
            </div>

            {/* Links */}
            <motion.nav
              variants={menuVariants}
              initial="closed"
              animate="open"
              exit="closed"
              className="flex flex-1 flex-col gap-6 px-5 py-8 sm:gap-8 sm:px-8 sm:py-12"
            >
              {navLinks.map((link) => (
                <motion.div key={link.name} variants={itemVariants}>
                  <Link
                    href={link.href}
                    onClick={() => setIsOpen(false)}
                    className="hover:text-primary text-2xl font-black tracking-tight text-white/90 transition-colors sm:text-3xl"
                  >
                    {link.name}
                  </Link>
                </motion.div>
              ))}

              <motion.div
                variants={itemVariants}
                className="flex flex-col gap-3 pt-6 sm:gap-4 sm:pt-8"
              >
                <Link
                  href="/auth/login"
                  onClick={() => setIsOpen(false)}
                  className="flex h-12 items-center justify-center rounded-2xl border border-white/[0.08] bg-white/[0.03] text-base font-bold text-white sm:h-14 sm:text-lg"
                >
                  Log In
                </Link>
                <Link
                  href="/auth/signup"
                  onClick={() => setIsOpen(false)}
                  className="bg-primary text-primary-foreground flex h-12 items-center justify-center gap-3 rounded-2xl text-base font-black shadow-[0_20px_40px_rgba(var(--primary),0.2)] sm:h-14 sm:text-lg"
                >
                  Get Started
                  <ArrowRight size={20} />
                </Link>
              </motion.div>
            </motion.nav>

            {/* Footer */}
            <div className="border-t border-white/[0.05] px-5 py-6 sm:px-8 sm:py-8">
              <p className="text-xs font-bold tracking-widest text-slate-500 uppercase">
                Agentic Intelligence Layer
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
