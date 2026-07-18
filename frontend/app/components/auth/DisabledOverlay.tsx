"use client";

import { motion, AnimatePresence } from "framer-motion";
import { ShieldAlert, LogOut, MessageSquare } from "lucide-react";
import Link from "next/link";
import { useAuth } from "@/app/context/AuthContext";

export default function DisabledOverlay({ isVisible }: { isVisible: boolean }) {
  const { logout } = useAuth();

  return (
    <AnimatePresence>
      {isVisible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/60 p-4 backdrop-blur-md"
        >
          <motion.div
            initial={{ scale: 0.9, opacity: 0, y: 20 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.9, opacity: 0, y: 20 }}
            className="border-warning/20 w-full max-w-lg overflow-hidden rounded-[2rem] border bg-[#0f0f11] shadow-[0_32px_64px_-16px_rgba(234,179,8,0.15)]"
          >
            <div className="bg-warning/10 border-warning/10 border-b px-8 py-10 text-center">
              <div className="bg-warning/20 text-warning mx-auto mb-6 flex h-20 w-20 items-center justify-center rounded-3xl">
                <ShieldAlert size={40} />
              </div>
              <h2 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">
                Account Temporarily Disabled
              </h2>
              <p className="text-warning/80 mt-4 font-medium">
                Your access to AverQel has been restricted by an administrator.
              </p>
            </div>

            <div className="space-y-6 p-8">
              <div className="rounded-2xl border border-white/10 bg-white/5 p-6">
                <p className="text-center text-sm leading-relaxed text-slate-300">
                  All active services and data access have been paused. If you believe this is a
                  mistake or need to resolve an issue, please contact our support team.
                </p>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row">
                <Link
                  href="/dashboard/support"
                  className="bg-warning hover:bg-warning/90 inline-flex flex-1 items-center justify-center gap-2 rounded-xl px-5 py-3.5 text-sm font-bold text-black transition"
                >
                  <MessageSquare size={18} />
                  Contact Support
                </Link>
                <button
                  onClick={() => void logout()}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/5 px-5 py-3.5 text-sm font-bold text-white transition hover:bg-white/10"
                >
                  <LogOut size={18} />
                  Log Out
                </button>
              </div>
            </div>

            <div className="bg-warning/5 px-8 py-4 text-center">
              <p className="text-warning/40 text-[10px] font-bold tracking-[0.2em] uppercase">
                Security Protocol Active
              </p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
